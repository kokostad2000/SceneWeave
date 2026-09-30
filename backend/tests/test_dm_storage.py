import json
import sqlite3

import pytest

from role_theater.contracts import AgentProfileFields, SceneMode, DiscussionConfig, DiscussionParticipantConfig
from role_theater.domain import AgentSpec
from role_theater.storage import Database, SceneRepository, TemplateRepository, migrator


@pytest.mark.parametrize("mode", list(SceneMode))
def test_profile_crud_copy_snapshot_and_reopen(services, database, mode):
    templates, scenes = services
    a = templates.create(AgentProfileFields(name="甲", persona="PRIVATE_A", speech_style="", initial_goal="", private_background="", public_profile="PUBLIC_A"))
    b = templates.copy(a.template_id, new_name="乙")
    assert b.public_profile == "PUBLIC_A"
    config = DiscussionParticipantConfig(focus="PRIVATE_FOCUS", initial_position="PRIVATE_POSITION") if mode == "discussion" else None
    detail = scenes.create(title="场", background="", mode=mode,
        mode_config=DiscussionConfig(topic="议题", materials="资料") if mode == "discussion" else None,
        agent_specs=[AgentSpec(a.template_id, discussion_config=config), AgentSpec(b.template_id)])
    templates.update(a.template_id, public_profile="CHANGED", persona="CHANGED_PRIVATE")
    saved = scenes.get_detail(detail.scene.scene_id)
    assert saved.agents[0].snapshot.public_profile == "PUBLIC_A"
    assert saved.agents[0].snapshot.persona == "PRIVATE_A"
    assert saved.agents[0].discussion_config == config
    assert SceneRepository(Database(database.path)).get_scene(detail.scene.scene_id) == detail.scene
    assert scenes.list_summaries(mode)[0].scene.scene_id == detail.scene.scene_id
    assert scenes.list_summaries(SceneMode.DISCUSSION if mode == "simulation" else SceneMode.SIMULATION) == []
    templates.update(a.template_id, public_profile=" ")
    assert templates.get(a.template_id).public_profile == ""
    templates.remove(a.template_id)
    assert scenes.get_detail(detail.scene.scene_id) == saved


@pytest.mark.parametrize("mode", list(SceneMode))
def test_api_modes_no_model_and_frozen_mode(api_client, mode):
    template_ids=[]
    for name in ["甲", "乙"]:
        r=api_client.post("/api/templates", json=dict(name=name, persona="私有", speech_style="", initial_goal="", private_background="", public_profile="公开"))
        assert r.status_code == 201
        template_ids.append(r.json()["template_id"])
    data=dict(title="场", agents=[dict(template_id=x) for x in template_ids], mode=mode,
        mode_config={"situation":"情境"} if mode == "simulation" else {"topic":"议题"})
    r=api_client.post("/api/scenes",json=data); assert r.status_code==201
    scene_id=r.json()["scene"]["scene_id"]
    assert r.json()["scene"]["mode"]==mode
    assert api_client.patch(f"/api/scenes/{scene_id}",json={"mode":"discussion"}).status_code==405
    assert api_client.get(f"/api/scenes?mode={mode}").json()["scenes"][0]["scene_id"]==scene_id
    assert api_client.get("/api/scenes?mode=other").status_code==422
    if mode == "simulation":
        bad=api_client.post(f"/api/scenes/{scene_id}/agents",json=dict(template_id=template_ids[0],name="丙",discussion_config={}))
        assert bad.status_code==422
    assert api_client.app.state.scene_runner._model.call_count==0


def test_upgrade_copy_preserves_all_columns_and_007_rollback(tmp_path, monkeypatch):
    from test_m04_runner import build_env, CLOCK
    migrations=migrator.discover_migrations()[:7]
    assert migrations[-1].version==7
    old=Database(tmp_path/"old006.db")
    with monkeypatch.context() as patch:
        patch.setattr(migrator,"discover_migrations",lambda:migrations[:6])
        assert old.migrate()==[1,2,3,4,5,6]
    # Populate schema 006 from controlled current rows using its original columns.
    seed=Database(tmp_path/"seed.db"); seed.migrate(); env=build_env(seed)
    with seed.connection() as source, old.transaction() as target:
        for table in ["agent_templates","scenes","scene_agents"]:
            cols=[r["name"] for r in target.execute(f"PRAGMA table_info({table})")]; names=','.join(cols)
            for row in source.execute(f"SELECT {names} FROM {table}"):
                target.execute(f"INSERT INTO {table} ({names}) VALUES ({','.join('?' for _ in cols)})",tuple(row))
        target.execute("INSERT INTO scene_turns (action_id,turn_id,attempt_id,scene_id,actor_id,input_cursor_seq,prompt_template_id,status,created_at,request_snapshot_json) VALUES ('old-a','old-t','old-r',?,?,0,'role_action@pc.1','UNKNOWN',?,?)",(env.scene_id,env.agent_ids[0],CLOCK.isoformat(),'{"old_prompt":"verbatim"}'))
    copy=Database(tmp_path/"copy.db")
    with old.connection() as src, copy.connection() as dest:
        src.backup(dest)
        tables=[r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        before={table:[dict(r) for r in src.execute(f'SELECT * FROM "{table}"')] for table in tables}
    broken=migrator.Migration(7,"dual_mode",migrations[-1].sql+"\nSELECT * FROM missing_dm_table;\n")
    with monkeypatch.context() as patch:
        patch.setattr(migrator,"discover_migrations",lambda:[*migrations[:6],broken])
        with pytest.raises(sqlite3.OperationalError): copy.migrate()
    with copy.connection() as conn:
        assert 'mode' not in [r['name'] for r in conn.execute('PRAGMA table_info(scenes)')]
        assert conn.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0]==6
    assert copy.migrate()==[7,8,9] and copy.migrate()==[]
    with copy.connection() as conn:
        for table, rows in before.items():
            after=[dict(r) for r in conn.execute(f'SELECT * FROM "{table}"'+(' WHERE version<=6' if table=='schema_migrations' else ''))]
            assert [{k:row[k] for k in original} for original,row in zip(rows,after,strict=True)]==rows
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    scene=SceneRepository(copy).get_scene(env.scene_id)
    assert scene.mode is SceneMode.SIMULATION
    assert all(t.public_profile=='' for t in TemplateRepository(copy).list_all())
    assert all(a.snapshot.public_profile=='' for a in SceneRepository(copy).list_agents(env.scene_id))
    assert env.port.call_count==0
    with old.connection() as conn:
        assert conn.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0]==6
