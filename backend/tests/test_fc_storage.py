"""FC-03: old rule snapshots survive migration; new scenes default to policy 2."""
import sqlite3
from datetime import UTC, datetime
import pytest
from role_theater.contracts import Budget, Scene
from role_theater.storage import Database, SceneRepository
from role_theater.storage import migrator


def test_upgrade_preserves_every_old_scene_column_and_defaults_to_legacy(tmp_path, monkeypatch):
    db = Database(tmp_path / "old.db")
    migrations = migrator.discover_migrations()
    with monkeypatch.context() as patch:
        patch.setattr(migrator, "discover_migrations", lambda: migrations[:-1])
        assert db.migrate() == list(range(1, 9))
    now = datetime.now(UTC).isoformat()
    with db.transaction() as conn:
        conn.execute("INSERT INTO scenes (scene_id,title,background,status,schema_version,max_role_requests,max_analysis_requests,created_at,mode,configuration_version) VALUES (?,?,?,?,?,?,?,?,?,?)",
                     ("old", "旧场景", "背景", "READY", 1, 12, 4, now, "simulation", 2))
        before = dict(conn.execute("SELECT * FROM scenes").fetchone())
    assert db.migrate() == [9]
    assert db.migrate() == []
    with db.connection() as conn:
        after = dict(conn.execute("SELECT * FROM scenes").fetchone())
        assert {k: after[k] for k in before} == before
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    scene = SceneRepository(db).get_scene("old")
    assert scene.chat_policy_version == 1
    assert scene.configuration_version == 2


def test_policy_persists_and_invalid_database_value_is_rejected(database):
    repo = SceneRepository(database)
    scene = Scene(scene_id="new", title="新场景", background="", budget=Budget(),
                  chat_policy_version=2, created_at=datetime.now(UTC))
    repo.insert_scene_with_agents(scene, [])
    assert SceneRepository(Database(database.path)).get_scene("new").chat_policy_version == 2
    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction() as conn:
            conn.execute("UPDATE scenes SET chat_policy_version = 3")
    assert repo.get_scene("new").chat_policy_version == 2


def test_new_preset_default_and_explicit_legacy_service(services):
    _, scenes = services
    first = scenes.create_preset()
    assert first.scene.chat_policy_version == 2
    second = scenes.create_preset(chat_policy_version=1)
    assert second.scene.chat_policy_version == 1


def test_new_api_default_and_explicit_legacy(api_client):
    for data, expected in [({}, 2), ({"chat_policy_version": 1}, 1)]:
        response = api_client.post("/api/scenes/preset", json=data)
        assert response.status_code == 201
        assert response.json()["scene"]["chat_policy_version"] == expected


def test_failed_policy_migration_rolls_back_all_schema_changes(tmp_path, monkeypatch):
    migrations = migrator.discover_migrations()
    db = Database(tmp_path / "rollback.db")
    with monkeypatch.context() as patch:
        patch.setattr(migrator, "discover_migrations", lambda: migrations[:8])
        db.migrate()
    broken = migrator.Migration(9, "free_chat", migrations[8].sql + "\nSELECT * FROM missing_fc_table;")
    with monkeypatch.context() as patch:
        patch.setattr(migrator, "discover_migrations", lambda: [*migrations[:8], broken])
        with pytest.raises(sqlite3.OperationalError):
            db.migrate()
    with db.connection() as conn:
        assert "chat_policy_version" not in {r["name"] for r in conn.execute("PRAGMA table_info(scenes)")}
        assert "last_success_action" not in {r["name"] for r in conn.execute("PRAGMA table_info(role_cursors)")}
        assert conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 8
    assert db.migrate() == [9]
