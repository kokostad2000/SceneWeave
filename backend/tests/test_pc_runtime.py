import sqlite3
from itertools import combinations
import pytest
from role_theater.contracts import ActionDraft, ControlCommandType, RoleCursor, EventSubmission
from role_theater.ports import MockModelPort
from test_m04_runner import build_env, CLOCK
from test_m04_api import make_preset_scene, step

async def turn(env, n):
    return await env.runner.run_command(env.scene_id, request_id=f"s{n}", command=ControlCommandType.STEP)

async def test_pc_actual_requests_silence_old_reply_relay(database):
    env = build_env(database)
    a, b, c = env.agent_ids
    env.port._script = [ActionDraft(action="PRIVATE", text="SECRET_PC_MARKER", recipient_id=b), ActionDraft(action="PASS"), ActionDraft(action="PASS")]
    for n in range(3): await turn(env, n)
    first = env.runtime.list_messages(env.scene_id)[0]
    assert env.port.calls[1].actor_id == b
    assert "SECRET_PC_MARKER" in env.port.calls[1].prompt
    third = env.port.calls[2]
    import json
    saved = json.loads(env.runtime.list_turns(env.scene_id)[2]["request_snapshot_json"])
    assert saved == third.model_dump(mode="json")
    assert third.actor_id == c
    assert "SECRET_PC_MARKER" not in third.model_dump_json() and first.message_id not in third.model_dump_json()
    await turn(env, 3)
    assert env.port.call_count == 3  # all opportunities consumed, no refusal notification
    await env.runner.inject_event(env.scene_id, request_id="wake", submission=EventSubmission(body="新机会", visibility="TARGETED", target_agent_id=b))
    env.port._script = [ActionDraft(action="PRIVATE", text="旧私聊回复", recipient_id=a, reply_to_message_id=first.message_id)]
    await turn(env, 4)
    messages = env.runtime.list_messages(env.scene_id)
    assert messages[1].conversation_id == first.conversation_id
    assert env.runtime.action_records(env.scene_id)[-1].draft.recipient_id == a
    assert len(env.runtime.conversations(env.scene_id)) == 1
    assert env.runtime.conversations(env.scene_id, viewer_id=c) == []

@pytest.mark.parametrize("count,expected", [(2,1),(3,3),(5,10),(8,28)])
async def test_pc_all_pairs_reverse_scene_isolation(database, count, expected):
    env = build_env(database, agent_count=count)
    n = 0
    for a,b in combinations(env.agent_ids,2):
        for actor, recipient in [(a,b),(b,a)]:
            # Grant only sender an explicit new event, ensuring deterministic choice.
            for agent in env.agent_ids:
                env.runtime.upsert_cursor(RoleCursor(scene_id=env.scene_id, agent_id=agent, processed_seq=env.runtime.last_seq(env.scene_id), startup_opportunity_consumed=True))
            await env.runner.inject_event(env.scene_id, request_id=f"e{n}", submission=EventSubmission(body="opportunity", visibility="TARGETED", target_agent_id=actor))
            env.port._script = [ActionDraft(action="PRIVATE", text="pair", recipient_id=recipient)]
            await turn(env,n); n += 1
    convs = env.runtime.conversations(env.scene_id)
    assert len(convs) == expected and all(c.message_count == 2 for c in convs)
    assert all(len(env.runtime.conversations(env.scene_id, viewer_id=a)) == count-1 for a in env.agent_ids)
    assert env.runtime.conversation_id("other-scene", env.agent_ids[0], env.agent_ids[1]) != convs[-1].conversation_id
    assert env.runtime.budget_used(env.scene_id)["role_requests_used"] == expected*2

