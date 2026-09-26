"""角色模板数据访问（PRD 3.2）。"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from ..contracts import AgentTemplate
from .database import Database

_COLUMNS = (
    "template_id, name, persona, speech_style, initial_goal, private_background,"
    " is_preset, created_at, updated_at"
)


def _to_model(row: sqlite3.Row) -> AgentTemplate:
    return AgentTemplate(
        template_id=row["template_id"],
        name=row["name"],
        persona=row["persona"],
        speech_style=row["speech_style"],
        initial_goal=row["initial_goal"],
        private_background=row["private_background"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


class TemplateRepository:
    """模板的读写。

    名称唯一由数据库索引 ``idx_agent_templates_name`` 兜底；服务层先做检查
    以给出明确的 409，而不是依赖底层异常。
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    def list_all(self) -> list[AgentTemplate]:
        with self._db.connection() as conn:
            rows = conn.execute(
                f"SELECT {_COLUMNS} FROM agent_templates ORDER BY name ASC"
            ).fetchall()
        return [_to_model(row) for row in rows]

    def get(self, template_id: str) -> AgentTemplate | None:
        with self._db.connection() as conn:
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM agent_templates WHERE template_id = ?",
                (template_id,),
            ).fetchone()
        return _to_model(row) if row is not None else None

    def find_by_name(self, name: str) -> AgentTemplate | None:
        with self._db.connection() as conn:
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM agent_templates WHERE name = ?",
                (name,),
            ).fetchone()
        return _to_model(row) if row is not None else None

    def insert(self, template: AgentTemplate, *, is_preset: bool = False) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO agent_templates"
                " (template_id, name, persona, speech_style, initial_goal, private_background,"
                "  is_preset, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    template.template_id,
                    template.name,
                    template.persona,
                    template.speech_style,
                    template.initial_goal,
                    template.private_background,
                    1 if is_preset else 0,
                    template.created_at.isoformat(),
                    template.updated_at.isoformat(),
                ),
            )

    def update(self, template: AgentTemplate) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE agent_templates"
                " SET name = ?, persona = ?, speech_style = ?, initial_goal = ?,"
                "     private_background = ?, updated_at = ?"
                " WHERE template_id = ?",
                (
                    template.name,
                    template.persona,
                    template.speech_style,
                    template.initial_goal,
                    template.private_background,
                    template.updated_at.isoformat(),
                    template.template_id,
                ),
            )

    def delete(self, template_id: str) -> bool:
        with self._db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM agent_templates WHERE template_id = ?", (template_id,)
            )
        return cursor.rowcount > 0

    def count(self) -> int:
        with self._db.connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS total FROM agent_templates").fetchone()
        return int(row["total"])
