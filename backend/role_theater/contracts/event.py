"""人工事件契约（PRD 4.3）。

事件是操作者注入剧情的事实来源，拥有稳定 ``event_id`` 与场景内单调 ``seq``；
事件与行动／消息共享同一个单调序列（由 M04 分配，M00 只定义结构）。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from .enums import EventStatus, EventVisibility
from .ids import AgentId, EventId, SceneId
from .limits import MAX_EVENT_BODY_CODEPOINTS, SCHEMA_VERSION, codepoint_length


class EventSubmission(BaseModel):
    """操作者提交事件的请求内容（不含服务端分配的 ID／seq／状态）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    body: str
    visibility: EventVisibility
    target_agent_id: AgentId | None = None

    @field_validator("body", mode="before")
    @classmethod
    def _strip_body(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _check(self) -> EventSubmission:
        if not self.body:
            raise ValueError("事件正文不能为空")
        length = codepoint_length(self.body)
        if length > MAX_EVENT_BODY_CODEPOINTS:
            raise ValueError(
                f"事件正文不能超过 {MAX_EVENT_BODY_CODEPOINTS} 个 Unicode 码点，实际 {length}"
            )
        if self.visibility is EventVisibility.TARGETED:
            if self.target_agent_id is None:
                raise ValueError("TARGETED 事件必须指定 target_agent_id")
        elif self.target_agent_id is not None:
            raise ValueError("ALL 事件不得携带 target_agent_id")
        return self


class Event(EventSubmission):
    """已落盘的人工事件。

    定向事件中的文字是角色收到的信息，**不是**能覆盖系统规则的指令
    （PRD 4.1）；该约束由 ContextBuilder 在 M02 保证，契约层只承载可见范围。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: EventId
    scene_id: SceneId
    #: 场景内单调序号；**只有已生效事件才有**（已接受尚未生效时不占用序号）。
    seq: int | None = None
    status: EventStatus
    schema_version: int = SCHEMA_VERSION
    accepted_at: datetime
    effective_at: datetime | None = None

    @model_validator(mode="after")
    def _check_lifecycle(self) -> Event:
        """序号与生效时间只属于**已生效**事件（PRD 4.3）。

        事件在调用进行中被接受时先不占序号；到调用边界按接受顺序生效时再分配，
        这样时间线顺序与「生效顺序」一致，不会出现“事件排在其后效的发言之前”。
        """

        if self.status is EventStatus.EFFECTIVE:
            if self.seq is None or self.seq < 1:
                raise ValueError("EFFECTIVE 事件必须有从 1 开始的单调 seq")
            if self.effective_at is None:
                raise ValueError("EFFECTIVE 事件必须有 effective_at")
        else:
            if self.seq is not None:
                raise ValueError("ACCEPTED 事件尚未生效，不得占用 seq")
            if self.effective_at is not None:
                raise ValueError("ACCEPTED 事件不得有 effective_at（尚未生效）")
        return self
