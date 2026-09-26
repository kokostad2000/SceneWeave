"""分析记录的数据访问（PRD 6.2、5.3）。

记录按 ``scene_id``／``agent_id`` 隔离；**没有**画像表——`persist_profile` 强制
关闭，本项目不写任何画像。
"""

from __future__ import annotations

import json
from datetime import datetime

from ..contracts import AnalysisReport, AnalysisStatus
from .database import Database


class AnalysisRepository:
    """`analysis_records` 的读写。"""

    def __init__(self, db: Database) -> None:
        self._db = db

    def insert(
        self,
        *,
        analysis_id: str,
        scene_id: str,
        agent_id: str,
        report: AnalysisReport,
        materials: list[dict],
        material_seqs: list[int],
        behavior_description: str,
        context: str,
        created_at: datetime,
        error: str | None = None,
    ) -> None:
        usage = report.usage
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO analysis_records (analysis_id, scene_id, agent_id, status,"
                " materials_json, material_seqs_json, behavior_description, context,"
                " report_json, provider_attempts, degradation_flags, input_tokens,"
                " output_tokens, cached_tokens, error, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    analysis_id,
                    scene_id,
                    agent_id,
                    report.status.value,
                    json.dumps(materials, ensure_ascii=False),
                    json.dumps(material_seqs),
                    behavior_description,
                    context,
                    report.model_dump_json(),
                    report.provider_attempts,
                    json.dumps(report.degradation_flags, ensure_ascii=False),
                    usage.input_tokens,
                    usage.output_tokens,
                    usage.cached_tokens,
                    error or report.error,
                    created_at.isoformat(),
                ),
            )

    def list_for_scene(self, scene_id: str, *, agent_id: str | None = None) -> list[dict]:
        query = (
            "SELECT analysis_id, scene_id, agent_id, status, materials_json,"
            " material_seqs_json, behavior_description, context, report_json,"
            " provider_attempts, degradation_flags, input_tokens, output_tokens,"
            " cached_tokens, error, created_at FROM analysis_records WHERE scene_id = ?"
        )
        params: list[object] = [scene_id]
        if agent_id is not None:
            query += " AND agent_id = ?"
            params.append(agent_id)
        query += " ORDER BY created_at ASC, analysis_id ASC"
        with self._db.connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_record(row) for row in rows]

    def get(self, analysis_id: str) -> dict | None:
        with self._db.connection() as conn:
            row = conn.execute(
                "SELECT analysis_id, scene_id, agent_id, status, materials_json,"
                " material_seqs_json, behavior_description, context, report_json,"
                " provider_attempts, degradation_flags, input_tokens, output_tokens,"
                " cached_tokens, error, created_at FROM analysis_records"
                " WHERE analysis_id = ?",
                (analysis_id,),
            ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def count_operations(self, scene_id: str) -> int:
        """用户可见的**分析操作数**（含被本地规则拦截的记录）。"""

        with self._db.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total FROM analysis_records WHERE scene_id = ?",
                (scene_id,),
            ).fetchone()
        return int(row["total"])

    @staticmethod
    def _row_to_record(row) -> dict:
        report = AnalysisReport.model_validate_json(row["report_json"])
        return {
            "analysis_id": row["analysis_id"],
            "scene_id": row["scene_id"],
            "agent_id": row["agent_id"],
            "status": AnalysisStatus(row["status"]),
            "materials": json.loads(row["materials_json"]),
            "material_seqs": json.loads(row["material_seqs_json"]),
            "behavior_description": row["behavior_description"],
            "context": row["context"],
            "report": report,
            "provider_attempts": int(row["provider_attempts"]),
            "degradation_flags": json.loads(row["degradation_flags"]),
            "error": row["error"],
            "created_at": datetime.fromisoformat(row["created_at"]),
        }


__all__ = ["AnalysisRepository"]
