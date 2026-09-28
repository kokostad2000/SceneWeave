"""运行时数据访问：事件、消息、行动、游标、预算与命令幂等（PRD 4.3、5.1～5.4）。

所有写操作都是**短事务**：模型网络等待期间不持有任何 SQLite 写事务（PRD 5.4）。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from datetime import datetime

from ..contracts import (
    ActionRecord,
    ActionType,
    Event,
    EventStatus,
    EventVisibility,
    Message,
    ModelActionResponse,
    PauseReason,
    RoleCursor,
    RunState,
    TurnStatus,
    Usage,
)
from .database import Database

#: 派发后、结果落盘前的在途状态（存储层概念，不属于对外 TurnStatus 枚举）。
PENDING_TURN_STATUS = "PENDING"

_EVENT_COLUMNS = (
    "event_id, scene_id, seq, body, visibility, target_agent_id, status,"
    " schema_version, accepted_at, effective_at"
)
_TURN_COLUMNS = (
    "action_id, turn_id, attempt_id, scene_id, actor_id, status, action, text,"
    " reply_to_message_id, requested_speaker_id, message_id, input_cursor_seq,"
    " prompt_template_id, requested_model, returned_model, provider_request_id,"
    " input_tokens, output_tokens, cached_tokens, usage_unknown, failure_kind,"
    " failure_detail, sent, budget_consumed, latency_ms, created_at, finished_at"
)


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _to_event(row: sqlite3.Row) -> Event:
    return Event(
        event_id=row["event_id"],
        scene_id=row["scene_id"],
        seq=int(row["seq"]) if row["seq"] is not None else None,
        body=row["body"],
        visibility=EventVisibility(row["visibility"]),
        target_agent_id=row["target_agent_id"],
        status=EventStatus(row["status"]),
        schema_version=int(row["schema_version"]),
        accepted_at=datetime.fromisoformat(row["accepted_at"]),
        effective_at=_dt(row["effective_at"]),
    )


def _to_message(row: sqlite3.Row) -> Message:
    return Message(
        message_id=row["message_id"],
        scene_id=row["scene_id"],
        seq=int(row["seq"]),
        actor_id=row["actor_id"],
        text=row["text"],
        reply_to_message_id=row["reply_to_message_id"],
        requested_speaker_id=row["requested_speaker_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


class RuntimeRepository:
    """运行时表的数据访问。"""

    def __init__(self, db: Database) -> None:
        self._db = db

    # --- 序列 ---

    def next_seq(self, scene_id: str) -> int:
        """在同一事务内原子分配下一个 ``seq``（消息与事件共享序列）。"""

        with self._db.transaction() as conn:
            return self._next_seq(conn, scene_id)

    @staticmethod
    def _next_seq(conn: sqlite3.Connection, scene_id: str) -> int:
        conn.execute(
            "INSERT INTO scene_seq (scene_id, last_seq) VALUES (?, 0)"
            " ON CONFLICT (scene_id) DO NOTHING", (scene_id,)
        )
        conn.execute("UPDATE scene_seq SET last_seq = last_seq + 1 WHERE scene_id = ?", (scene_id,))
        row = conn.execute("SELECT last_seq FROM scene_seq WHERE scene_id = ?", (scene_id,)).fetchone()
        return int(row["last_seq"])

    def last_seq(self, scene_id: str) -> int:
        with self._db.connection() as conn:
            row = conn.execute(
                "SELECT last_seq FROM scene_seq WHERE scene_id = ?", (scene_id,)
            ).fetchone()
        return int(row["last_seq"]) if row is not None else 0

    # --- 场景状态 ---

    def set_scene_state(
        self,
        scene_id: str,
        *,
        status: RunState,
        pause_reason: PauseReason | None = None,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
    ) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE scenes SET status = ?, pause_reason = ?,"
                " started_at = COALESCE(?, started_at), ended_at = COALESCE(?, ended_at)"
                " WHERE scene_id = ?",
                (
                    status.value,
                    pause_reason.value if pause_reason else None,
                    started_at.isoformat() if started_at else None,
                    ended_at.isoformat() if ended_at else None,
                    scene_id,
                ),
            )

    # --- 事件 ---

    def insert_event(self, event: Event, *, accepted_order: int) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO events (event_id, scene_id, seq, body, visibility, target_agent_id,"
                " status, schema_version, accepted_order, accepted_at, effective_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event.event_id,
                    event.scene_id,
                    event.seq,
                    event.body,
                    event.visibility.value,
                    event.target_agent_id,
                    event.status.value,
                    event.schema_version,
                    accepted_order,
                    event.accepted_at.isoformat(),
                    event.effective_at.isoformat() if event.effective_at else None,
                ),
            )

    def next_accepted_order(self, scene_id: str) -> int:
        with self._db.connection() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(accepted_order), 0) AS last FROM events WHERE scene_id = ?",
                (scene_id,),
            ).fetchone()
        return int(row["last"]) + 1

    def list_events(self, scene_id: str, *, status: EventStatus | None = None) -> list[Event]:
        query = f"SELECT {_EVENT_COLUMNS} FROM events WHERE scene_id = ?"
        params: list[object] = [scene_id]
        if status is not None:
            query += " AND status = ?"
            params.append(status.value)
        query += " ORDER BY accepted_order ASC, seq ASC"
        with self._db.connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_to_event(row) for row in rows]

    def list_pending_events(self, scene_id: str) -> list[Event]:
        return self.list_events(scene_id, status=EventStatus.ACCEPTED)

    def mark_event_effective(self, event_id: str, effective_at: datetime, seq: int) -> None:
        """生效时分配序号：时间线顺序 = 生效顺序（tasks/M04.md §3.7 I6）。"""

        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE events SET status = 'EFFECTIVE', effective_at = ?, seq = ?"
                " WHERE event_id = ? AND status = 'ACCEPTED' AND seq IS NULL",
                (effective_at.isoformat(), seq, event_id),
            )

    # --- 消息 ---

    def insert_message(self, message: Message) -> None:
        with self._db.transaction() as conn:
            self._insert_message(conn, message)

    @staticmethod
    def _insert_message(conn: sqlite3.Connection, message: Message) -> None:
        conn.execute(
            "INSERT INTO messages (message_id, scene_id, seq, actor_id, text,"
            " reply_to_message_id, requested_speaker_id, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                message.message_id,
                message.scene_id,
                message.seq,
                message.actor_id,
                message.text,
                message.reply_to_message_id,
                message.requested_speaker_id,
                message.created_at.isoformat(),
            ),
        )

    def list_messages(self, scene_id: str) -> list[Message]:
        with self._db.connection() as conn:
            rows = conn.execute(
                "SELECT message_id, scene_id, seq, actor_id, text, reply_to_message_id,"
                " requested_speaker_id, created_at FROM messages"
                " WHERE scene_id = ? ORDER BY seq ASC",
                (scene_id,),
            ).fetchall()
        return [_to_message(row) for row in rows]

    def get_message(self, scene_id: str, message_id: str) -> Message | None:
        with self._db.connection() as conn:
            row = conn.execute(
                "SELECT message_id, scene_id, seq, actor_id, text, reply_to_message_id,"
                " requested_speaker_id, created_at FROM messages"
                " WHERE scene_id = ? AND message_id = ?",
                (scene_id, message_id),
            ).fetchone()
        return _to_message(row) if row is not None else None

    # --- 行动 ---

    def insert_turn(
        self,
        *,
        action_id: str,
        turn_id: str,
        attempt_id: str,
        scene_id: str,
        actor_id: str,
        input_cursor_seq: int,
        prompt_template_id: str,
        created_at: datetime,
        budget_consumed: bool = True,
    ) -> None:
        """写入 ``PENDING`` 行动：同时占用预算并标记在途（tasks/M04.md §3.7 I2）。"""

        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO scene_turns (action_id, turn_id, attempt_id, scene_id, actor_id,"
                " status, input_cursor_seq, prompt_template_id, created_at,"
                " budget_consumed, sent, usage_unknown)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1)",
                (
                    action_id,
                    turn_id,
                    attempt_id,
                    scene_id,
                    actor_id,
                    PENDING_TURN_STATUS,
                    input_cursor_seq,
                    prompt_template_id,
                    created_at.isoformat(),
                    1 if budget_consumed else 0,
                ),
            )
            if budget_consumed:
                self._bump_budget(conn, scene_id, role_requests=1)

    def finish_turn(
        self,
        attempt_id: str,
        *,
        status: TurnStatus,
        finished_at: datetime,
        action: str | None = None,
        text: str | None = None,
        reply_to_message_id: str | None = None,
        requested_speaker_id: str | None = None,
        message_id: str | None = None,
        requested_model: str | None = None,
        returned_model: str | None = None,
        provider_request_id: str | None = None,
        usage: Usage | None = None,
        failure_kind: str | None = None,
        failure_detail: str | None = None,
        sent: bool = True,
        budget_consumed: bool = True,
        latency_ms: int | None = None,
    ) -> None:
        with self._db.transaction() as conn:
            if not budget_consumed:
                turn = conn.execute(
                    "SELECT scene_id, budget_consumed FROM scene_turns WHERE attempt_id = ?",
                    (attempt_id,),
                ).fetchone()
                if turn is not None and turn["budget_consumed"]:
                    self._refund_budget(conn, attempt_id, turn["scene_id"])
            self._finish_turn(
                conn, attempt_id,
                status=status,
                finished_at=finished_at,
                action=action,
                text=text,
                reply_to_message_id=reply_to_message_id,
                requested_speaker_id=requested_speaker_id,
                message_id=message_id,
                requested_model=requested_model,
                returned_model=returned_model,
                provider_request_id=provider_request_id,
                usage=usage,
                failure_kind=failure_kind,
                failure_detail=failure_detail,
                sent=sent,
                budget_consumed=budget_consumed,
                latency_ms=latency_ms,
            )

    @staticmethod
    def _finish_turn(
        conn: sqlite3.Connection,
        attempt_id: str,
        *,
        status: TurnStatus,
        finished_at: datetime,
        action: str | None = None,
        text: str | None = None,
        reply_to_message_id: str | None = None,
        requested_speaker_id: str | None = None,
        message_id: str | None = None,
        requested_model: str | None = None,
        returned_model: str | None = None,
        provider_request_id: str | None = None,
        usage: Usage | None = None,
        failure_kind: str | None = None,
        failure_detail: str | None = None,
        sent: bool = True,
        budget_consumed: bool = True,
        latency_ms: int | None = None,
    ) -> None:
        usage = usage or Usage()
        conn.execute(
            "UPDATE scene_turns SET status = ?, action = ?, text = ?,"
            " reply_to_message_id = ?, requested_speaker_id = ?, message_id = ?,"
            " requested_model = ?, returned_model = ?, provider_request_id = ?,"
            " input_tokens = ?, output_tokens = ?, cached_tokens = ?, usage_unknown = ?,"
            " failure_kind = ?, failure_detail = ?, sent = ?, budget_consumed = ?,"
            " latency_ms = ?, finished_at = ?"
            " WHERE attempt_id = ?",
            (
                status.value,
                action,
                text,
                reply_to_message_id,
                requested_speaker_id,
                message_id,
                requested_model,
                returned_model,
                provider_request_id,
                usage.input_tokens,
                usage.output_tokens,
                usage.cached_tokens,
                1 if usage.is_unknown else 0,
                failure_kind,
                failure_detail,
                1 if sent else 0,
                1 if budget_consumed else 0,
                latency_ms,
                finished_at.isoformat(),
                attempt_id,
            ),
        )

    def commit_success(
        self,
        attempt_id: str,
        *,
        response: ModelActionResponse,
        cursor: RoleCursor,
        message_id: str | None,
        created_at: datetime,
        finished_at: datetime,
        requested_priority: bool,
    ) -> None:
        """一次成功行动的所有事实同事务提交；SPEAK 与 PASS 使用相同边界。"""
        draft = response.draft
        if not response.ok or draft is None:
            raise ValueError("成功提交需要有效的行动结果")
        if (draft.action is ActionType.SPEAK) != (message_id is not None):
            raise ValueError("SPEAK 必须有消息 ID，PASS 不得有消息 ID")

        with self._db.transaction() as conn:
            turn = conn.execute(
                "SELECT status, scene_id, actor_id FROM scene_turns WHERE attempt_id = ?",
                (attempt_id,),
            ).fetchone()
            if turn is None or turn["status"] != PENDING_TURN_STATUS:
                raise ValueError("行动不存在或已完成，不能重复提交")
            if (turn["scene_id"], turn["actor_id"]) != (cursor.scene_id, cursor.agent_id):
                raise ValueError("行动与角色游标不匹配")

            if draft.action is ActionType.SPEAK:
                self._insert_message(
                    conn,
                    Message(
                        message_id=message_id,
                        scene_id=cursor.scene_id,
                        seq=self._next_seq(conn, cursor.scene_id),
                        actor_id=cursor.agent_id,
                        text=draft.text,
                        reply_to_message_id=draft.reply_to_message_id,
                        requested_speaker_id=draft.requested_speaker_id,
                        created_at=created_at,
                    ),
                )
            self._finish_turn(
                conn, attempt_id,
                status=TurnStatus.SUCCEEDED,
                finished_at=finished_at,
                action=draft.action.value,
                text=draft.text,
                reply_to_message_id=draft.reply_to_message_id,
                requested_speaker_id=draft.requested_speaker_id,
                message_id=message_id,
                requested_model=response.requested_model,
                returned_model=response.returned_model,
                provider_request_id=response.provider_request_id,
                usage=response.usage,
                sent=response.sent,
                latency_ms=response.latency_ms,
            )
            # 兼容已有 RoleCursor 契约中的旧字段；调度不再读取角色个人计数。
            self._upsert_cursor(conn, cursor.model_copy(update={"consecutive_requested_priority": 0}))
            conn.execute(
                "INSERT INTO scene_scheduler_state (scene_id, consecutive_requested_priority)"
                " VALUES (?, ?) ON CONFLICT (scene_id) DO UPDATE SET"
                " consecutive_requested_priority = CASE WHEN ? THEN"
                " MIN(scene_scheduler_state.consecutive_requested_priority + 1, 2) ELSE 0 END",
                (cursor.scene_id, int(requested_priority), int(requested_priority)),
            )

    def requested_priority_streak(self, scene_id: str) -> int:
        """场景连续成功点名次数；普通轮转成功后清零，重启后仍可读取。"""
        with self._db.connection() as conn:
            row = conn.execute(
                "SELECT consecutive_requested_priority FROM scene_scheduler_state WHERE scene_id = ?",
                (scene_id,),
            ).fetchone()
        return int(row["consecutive_requested_priority"]) if row is not None else 0

    def list_turns(self, scene_id: str) -> list[dict]:
        with self._db.connection() as conn:
            rows = conn.execute(
                f"SELECT {_TURN_COLUMNS} FROM scene_turns WHERE scene_id = ?"
                " ORDER BY created_at ASC, attempt_id ASC",
                (scene_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_turn(self, attempt_id: str) -> dict | None:
        with self._db.connection() as conn:
            row = conn.execute(
                f"SELECT {_TURN_COLUMNS} FROM scene_turns WHERE attempt_id = ?", (attempt_id,)
            ).fetchone()
        return dict(row) if row is not None else None

    def count_role_requests(self, scene_id: str) -> int:
        with self._db.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total FROM scene_turns"
                " WHERE scene_id = ? AND budget_consumed = 1",
                (scene_id,),
            ).fetchone()
        return int(row["total"])

    def refund_budget(self, attempt_id: str, scene_id: str) -> None:
        """未派发的调用不占用预算（PRD 5.3）。"""
        with self._db.transaction() as conn:
            self._refund_budget(conn, attempt_id, scene_id)

    @staticmethod
    def _refund_budget(conn: sqlite3.Connection, attempt_id: str, scene_id: str) -> None:
        conn.execute(
            "UPDATE scene_turns SET budget_consumed = 0 WHERE attempt_id = ?",
            (attempt_id,),
        )
        conn.execute(
            "UPDATE scene_budget_usage SET role_requests_used ="
            " MAX(role_requests_used - 1, 0) WHERE scene_id = ?",
            (scene_id,),
        )

    def mark_pending_turns_unknown(self) -> list[str]:
        """进程重启：把残留 `PENDING` 标记 `UNKNOWN`，返回受影响场景。

        PRD 5.4：不自动恢复付费请求，只标记并暂停。
        """

        with self._db.connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT scene_id FROM scene_turns WHERE status = ?",
                (PENDING_TURN_STATUS,),
            ).fetchall()
        scene_ids = [str(row["scene_id"]) for row in rows]
        if not scene_ids:
            return []
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE scene_turns SET status = 'UNKNOWN',"
                " failure_kind = COALESCE(failure_kind, 'UNKNOWN_REQUEST'),"
                " failure_detail = COALESCE(failure_detail, '进程重启时该请求仍在途')"
                " WHERE status = ?",
                (PENDING_TURN_STATUS,),
            )
        return scene_ids

    # --- 游标 ---

    def upsert_cursor(self, cursor: RoleCursor) -> None:
        with self._db.transaction() as conn:
            self._upsert_cursor(conn, cursor)

    @staticmethod
    def _upsert_cursor(conn: sqlite3.Connection, cursor: RoleCursor) -> None:
        conn.execute(
            "INSERT INTO role_cursors (scene_id, agent_id, processed_seq,"
            " startup_opportunity_consumed, last_action_at, last_action_status,"
            " consecutive_requested_priority)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (scene_id, agent_id) DO UPDATE SET"
            " processed_seq = excluded.processed_seq,"
            " startup_opportunity_consumed = excluded.startup_opportunity_consumed,"
            " last_action_at = excluded.last_action_at,"
            " last_action_status = excluded.last_action_status,"
            " consecutive_requested_priority = excluded.consecutive_requested_priority",
            (
                cursor.scene_id,
                cursor.agent_id,
                cursor.processed_seq,
                1 if cursor.startup_opportunity_consumed else 0,
                cursor.last_action_at.isoformat() if cursor.last_action_at else None,
                cursor.last_action_status.value if cursor.last_action_status else None,
                cursor.consecutive_requested_priority,
            ),
        )

    def list_cursors(self, scene_id: str) -> list[RoleCursor]:
        with self._db.connection() as conn:
            rows = conn.execute(
                "SELECT scene_id, agent_id, processed_seq, startup_opportunity_consumed,"
                " last_action_at, last_action_status, consecutive_requested_priority"
                " FROM role_cursors WHERE scene_id = ? ORDER BY agent_id",
                (scene_id,),
            ).fetchall()
        return [
            RoleCursor(
                scene_id=row["scene_id"],
                agent_id=row["agent_id"],
                processed_seq=int(row["processed_seq"]),
                startup_opportunity_consumed=bool(row["startup_opportunity_consumed"]),
                last_action_at=_dt(row["last_action_at"]),
                last_action_status=(
                    TurnStatus(row["last_action_status"]) if row["last_action_status"] else None
                ),
                consecutive_requested_priority=int(row["consecutive_requested_priority"]),
            )
            for row in rows
        ]

    def get_cursor(self, scene_id: str, agent_id: str) -> RoleCursor | None:
        for cursor in self.list_cursors(scene_id):
            if cursor.agent_id == agent_id:
                return cursor
        return None

    # --- 命令幂等 ---

    def get_command(self, request_id: str) -> dict | None:
        with self._db.connection() as conn:
            row = conn.execute(
                "SELECT request_id, scene_id, command, response_json FROM scene_commands"
                " WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def store_command(
        self, *, request_id: str, scene_id: str, command: str, response_json: str, created_at: datetime
    ) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO scene_commands (request_id, scene_id, command, response_json,"
                " created_at) VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT (request_id) DO NOTHING",
                (request_id, scene_id, command, response_json, created_at.isoformat()),
            )

    # --- 预算 ---

    def budget_used(self, scene_id: str) -> dict[str, int]:
        with self._db.connection() as conn:
            row = conn.execute(
                "SELECT role_requests_used, analysis_requests_used FROM scene_budget_usage"
                " WHERE scene_id = ?",
                (scene_id,),
            ).fetchone()
        if row is None:
            return {"role_requests_used": 0, "analysis_requests_used": 0}
        return {
            "role_requests_used": int(row["role_requests_used"]),
            "analysis_requests_used": int(row["analysis_requests_used"]),
        }

    def bump_budget(self, scene_id: str, *, role_requests: int = 0, analysis_requests: int = 0) -> None:
        with self._db.transaction() as conn:
            self._bump_budget(
                conn, scene_id, role_requests=role_requests, analysis_requests=analysis_requests
            )

    @staticmethod
    def _bump_budget(
        conn: sqlite3.Connection, scene_id: str, *, role_requests: int = 0, analysis_requests: int = 0
    ) -> None:
        conn.execute(
            "INSERT INTO scene_budget_usage (scene_id, role_requests_used,"
            " analysis_requests_used) VALUES (?, ?, ?)"
            " ON CONFLICT (scene_id) DO UPDATE SET"
            " role_requests_used = role_requests_used + excluded.role_requests_used,"
            " analysis_requests_used = analysis_requests_used + excluded.analysis_requests_used",
            (scene_id, role_requests, analysis_requests),
        )

    # --- 时间线 ---

    def pending_event_count(self, scene_id: str) -> int:
        with self._db.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total FROM events WHERE scene_id = ? AND status = 'ACCEPTED'",
                (scene_id,),
            ).fetchone()
        return int(row["total"])

    def timeline(self, scene_id: str, *, since_seq: int = 0, limit: int | None = None):
        """按 ``seq`` 合并已提交的消息与事件（数据库是事实来源）。"""

        entries: list[tuple[int, str, object]] = []
        for message in self.list_messages(scene_id):
            if message.seq > since_seq:
                entries.append((message.seq, "message", message))
        for event in self.list_events(scene_id):
            # 只有已生效事件才有 seq，因此只有它们出现在时间线上（PRD 4.3）。
            if event.seq is not None and event.seq > since_seq:
                entries.append((event.seq, "event", event))
        entries.sort(key=lambda item: item[0])
        if limit is not None:
            entries = entries[:limit]
        return entries

    def scene_agent_names(self, scene_id: str) -> dict[str, str]:
        with self._db.connection() as conn:
            rows = conn.execute(
                "SELECT agent_id, name FROM scene_agents WHERE scene_id = ?", (scene_id,)
            ).fetchall()
        return {str(row["agent_id"]): str(row["name"]) for row in rows}

    def turns_for_budget(self, scene_id: str) -> Sequence[dict]:
        return self.list_turns(scene_id)

    def action_records(self, scene_id: str) -> list[ActionRecord]:
        """把 `SUCCEEDED`／`FAILED` 行动还原为契约模型（供测试与分析核对）。"""

        records: list[ActionRecord] = []
        for turn in self.list_turns(scene_id):
            if turn["status"] == PENDING_TURN_STATUS:
                continue
            records.append(
                ActionRecord(
                    action_id=turn["action_id"],
                    turn_id=turn["turn_id"],
                    attempt_id=turn["attempt_id"],
                    scene_id=turn["scene_id"],
                    actor_id=turn["actor_id"],
                    status=TurnStatus(turn["status"]),
                    draft=(
                        None
                        if turn["action"] is None
                        else {
                            "action": turn["action"],
                            "text": turn["text"] or "",
                            "reply_to_message_id": turn["reply_to_message_id"],
                            "requested_speaker_id": turn["requested_speaker_id"],
                        }
                    ),
                    message_id=turn["message_id"],
                    input_cursor_seq=int(turn["input_cursor_seq"]),
                    prompt_template_id=turn["prompt_template_id"],
                    created_at=datetime.fromisoformat(turn["created_at"]),
                )
            )
        return records
