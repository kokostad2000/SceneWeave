"""运行控制契约（PRD 5.1、5.2、5.4）。

控制命令携带 ``request_id``；同一命令重复提交返回既有结果（幂等）。M00 只定义
结构，幂等实现属于 M04。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import ControlCommandType, PauseReason, RunState, SchedulerReason, TurnStatus
from .event import Event, EventSubmission
from .ids import AgentId, EventId, RequestId, SceneId


class ControlCommand(BaseModel):
    """控制命令信封。``request_id`` 用于幂等去重。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: RequestId
    command: ControlCommandType


class InjectEventCommand(BaseModel):
    """提交人工事件（暂停时立即生效；调用中先保存为待生效，PRD 4.3）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: RequestId
    event: EventSubmission


class CommandAck(BaseModel):
    """命令受理结果。

    ``deduplicated=True`` 表示重放同一个幂等命令，**未**新增模型请求或记录
    （PRD 5.3、5.4）。``event_status`` 区分“已接受”与“已生效”。
    """

    model_config = ConfigDict(extra="forbid")

    request_id: RequestId
    command: ControlCommandType | None = None
    accepted: bool
    deduplicated: bool = False
    run_state: RunState
    pause_reason: PauseReason | None = None
    event_id: EventId | None = None
    event_status: str | None = None
    detail: str | None = None


class RoleCursor(BaseModel):
    """每个角色的已处理位置。只有成功的 SPEAK／PASS 才推进（PRD 5.1）。"""

    model_config = ConfigDict(extra="forbid")

    scene_id: SceneId
    agent_id: AgentId
    processed_seq: int = Field(default=0, ge=0)
    startup_opportunity_consumed: bool = False
    last_action_turn_id: str | None = None
    last_action_status: TurnStatus | None = None
    last_action_at: datetime | None = None
    consecutive_requested_priority: int = Field(default=0, ge=0, le=2)


class SchedulerDirective(BaseModel):
    """一次调度决策，可复核（PRD 5.1）。不额外调用主持模型。"""

    model_config = ConfigDict(extra="forbid")

    scene_id: SceneId
    actor_id: AgentId
    reason: SchedulerReason
    based_on_seq: int = Field(ge=0)
    requested_by_agent_id: AgentId | None = None


class RunStatus(BaseModel):
    """会话运行状态快照，用于界面与 SSE 之外的只读查询。"""

    model_config = ConfigDict(extra="forbid")

    scene_id: SceneId
    run_state: RunState
    pause_reason: PauseReason | None = None
    last_committed_seq: int = Field(default=0, ge=0)
    pending_event_count: int = Field(default=0, ge=0)


class TimelineEntry(BaseModel):
    """时间线条目：消息与事件共享场景内单调 ``seq``。

    分析报告、错误、使用量、SSE 心跳和运行状态**不属于剧情**，因此不是
    TimelineEntry 的类型之一（PRD 4.1）。
    """

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(pattern="^(message|event)$")
    seq: int = Field(ge=1)
    event: Event | None = None
