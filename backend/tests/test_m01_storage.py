"""M01 存储与迁移（PRD 第 8 节；tasks/M01.md A6）。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from role_theater.storage import Database
from role_theater.storage.migrator import (
    MigrationChecksumError,
    apply_migrations,
    discover_migrations,
    split_statements,
)


def test_migrations_are_discovered_in_version_order() -> None:
    migrations = discover_migrations()

    assert [m.version for m in migrations] == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert [m.name for m in migrations] == ["initial", "runtime", "analysis", "scene_scheduler", "private_chat", "request_snapshot", "dual_mode", "scene_role_profile", "free_chat"]
    assert all(len(m.checksum) == 64 for m in migrations)


def test_migration_applies_once_and_is_idempotent(tmp_path: Path) -> None:
    db = Database(tmp_path / "a.db")

    assert db.migrate() == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    # 重复启动不得重复应用（PRD 5.4：重入幂等的基础）。
    assert db.migrate() == []
    assert db.migrate() == []

    with db.connection() as conn:
        rows = conn.execute(
            "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
        ).fetchall()
    assert [row["version"] for row in rows] == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert [row["name"] for row in rows] == ["initial", "runtime", "analysis", "scene_scheduler", "private_chat", "request_snapshot", "dual_mode", "scene_role_profile", "free_chat"]


def test_modified_migration_is_rejected(database: Database) -> None:
    """改写已应用的迁移必须被拒绝，而不是悄悄放过。"""

    with database.transaction() as conn:
        conn.execute("UPDATE schema_migrations SET checksum = 'tampered' WHERE version = 1")

    with pytest.raises(MigrationChecksumError, match="已被修改"):
        database.migrate()


def test_schema_uses_a_role_set_not_fixed_agent_columns(database: Database) -> None:
    """PRD 3.2：不得使用 agent1／agent2／agent3 等固定列。"""

    with database.connection() as conn:
        tables = [
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
        ]
        assert set(tables) >= {
            "agent_templates",
            "scenes",
            "scene_agents",
            "schema_migrations",
            "messages",
            "events",
            "scene_turns",
            "role_cursors",
            "scene_seq",
            "scene_budget_usage",
            "scene_commands",
            "analysis_records",
            "scene_scheduler_state",
        }

        for table in ("agent_templates", "scenes", "scene_agents"):
            columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})")]
            fixed = [c for c in columns if c.rstrip("0123456789") == "agent"]
            assert fixed == [], f"{table} 出现固定角色列：{fixed}"

        agent_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(scene_agents)")
        }

    assert {
        "agent_id",
        "scene_id",
        "name",
        "order_index",
        "source_template_id",
        "snapshot_name",
        "snapshot_persona",
        "snapshot_speech_style",
        "snapshot_initial_goal",
        "snapshot_private_background",
        "snapshot_captured_at",
        "created_at",
    } <= agent_columns


def test_scene_agent_unique_constraints_are_enforced(database: Database) -> None:
    """同一场景内名称与顺序唯一，但不同场景可以重名（PRD 3.2）。"""

    _insert_minimal_scene(database, "scn-1")

    # 同一事务内重名 → 唯一约束拦截，整个事务回滚。
    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction() as conn:
            _insert_agent(conn, "agt-1", "scn-1", "安然", 0)
            _insert_agent(conn, "agt-2", "scn-1", "安然", 1)
    with database.connection() as conn:
        assert conn.execute("SELECT COUNT(*) AS t FROM scene_agents").fetchone()["t"] == 0

    # 顺序号唯一。
    with database.transaction() as conn:
        _insert_agent(conn, "agt-3", "scn-1", "许川", 0)
    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction() as conn:
            _insert_agent(conn, "agt-4", "scn-1", "陈禾", 0)

    # 名称只需在**场景内**唯一：另一个场景可以叫同样的名字。
    _insert_minimal_scene(database, "scn-2")
    with database.transaction() as conn:
        _insert_agent(conn, "agt-5", "scn-2", "许川", 0)
    with database.connection() as conn:
        assert conn.execute("SELECT COUNT(*) AS t FROM scene_agents").fetchone()["t"] == 2


def test_foreign_keys_are_enforced_and_cascade(database: Database) -> None:
    """SQLite 默认关闭外键；我们的连接必须显式打开。"""

    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction() as conn:
            _insert_agent(conn, "agt-x", "scn-missing", "陈禾", 0)

    _insert_minimal_scene(database, "scn-cascade")
    with database.transaction() as conn:
        _insert_agent(conn, "agt-c", "scn-cascade", "陈禾", 0)
    with database.transaction() as conn:
        conn.execute("DELETE FROM scenes WHERE scene_id = 'scn-cascade'")
    with database.connection() as conn:
        remaining = conn.execute(
            "SELECT COUNT(*) AS total FROM scene_agents WHERE scene_id = 'scn-cascade'"
        ).fetchone()
    assert remaining["total"] == 0


def test_split_statements_handles_the_real_migration() -> None:
    sql = discover_migrations()[0].sql
    statements = split_statements(sql)

    # 001_initial.sql 恰好包含 6 条语句：3 张表 + 3 个索引。
    assert len(statements) == 6
    assert all(statement.strip().endswith(";") for statement in statements)
    assert sum("CREATE TABLE" in s for s in statements) == 3
    assert sum("CREATE INDEX" in s or "CREATE UNIQUE INDEX" in s for s in statements) == 3
    # 前导注释块属于其后的语句，且不会因为注释里的全角分号被切断。
    assert "PRAGMA" not in sql
    assert all("PRAGMA" not in statement for statement in statements)


def test_migrations_apply_on_a_fresh_connection(database: Database) -> None:
    """迁移可在一个全新连接上重放（体现 apply_migrations 的独立性）。"""

    with database.connection() as conn:
        assert apply_migrations(conn) == []


def _insert_minimal_scene(database: Database, scene_id: str) -> None:
    with database.transaction() as conn:
        conn.execute(
            "INSERT INTO scenes (scene_id, title, background, status, schema_version,"
            " max_role_requests, max_analysis_requests, created_at)"
            " VALUES (?, '标题', '背景', 'READY', 1, 24, 4, '2026-09-26T20:00:00+00:00')",
            (scene_id,),
        )


def _insert_agent(
    conn: sqlite3.Connection, agent_id: str, scene_id: str, name: str, order_index: int
) -> None:
    conn.execute(
        "INSERT INTO scene_agents (agent_id, scene_id, name, order_index, source_template_id,"
        " snapshot_name, snapshot_persona, snapshot_speech_style, snapshot_initial_goal,"
        " snapshot_private_background, snapshot_captured_at, created_at)"
        " VALUES (?, ?, ?, ?, 'tpl-1', ?, '', '', '', '', '2026-09-26T20:00:00+00:00',"
        " '2026-09-26T20:00:00+00:00')",
        (agent_id, scene_id, name, order_index, name),
    )