@pytest.mark.parametrize("table,operation", [("messages","INSERT"),("scene_turns","UPDATE"),("role_cursors","INSERT"),("scene_scheduler_state","INSERT")])
async def test_pc_private_atomic_fault(database, table, operation):
    env = build_env(database, script=[ActionDraft(action="PRIVATE", text="secret", recipient_id="agt-2")])
    with database.transaction() as conn:
        condition = " WHEN NEW.status = 'SUCCEEDED'" if table == "scene_turns" else ""
        conn.execute(f"CREATE TRIGGER pc_fault BEFORE {operation} ON {table}{condition} BEGIN SELECT RAISE(ABORT, 'pc fault'); END")
    with pytest.raises(sqlite3.IntegrityError, match="pc fault"):
        await turn(env,0)
    assert env.runtime.list_messages(env.scene_id) == [] and env.runtime.conversations(env.scene_id) == []
    assert env.runtime.list_cursors(env.scene_id) == [] and env.runtime.last_seq(env.scene_id) == 0
    assert env.runtime.requested_priority_streak(env.scene_id) == 0
    assert env.runtime.list_turns(env.scene_id)[0]["status"] == "PENDING"
    assert env.runtime.budget_used(env.scene_id)["role_requests_used"] == 1
    with database.transaction() as conn:
        conn.execute("DROP TRIGGER pc_fault")
    env.runner.recover_after_restart()
    assert env.runtime.list_turns(env.scene_id)[0]["status"] == "UNKNOWN"
    assert env.port.call_count == 1


def test_pc_http_viewpoint_menu_queries_no_requests(api_client):
    scene_id = make_preset_scene(api_client)
    app = api_client.app
    a,b,c = [x["agent_id"] for x in api_client.get(f"/api/scenes/{scene_id}").json()["agents"]]
    app.state.scene_runner._model._script = [ActionDraft(action="PRIVATE", text="HTTP_PRIVATE", recipient_id=b), ActionDraft(action="PRIVATE", text="reply", recipient_id=a), ActionDraft(action="PASS")]
    step(api_client,scene_id,"x1"); step(api_client,scene_id,"x2")
    timeline = api_client.get(f"/api/scenes/{scene_id}/timeline").json()
    conv = timeline["conversations"][0]
    assert conv["message_count"] == 2
    for route in [f"agents/{c}/viewpoint", f"timeline?viewer_id={c}", f"conversations?viewer_id={c}", f"agents/status?viewer_id={c}"]:
        response = api_client.get(f"/api/scenes/{scene_id}/{route}")
        assert response.status_code == 200
        assert "HTTP_PRIVATE" not in response.text and conv["conversation_id"] not in response.text
    assert api_client.get(f"/api/scenes/{scene_id}/timeline?viewer_id={c}&conversation_id={conv['conversation_id']}").status_code == 404
    assert api_client.get(f"/api/scenes/{scene_id}/conversations?viewer_id=outside").status_code == 404
    # 可见事件的编号也不能暴露中间两条隐藏私聊留下的全局序号间隔。
    response = api_client.post(f"/api/scenes/{scene_id}/events", json={
        "request_id": "visible-event", "body": "public update", "visibility": "ALL"})
    assert response.status_code == 200
    visible = api_client.get(f"/api/scenes/{scene_id}/timeline?viewer_id={c}").json()["entries"]
    events = api_client.get(f"/api/scenes/{scene_id}/events?viewer_id={c}").json()
    assert [item["seq"] for item in visible] == list(range(1, len(visible) + 1))
    assert events[-1]["event"]["seq"] == visible[-1]["seq"]
    assert app.state.scene_runner._model.call_count == 2


@pytest.mark.parametrize("choice", ["public", "initiate", "reply", "silence"])
async def test_pc_four_actions_same_received_snapshot(database, choice):
    env = build_env(database)
    a,b,c = env.agent_ids
    env.port._script = [ActionDraft(action="PRIVATE", text="secret", recipient_id=b)]
    await turn(env,0)
    original = env.runtime.list_messages(env.scene_id)[0]
    drafts = {"public": ActionDraft(action="SPEAK", text="new public relay"),
        "initiate": ActionDraft(action="PRIVATE", text="new relay", recipient_id=c),
        "reply": ActionDraft(action="PRIVATE", text="reply", recipient_id=a, reply_to_message_id=original.message_id),
        "silence": ActionDraft(action="PASS")}
    env.port._script = [drafts[choice]]
    await turn(env,1)
    assert env.runtime.action_records(env.scene_id)[1].draft == drafts[choice]
    assert env.runtime.get_cursor(env.scene_id,b).processed_seq == original.seq
    assert env.runtime.requested_priority_streak(env.scene_id) == 1
    if choice in ("initiate", "public"):
        _, third = env.runner.viewpoint(env.scene_id,c)
        assert "secret" not in third.prompt and original.message_id not in third.prompt
        assert "relay" in third.prompt


