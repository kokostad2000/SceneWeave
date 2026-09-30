"""角色、场景、消息与预算契约（PRD 3.1～3.3、4.1、5.3）。

关键点：角色集合是**集合**，不是固定列。契约中不出现 agent1／agent2／agent3
之类字段；规模上限由 ``MIN_AGENTS_PER_SCENE``／``MAX_AGENTS_PER_SCENE`` 约束。
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

from .enums import MessageVisibility, PauseReason, RunState, SceneMode
from .mode import SimulationConfig, DiscussionConfig, DiscussionParticipantConfig, resolve_mode_config
from .ids import AgentId, MessageId, SceneId, TemplateId
from .limits import (
    DEFAULT_AGENTS_PER_SCENE,
    MAX_AGENT_NAME_CODEPOINTS,
    MAX_AGENTS_PER_SCENE,
    MAX_ANALYSIS_REQUESTS_PER_SCENE,
    MAX_INITIAL_GOAL_CODEPOINTS,
    MAX_PERSONA_CODEPOINTS,
    MAX_PRIVATE_BACKGROUND_CODEPOINTS,
    MAX_ROLE_REQUESTS_PER_SCENE,
    MAX_SCENE_BACKGROUND_CODEPOINTS,
    MAX_SCENE_REQUEST_LIMIT,
    MAX_SPEECH_STYLE_CODEPOINTS,
    MIN_AGENTS_PER_SCENE,
    MIN_SCENE_REQUEST_LIMIT,
    SCHEMA_VERSION,
    codepoint_length,
)


def _strip(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


def _codepoints(value: str) -> int:
    return codepoint_length(value)


def _configuration_version(value):
    if type(value) is not int:
        raise ValueError("配置版本必须是整数 1 或 2")
    return value


ConfigurationVersion = Annotated[Literal[1, 2], BeforeValidator(_configuration_version)]
ChatPolicyVersion = Annotated[Literal[1, 2], BeforeValidator(_configuration_version)]


class SceneRoleProfile(BaseModel):
    """本场行为资料；未填写保持为空，不回退到人物目录。"""

    model_config = ConfigDict(extra="forbid")
    persona: str = Field(default="", max_length=MAX_PERSONA_CODEPOINTS)
    speech_style: str = Field(default="", max_length=MAX_SPEECH_STYLE_CODEPOINTS)
    initial_goal: str = Field(default="", max_length=MAX_INITIAL_GOAL_CODEPOINTS)
    private_background: str = Field(default="", max_length=MAX_PRIVATE_BACKGROUND_CODEPOINTS)
    public_profile: str = Field(default="", max_length=MAX_PERSONA_CODEPOINTS)

    @field_validator("persona", "speech_style", "initial_goal", "private_background", "public_profile", mode="before")
    @classmethod
    def _strip_profile(cls, value: object) -> object:
        return _strip(value)


class AgentProfileFields(SceneRoleProfile):
    """人物名称与旧版兼容资料；新创建流程只复用名称。"""

    model_config = ConfigDict(extra="forbid")

    name: str

    @field_validator("name", "persona", "speech_style", "initial_goal", "private_background", "public_profile", mode="before")
    @classmethod
    def _strip_fields(cls, value: object) -> object:
        return _strip(value)

    @model_validator(mode="after")
    def _check_limits(self) -> AgentProfileFields:
        if not self.name:
            raise ValueError("角色名称不能为空")
        limits = (
            ("name", self.name, MAX_AGENT_NAME_CODEPOINTS),
            ("persona", self.persona, MAX_PERSONA_CODEPOINTS),
            ("speech_style", self.speech_style, MAX_SPEECH_STYLE_CODEPOINTS),
            ("initial_goal", self.initial_goal, MAX_INITIAL_GOAL_CODEPOINTS),
            ("private_background", self.private_background, MAX_PRIVATE_BACKGROUND_CODEPOINTS),
        )
        for field_name, value, limit in limits:
            if _codepoints(value) > limit:
                raise ValueError(
                    f"{field_name} 不能超过 {limit} 个 Unicode 码点，实际 {_codepoints(value)}"
                )
        return self


class AgentTemplate(AgentProfileFields):
    """角色模板；支持创建、编辑、复制、列表查看与移除（PRD 3.2）。"""

    model_config = ConfigDict(extra="forbid")

    template_id: TemplateId
    created_at: datetime
    updated_at: datetime


class AgentSnapshot(AgentProfileFields):
    """创建本场角色时保存的模板快照。

    模板后续改动**不影响**历史与已有会话；同时记录模板来源 ID。
    """

    model_config = ConfigDict(extra="forbid")

    source_template_id: TemplateId
    captured_at: datetime


class SceneAgent(BaseModel):
    """本场角色实例：``agent_id`` 是关联主键，``name`` 是显示字段。"""

    model_config = ConfigDict(extra="forbid")

    agent_id: AgentId
    scene_id: SceneId
    name: str
    order_index: int = Field(ge=0)
    snapshot: AgentSnapshot
    discussion_config: DiscussionParticipantConfig | None = None
    created_at: datetime

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, value: object) -> object:
        return _strip(value)

    @model_validator(mode="after")
    def _check(self) -> SceneAgent:
        if not self.name or _codepoints(self.name) > MAX_AGENT_NAME_CODEPOINTS:
            raise ValueError(
                f"角色名称必须为 1～{MAX_AGENT_NAME_CODEPOINTS} 个 Unicode 码点"
            )
        return self


class Message(BaseModel):
    """已提交的公开或一对一私聊角色消息（PRD 4.1、4.2）。

    ``PASS`` 不形成聊天气泡，但保存行动结果并推进已处理位置——因此这里只
    承载 SPEAK／PRIVATE 产生的消息。
    """

    model_config = ConfigDict(extra="forbid")

    message_id: MessageId
    scene_id: SceneId
    seq: int = Field(ge=1)
    actor_id: AgentId
    text: str
    reply_to_message_id: MessageId | None = None
    requested_speaker_id: AgentId | None = None
    visibility: MessageVisibility = MessageVisibility.PUBLIC
    recipient_id: AgentId | None = None
    conversation_id: str | None = None
    schema_version: int = 1
    created_at: datetime

    @model_validator(mode="after")
    def _check_channel(self) -> Message:
        if self.visibility is MessageVisibility.PRIVATE:
            if self.recipient_id is None or self.recipient_id == self.actor_id or not self.conversation_id:
                raise ValueError("私聊必须指定另一收件人及会话")
            if self.requested_speaker_id is not None:
                raise ValueError("私聊不得有公开点名")
        elif self.recipient_id is not None or self.conversation_id is not None:
            raise ValueError("公开消息不得含私聊字段")
        return self


class Budget(BaseModel):
    """每场预算上限（PRD 5.3）。

    两项独立计数；创建前可在服务端允许范围内修改，开始时锁定（``locked_at``）。
    """

    model_config = ConfigDict(extra="forbid")

    max_role_requests: int = Field(
        default=MAX_ROLE_REQUESTS_PER_SCENE,
        ge=MIN_SCENE_REQUEST_LIMIT,
        le=MAX_SCENE_REQUEST_LIMIT,
    )
    max_analysis_requests: int = Field(
        default=MAX_ANALYSIS_REQUESTS_PER_SCENE,
        ge=0,
        le=MAX_SCENE_REQUEST_LIMIT,
    )
    locked_at: datetime | None = None


class BudgetUsage(BaseModel):
    """预算消耗计数。

    每次**实际发送**都占用一次；失败、超时和人工重试不退款（PRD 5.3）。
    """

    model_config = ConfigDict(extra="forbid")

    role_requests_used: int = Field(default=0, ge=0)
    analysis_requests_used: int = Field(default=0, ge=0)
    role_requests_in_flight: int = Field(default=0, ge=0, le=1)
    analysis_requests_in_flight: int = Field(default=0, ge=0, le=1)


class Scene(BaseModel):
    """场景／会话（PRD 3.1、5.2）。一个活动场景，多份历史记录。"""

    model_config = ConfigDict(extra="forbid")

    scene_id: SceneId
    title: str = Field(min_length=1, max_length=120)
    background: str
    mode: SceneMode = SceneMode.SIMULATION
    mode_config: SimulationConfig | DiscussionConfig | None = None
    configuration_version: ConfigurationVersion = 1
    chat_policy_version: ChatPolicyVersion = 1
    status: RunState = RunState.READY
    pause_reason: PauseReason | None = None
    budget: Budget
    schema_version: int = SCHEMA_VERSION
    created_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None

    @field_validator("background", mode="before")
    @classmethod
    def _strip_background(cls, value: object) -> object:
        return _strip(value)

    @model_validator(mode="after")
    def _check(self) -> Scene:
        self.mode_config = resolve_mode_config(self.mode, self.mode_config, self.background)
        self.background = self.mode_config.background_text()
        if _codepoints(self.background) > MAX_SCENE_BACKGROUND_CODEPOINTS:
            raise ValueError(
                f"场景背景不能超过 {MAX_SCENE_BACKGROUND_CODEPOINTS} 个 Unicode 码点，"
                f"实际 {_codepoints(self.background)}"
            )
        if self.status is RunState.PAUSED:
            if self.pause_reason is None:
                raise ValueError("PAUSED 必须给出可区分的 pause_reason")
        elif self.pause_reason is not None:
            raise ValueError("只有 PAUSED 状态才携带 pause_reason")
        if self.status is RunState.ENDED and self.ended_at is None:
            raise ValueError("ENDED 必须有 ended_at")
        return self


def validate_agent_count(count: int) -> int:
    """校验本场角色数量在 2～8 之间（PRD 1.2）。"""

    if count < MIN_AGENTS_PER_SCENE or count > MAX_AGENTS_PER_SCENE:
        raise ValueError(
            f"本场角色数量必须在 {MIN_AGENTS_PER_SCENE}～{MAX_AGENTS_PER_SCENE} 之间，实际 {count}"
        )
    return count


DEFAULT_SCENE_AGENT_COUNT = DEFAULT_AGENTS_PER_SCENE
