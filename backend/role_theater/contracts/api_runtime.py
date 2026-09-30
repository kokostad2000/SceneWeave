"""M04 请求／响应契约：控制命令、事件注入、时间线、角色视角。

新增契约模型必须登记到 :mod:`role_theater.contracts.registry`。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .enums import ControlCommandType, EventStatus, EventVisibility, PauseReason, RunState
from .event import Event, EventSubmission
from .ids import AgentId, EventId, RequestId, SceneId
from .limits import MAX_ANALYSIS_REQUESTS_PER_SCENE, MAX_ROLE_REQUESTS_PER_SCENE, MAX_PROMPT_CHARS
from .runtime import RunStatus
from .scene import Message
from .action import ActionDraft


class ControlCommandRequest(BaseModel):
    """控制命令（PRD 5.2、5.4：携带 ``request_id`` 以便幂等）。"""

    model_config = ConfigDict(extra="forbid")

    request_id: RequestId
    command: ControlCommandType


class InjectEventRequest(BaseModel):
    """提交人工事件（PRD 4.3）。"""

    model_config = ConfigDict(extra="forbid")

    request_id: RequestId
    body: str
    visibility: EventVisibility
    target_agent_id: AgentId | None = None

    def to_submission(self) -> EventSubmission:
        return EventSubmission(
            body=self.body,
            visibility=self.visibility,
            target_agent_id=self.target_agent_id,
        )


class TimelineEntryView(BaseModel):
    """时间线条目：消息与事件共享 ``seq``（PRD 第 8 节）。"""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(pattern="^(message|event)$")
    seq: int = Field(ge=1)
    message: Message | None = None
    event: Event | None = None
    author_name: str | None = None


class ConversationView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversation_id: str
    scene_id: SceneId
    participant_ids: list[AgentId] = Field(min_length=2, max_length=2)
    participant_names: list[str] = Field(min_length=2, max_length=2)
    last_seq: int = Field(ge=1)
    message_count: int = Field(ge=1)


class ConversationListView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene_id: SceneId
    conversations: list[ConversationView]
    total: int = Field(ge=0)


class ActionHistoryView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: str
    actor_id: AgentId
    status: str
    draft: ActionDraft | None = None
    failure_kind: str | None = None
    created_at: str


class TimelineView(BaseModel):
    """时间线（含预算与运行状态，便于历史页只读渲染）。"""

    model_config = ConfigDict(extra="forbid")

    scene_id: SceneId
    status: RunStatus
    last_seq: int = Field(ge=0)
    role_requests_used: int = Field(ge=0)
    max_role_requests: int = Field(ge=0)
    analysis_requests_used: int = Field(ge=0)
    max_analysis_requests: int = Field(ge=0)
    entries: list[TimelineEntryView]
    conversations: list[ConversationView] = Field(default_factory=list)
    actions: list[ActionHistoryView] = Field(default_factory=list)


class ViewpointView(BaseModel):
    """角色视角（PRD 7.2）：与调用器**实际使用相同**的上下文选择结果。"""

    model_config = ConfigDict(extra="forbid")

    scene_id: SceneId
    agent_id: AgentId
    agent_name: str
    prompt_template_id: str
    cutoff_seq: int = Field(ge=0)
    public_roster: list[str]
    visible_seq: list[int]
    visible_kinds: list[str]
    prompt: str
    prompt_codepoints: int = Field(default=0, ge=0)
    max_prompt_codepoints: int = MAX_PROMPT_CHARS
    entries: list[TimelineEntryView] = Field(default_factory=list)
    conversations: list[ConversationView] = Field(default_factory=list)
    actions: list[ActionHistoryView] = Field(default_factory=list)


class RunStateView(BaseModel):
    """当前运行状态与预算（供界面控制区使用）。"""

    model_config = ConfigDict(extra="forbid")

    scene_id: SceneId
    status: RunState
    pause_reason: PauseReason | None = None
    role_requests_used: int = Field(ge=0)
    max_role_requests: int = Field(default=MAX_ROLE_REQUESTS_PER_SCENE, ge=0)
    analysis_requests_used: int = Field(ge=0)
    max_analysis_requests: int = Field(default=MAX_ANALYSIS_REQUESTS_PER_SCENE, ge=0)
    in_flight: bool = False
    last_committed_seq: int = Field(ge=0)


class EventView(BaseModel):
    """单个事件（含状态，界面需区分已接受／已生效）。"""

    model_config = ConfigDict(extra="forbid")

    event: Event
    status: EventStatus


class EventIdView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: EventId


class AgentStatusView(BaseModel):
    """单个本场角色的执行状态（PRD 7.1：角色卡显示名称与执行状态）。

    只暴露**运行事实**（是否行动过、上次行动结果、已处理到哪条），
    不含任何心理或关系评分。
    """

    model_config = ConfigDict(extra="forbid")

    agent_id: AgentId
    name: str
    order_index: int = Field(ge=0)
    has_acted: bool = False
    startup_opportunity_consumed: bool = False
    processed_seq: int = Field(default=0, ge=0)
    last_action_at: str | None = None
    last_action_status: str | None = None
    #: 是否被时间线上最新一条发言点名（界面高亮“当前待回应对象”）。
    is_requested: bool = False
    #: 本角色已提交的公开发言条数。
    speak_count: int = Field(default=0, ge=0)
    generating: bool = False
    last_failure_kind: str | None = None
    last_successful_draft: ActionDraft | None = None
    prompt_codepoints: int = Field(default=0, ge=0)
    max_prompt_codepoints: int = MAX_PROMPT_CHARS


class AgentStatusListView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: SceneId
    in_flight: bool = False
    agents: list[AgentStatusView]


class ScenarioSummaryView(BaseModel):
    """运行概览：实际调用计数与失败统计（PRD 1.2「实际调用计数」）。"""

    model_config = ConfigDict(extra="forbid")

    scene_id: SceneId
    role_requests_used: int = Field(ge=0)
    max_role_requests: int = Field(ge=0)
    succeeded: int = Field(ge=0)
    failed: int = Field(ge=0)
    unknown: int = Field(ge=0)
    last_failure_kind: str | None = None


class ReplyRelationView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message_id: str
    reply_to_message_id: str


class RoleActionCountView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_id: AgentId
    name: str
    succeeded: int = Field(ge=0)
    public_speaks: int = Field(ge=0)
    private_initiations: int = Field(ge=0)
    private_replies: int = Field(ge=0)
    passes: int = Field(ge=0)
    failed: int = Field(ge=0)
    unknown: int = Field(ge=0)


class FactStatisticsView(BaseModel):
    """已提交记录事实；viewer_id 的统计只包含其合法集合。"""
    model_config = ConfigDict(extra="forbid")
    scene_id: SceneId
    viewer_id: AgentId | None = None
    public_messages: int = Field(ge=0)
    private_messages: int = Field(ge=0)
    participant_ids: list[AgentId]
    reply_relations: list[ReplyRelationView]
    role_actions: list[RoleActionCountView]