def test_pc_migration_005_failure_rolls_back(tmp_path, monkeypatch):
    from role_theater.storage import Database, migrator
    db = Database(tmp_path / "old.db")
    all_migrations = migrator.discover_migrations()
    with monkeypatch.context() as patch:
        patch.setattr(migrator, "discover_migrations", lambda: all_migrations[:4])
        assert db.migrate() == [1,2,3,4]
    broken = migrator.Migration(5, "private_chat", all_migrations[4].sql + "\nSELECT * FROM nonexistent_table;\n")
    with monkeypatch.context() as patch:
        patch.setattr(migrator, "discover_migrations", lambda: [*all_migrations[:4],broken])
        with pytest.raises(sqlite3.OperationalError): db.migrate()
    with db.connection() as conn:
        assert "visibility" not in [r["name"] for r in conn.execute("PRAGMA table_info(messages)")]
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 4
    assert db.migrate() == [5,6,7,8,9] and db.migrate() == []


def test_pc_004_backup_upgrade_preserves_every_existing_column(tmp_path, monkeypatch):
    from role_theater.storage import Database, migrator
    from role_theater.contracts import TurnStatus

    old = Database(tmp_path / "old004.db")
    migrations = migrator.discover_migrations()
    with monkeypatch.context() as patch:
        patch.setattr(migrator, "discover_migrations", lambda: migrations[:4])
        assert old.migrate() == [1, 2, 3, 4]
    # Populate historical schema using only its original columns.
    seed = Database(tmp_path / "seed-current.db")
    seed.migrate()
    env = build_env(seed, max_role_requests=24)
    with seed.connection() as source, old.transaction() as target:
        for table in ["agent_templates", "scenes", "scene_agents"]:
            columns = [row["name"] for row in target.execute(f"PRAGMA table_info({table})")]
            names = ",".join(columns)
            for row in source.execute(f"SELECT {names} FROM {table}"):
                target.execute(f"INSERT INTO {table} ({names}) VALUES ({','.join('?' for _ in columns)})", tuple(row))
    from role_theater.storage import RuntimeRepository
    env.runtime = RuntimeRepository(old)
    env.runtime.insert_turn(action_id="old-action", turn_id="old-turn", attempt_id="old-attempt",
        scene_id=env.scene_id, actor_id=env.agent_ids[0], input_cursor_seq=0,
        prompt_template_id="role_action@m02.1", created_at=CLOCK)
    env.runtime.finish_turn("old-attempt", status=TurnStatus.SUCCEEDED, finished_at=CLOCK,
        action="PASS", text="")
    with old.transaction() as conn:
        conn.execute("INSERT INTO role_cursors (scene_id,agent_id,processed_seq,startup_opportunity_consumed,consecutive_requested_priority) VALUES (?,?,0,1,1)",
                     (env.scene_id, env.agent_ids[0]))
    env.runtime.store_command(request_id="old-command", scene_id=env.scene_id, command="STOP",
        response_json='{"old":true}', created_at=CLOCK)
    with old.transaction() as conn:
        conn.execute("UPDATE scenes SET status='ENDED', ended_at=? WHERE scene_id=?",
            (CLOCK.isoformat(), env.scene_id))
        conn.execute("INSERT INTO scene_scheduler_state VALUES (?, 2)", (env.scene_id,))
        conn.execute("INSERT INTO messages (message_id, scene_id, seq, actor_id, text, created_at) VALUES (?, ?, 1, ?, ?, ?)",
            ("old-public", env.scene_id, env.agent_ids[0], "legacy public", CLOCK.isoformat()))
    backup = Database(tmp_path / "upgrade-copy.db")
    with old.connection() as source, backup.connection() as destination:
        source.backup(destination)
        tables = [r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        before = {table: [dict(r) for r in source.execute(f'SELECT * FROM "{table}"')] for table in tables}
    assert backup.migrate() == [5, 6, 7, 8, 9]
    assert backup.migrate() == []
    with backup.connection() as conn:
        for table, expected in before.items():
            if table == "schema_migrations":
                assert [dict(r) for r in conn.execute("SELECT * FROM schema_migrations WHERE version<=4")] == expected
            else:
                actual = [dict(r) for r in conn.execute(f'SELECT * FROM "{table}"')]
                assert len(actual) == len(expected)
                for original, upgraded in zip(expected, actual, strict=True):
                    assert {name: upgraded[name] for name in original} == original
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT visibility, recipient_id, schema_version FROM messages").fetchone()[:] == ("PUBLIC", None, 1)
        assert conn.execute("SELECT request_snapshot_json FROM scene_turns").fetchone()[0] is None
    assert env.runtime.requested_priority_streak(env.scene_id) == 2
    with old.connection() as conn:
        assert conn.execute("SELECT max_role_requests FROM scenes").fetchone()[0] == 24
    # 升级只作用于副本，原库仍是完整的 004 回退备份。
    with old.connection() as conn:
        assert conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 4


async def test_pc_request_snapshot_reservation_fault(database):
    env = build_env(database)
    with database.transaction() as conn:
        conn.execute("CREATE TRIGGER snapshot_fault BEFORE UPDATE OF request_snapshot_json ON scene_turns BEGIN SELECT RAISE(ABORT, 'snapshot fault'); END")
    with pytest.raises(sqlite3.IntegrityError, match="snapshot fault"): await turn(env,0)
    assert env.runtime.list_turns(env.scene_id) == []
    assert env.runtime.budget_used(env.scene_id)["role_requests_used"] == 0
    assert env.port.call_count == 0


@pytest.mark.parametrize("choice", ["public", "initiate", "reply", "silence"])
@pytest.mark.parametrize("control", ["PAUSE", "STOP"])
async def test_pc_four_actions_control_event_boundary(database, choice, control):
    import asyncio
    from role_theater.contracts import Message
    from test_m04_runner import GatedModelPort
    drafts = {"public": ActionDraft(action="SPEAK",text="public"),
              "initiate": ActionDraft(action="PRIVATE",text="relay",recipient_id="agt-3"),
              "reply": ActionDraft(action="PRIVATE",text="reply",recipient_id="agt-1",reply_to_message_id="old-private"),
              "silence": ActionDraft(action="PASS")}
    port = GatedModelPort(drafts[choice]); env=build_env(database,port=port)
    a,b,c=env.agent_ids
    env.runtime.insert_message(Message(message_id="old-private",scene_id=env.scene_id,seq=env.runtime.next_seq(env.scene_id),actor_id=a,
        text="old",visibility="PRIVATE",recipient_id=b,conversation_id=env.runtime.conversation_id(env.scene_id,a,b),created_at=CLOCK))
    for actor in [a,c]: env.runtime.upsert_cursor(RoleCursor(scene_id=env.scene_id,agent_id=actor,processed_seq=1,startup_opportunity_consumed=True))
    task=asyncio.create_task(turn(env,0)); await asyncio.wait_for(port.started.wait(),timeout=5)
    assert (await env.runner.inject_event(env.scene_id,request_id="late",submission=EventSubmission(body="late boundary event",visibility="TARGETED",target_agent_id=b))).event_status == "ACCEPTED"
    await env.runner.run_command(env.scene_id,request_id="control",command=ControlCommandType(control))
    port.release.set(); ack=await asyncio.wait_for(task,timeout=5)
    assert ack.run_state == ("ENDED" if control=="STOP" else "PAUSED")
    assert env.runtime.get_cursor(env.scene_id,b).processed_seq == 1
    events=env.runtime.list_events(env.scene_id)
    assert events[0].status == "EFFECTIVE" and events[0].seq > 1
    assert env.runner.call_count(env.scene_id)==1
    before=len(env.runtime.list_messages(env.scene_id))
    duplicate=await turn(env,0)
    assert duplicate.deduplicated and env.runner.call_count(env.scene_id)==1
    assert len(env.runtime.list_messages(env.scene_id))==before
