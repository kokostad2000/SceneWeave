"""场景与本场角色数据访问（PRD 3.2、5.3）。

本场角色以**行**存储：每行一个角色，快照字段内联在 ``scene_agents`` 中，
因此不存在 ``agent1``／``agent2``／``agent3`` 之类固定列（PRD 3.2）。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from datetime import datetime

from ..contracts import AgentSnapshot, Budget, PauseReason, RunState, Scene, SceneAgent
from .database import Database

_SCENE_COLUMNS = (
    "scene_id, title, background, status, pause_reason, schema_version,"
    " max_role_requests, max_analysis_requests, budget_locked_at, created_at,"
    " started_at, ended_at"
)
_AGENT_COLUMNS = (
    "agent_id, scene_id, name, order_index, source_template_id, snapshot_name,"
    " snapshot_persona, snapshot_speech_style, snapshot_initial_goal,"
    " snapshot_private_background, snapshot_captured_at, created_at"
)


def _optional_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _to_scene(row: sqlite3.Row) -> Scene:
    return Scene(
        scene_id=row["scene_id"],
        title=row["title"],
        background=row["background"],
        status=RunState(row["status"]),
        pause_reason=PauseReason(row["pause_reason"]) if row["pause_reason"] else None,
        budget=Budget(
            max_role_requests=int(row["max_role_requests"]),
            max_analysis_requests=int(row["max_analysis_requests"]),
            locked_at=_optional_datetime(row["budget_locked_at"]),
        ),
        schema_version=int(row["schema_version"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        started_at=_optional_datetime(row["started_at"]),
        ended_at=_optional_datetime(row["ended_at"]),
    )


def _to_agent(row: sqlite3.Row) -> SceneAgent:
    return SceneAgent(
        agent_id=row["agent_id"],
        scene_id=row["scene_id"],
        name=row["name"],
        order_index=int(row["order_index"]),
        snapshot=AgentSnapshot(
            source_template_id=row["source_template_id"],
            name=row["snapshot_name"],
            persona=row["snapshot_persona"],
            speech_style=row["snapshot_speech_style"],
            initial_goal=row["snapshot_initial_goal"],
            private_background=row["snapshot_private_background"],
            captured_at=datetime.fromisoformat(row["snapshot_captured_at"]),
        ),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


class SceneRepository:
    """场景与本场角色的读写。

    并发说明（tasks/M01.md §3.6 I4）：M01 面向单用户本地部署，采用先检查后写入，
    并由 ``UNIQUE(scene_id, name)``／``UNIQUE(scene_id, order_index)`` 兜底。
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    # --- 写入 ---

    def insert_scene_with_agents(
        self,
        scene: Scene,
        agents: Sequence[SceneAgent],
        *,
        preset_key: str | None = None,
    ) -> None:
        """在同一事务内写入场景与其全部本场角色。"""

        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO scenes"
                " (scene_id, title, background, status, pause_reason, schema_version,"
                "  max_role_requests, max_analysis_requests, budget_locked_at, preset_key,"
                "  created_at, started_at, ended_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    scene.scene_id,
                    scene.title,
                    scene.background,
                    scene.status.value,
                    scene.pause_reason.value if scene.pause_reason else None,
                    scene.schema_version,
                    scene.budget.max_role_requests,
                    scene.budget.max_analysis_requests,
                    scene.budget.locked_at.isoformat() if scene.budget.locked_at else None,
                    preset_key,
                    scene.created_at.isoformat(),
                    scene.started_at.isoformat() if scene.started_at else None,
                    scene.ended_at.isoformat() if scene.ended_at else None,
                ),
            )
            for agent in agents:
                self._insert_agent(conn, agent)

    def insert_agent(self, agent: SceneAgent) -> None:
        with self._db.transaction() as conn:
            self._insert_agent(conn, agent)

    @staticmethod
    def _insert_agent(conn: sqlite3.Connection, agent: SceneAgent) -> None:
        snapshot = agent.snapshot
        conn.execute(
            "INSERT INTO scene_agents"
            " (agent_id, scene_id, name, order_index, source_template_id, snapshot_name,"
            "  snapshot_persona, snapshot_speech_style, snapshot_initial_goal,"
            "  snapshot_private_background, snapshot_captured_at, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                agent.agent_id,
                agent.scene_id,
                agent.name,
                agent.order_index,
                snapshot.source_template_id,
                snapshot.name,
                snapshot.persona,
                snapshot.speech_style,
                snapshot.initial_goal,
                snapshot.private_background,
                snapshot.captured_at.isoformat(),
                agent.created_at.isoformat(),
            ),
        )

    def rename_agent(self, scene_id: str, agent_id: str, new_name: str) -> bool:
        with self._db.transaction() as conn:
            cursor = conn.execute(
                "UPDATE scene_agents SET name = ? WHERE scene_id = ? AND agent_id = ?",
                (new_name, scene_id, agent_id),
            )
        return cursor.rowcount > 0

    def delete_agent(self, scene_id: str, agent_id: str) -> bool:
        with self._db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM scene_agents WHERE scene_id = ? AND agent_id = ?",
                (scene_id, agent_id),
            )
        return cursor.rowcount > 0

    def lock_scene(self, scene_id: str, locked_at: datetime) -> bool:
        """锁定预算与人物设定（由 M04 在首次角色请求开始时调用）。"""

        with self._db.transaction() as conn:
            cursor = conn.execute(
                "UPDATE scenes SET budget_locked_at = ?"
                " WHERE scene_id = ? AND budget_locked_at IS NULL",
                (locked_at.isoformat(), scene_id),
            )
        return cursor.rowcount > 0

    # --- 读取 ---

    def get_scene(self, scene_id: str) -> Scene | None:
        with self._db.connection() as conn:
            row = conn.execute(
                f"SELECT {_SCENE_COLUMNS} FROM scenes WHERE scene_id = ?", (scene_id,)
            ).fetchone()
        return _to_scene(row) if row is not None else None

    def list_scenes(self) -> list[Scene]:
        with self._db.connection() as conn:
            rows = conn.execute(
                f"SELECT {_SCENE_COLUMNS} FROM scenes ORDER BY created_at DESC, scene_id ASC"
            ).fetchall()
        return [_to_scene(row) for row in rows]

    def list_agents(self, scene_id: str) -> list[SceneAgent]:
        with self._db.connection() as conn:
            rows = conn.execute(
                f"SELECT {_AGENT_COLUMNS} FROM scene_agents"
                " WHERE scene_id = ? ORDER BY order_index ASC",
                (scene_id,),
            ).fetchall()
        return [_to_agent(row) for row in rows]

    def get_agent(self, scene_id: str, agent_id: str) -> SceneAgent | None:
        with self._db.connection() as conn:
            row = conn.execute(
                f"SELECT {_AGENT_COLUMNS} FROM scene_agents WHERE scene_id = ? AND agent_id = ?",
                (scene_id, agent_id),
            ).fetchone()
        return _to_agent(row) if row is not None else None

    def find_agent_by_name(self, scene_id: str, name: str) -> SceneAgent | None:
        with self._db.connection() as conn:
            row = conn.execute(
                f"SELECT {_AGENT_COLUMNS} FROM scene_agents WHERE scene_id = ? AND name = ?",
                (scene_id, name),
            ).fetchone()
        return _to_agent(row) if row is not None else None

    def count_agents(self, scene_id: str) -> int:
        with self._db.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total FROM scene_agents WHERE scene_id = ?", (scene_id,)
            ).fetchone()
        return int(row["total"])

    def agent_counts(self) -> dict[str, int]:
        """一次查询取回全部场景的角色数，避免列表接口 N+1 查询。"""

        with self._db.connection() as conn:
            rows = conn.execute(
                "SELECT scene_id, COUNT(*) AS total FROM scene_agents GROUP BY scene_id"
            ).fetchall()
        return {str(row["scene_id"]): int(row["total"]) for row in rows}

    def next_order_index(self, scene_id: str) -> int:
        with self._db.connection() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(order_index), -1) AS last FROM scene_agents WHERE scene_id = ?",
                (scene_id,),
            ).fetchone()
        return int(row["last"]) + 1
