"""通用契约：错误响应、健康检查与契约自检摘要。

``ContractSummary`` 让前端与契约测试可以核对枚举取值与长度上限，避免前后端
各自维护不一致的常量（PRD 第 8 节）。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    ActionType,
    AnalysisStatus,
    ControlCommandType,
    EventStatus,
    EventVisibility,
    ModelFailureKind,
    PauseReason,
    RunState,
    SchedulerReason,
    TurnStatus,
)
from .limits import (
    APP_NAME,
    APP_VERSION,
    CONTRACT_VERSION,
    DEFAULT_AGENTS_PER_SCENE,
    DEFAULT_MODEL_NAME,
    MAX_AGENT_NAME_CODEPOINTS,
    MAX_AGENTS_PER_SCENE,
    MAX_ANALYSIS_BEHAVIOR_DESCRIPTION_CODEPOINTS,
    MAX_ANALYSIS_CONTEXT_CODEPOINTS,
    MAX_ANALYSIS_REQUESTS_PER_SCENE,
    MAX_EVENT_BODY_CODEPOINTS,
    MAX_INITIAL_GOAL_CODEPOINTS,
    MAX_OUTPUT_TOKENS,
    MAX_PERSONA_CODEPOINTS,
    MAX_PRIVATE_BACKGROUND_CODEPOINTS,
    MAX_PROMPT_CHARS,
    MAX_ROLE_REQUESTS_PER_SCENE,
    MAX_SCENE_BACKGROUND_CODEPOINTS,
    MAX_SPEAK_TEXT_CODEPOINTS,
    MAX_SPEECH_STYLE_CODEPOINTS,
    MIN_AGENTS_PER_SCENE,
    MIN_SPEAK_TEXT_CODEPOINTS,
    REQUEST_TIMEOUT_SECONDS,
    SCHEMA_VERSION,
    SDK_MAX_RETRIES,
    SEND_TOOLS,
    STREAM_BY_DEFAULT,
    THINKING_ENABLED_BY_DEFAULT,
)

#: 全部契约枚举。新增枚举必须登记在此，确保自检摘要与前端类型同步。
CONTRACT_ENUMS: dict[str, type] = {
    "ActionType": ActionType,
    "EventVisibility": EventVisibility,
    "EventStatus": EventStatus,
    "RunState": RunState,
    "PauseReason": PauseReason,
    "ControlCommandType": ControlCommandType,
    "TurnStatus": TurnStatus,
    "ModelFailureKind": ModelFailureKind,
    "AnalysisStatus": AnalysisStatus,
    "SchedulerReason": SchedulerReason,
}

#: 按 Unicode 码点计数的长度上限。
CONTRACT_LIMIT_CODEPOINTS: dict[str, int] = {
    "agent_name": MAX_AGENT_NAME_CODEPOINTS,
    "persona": MAX_PERSONA_CODEPOINTS,
    "speech_style": MAX_SPEECH_STYLE_CODEPOINTS,
    "initial_goal": MAX_INITIAL_GOAL_CODEPOINTS,
    "private_background": MAX_PRIVATE_BACKGROUND_CODEPOINTS,
    "scene_background": MAX_SCENE_BACKGROUND_CODEPOINTS,
    "event_body": MAX_EVENT_BODY_CODEPOINTS,
    "speak_text": MAX_SPEAK_TEXT_CODEPOINTS,
    "analysis_behavior_description": MAX_ANALYSIS_BEHAVIOR_DESCRIPTION_CODEPOINTS,
    "analysis_context": MAX_ANALYSIS_CONTEXT_CODEPOINTS,
    "max_prompt_chars": MAX_PROMPT_CHARS,
}

#: 外部端口名称。首版只有两个，不建通用插件系统（PRD 第 8 节）。
EXTERNAL_PORTS: tuple[str, ...] = ("ModelPort", "AnalysisPort")


class EnumSummary(BaseModel):
    """单个枚举的取值摘要。"""

    model_config = ConfigDict(extra="forbid")

    name: str
    values: list[str]


class ContractSummary(BaseModel):
    """契约自检摘要，供前端与测试核对。不承载业务逻辑。"""

    model_config = ConfigDict(extra="forbid")

    app_name: str = APP_NAME
    app_version: str = APP_VERSION
    contract_version: str = CONTRACT_VERSION
    schema_version: int = SCHEMA_VERSION
    enums: list[EnumSummary]
    limit_codepoints: dict[str, int]
    agent_count: dict[str, int]
    budgets: dict[str, int]
    model_params: dict[str, object]
    ports: list[str]
    run_states: list[str]


class HealthResponse(BaseModel):
    """最小健康检查响应。

    **不需要任何模型密钥**即可返回 200；未配置密钥只体现为
    ``model_configured=false``。健康检查不发起任何外部调用。
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"] = "ok"
    app_name: str = APP_NAME
    app_version: str = APP_VERSION
    contract_version: str = CONTRACT_VERSION
    run_state: RunState = RunState.READY
    analysis_enabled: bool = False
    model_configured: bool = False
    #: 凭证来源（``environment``／``dotenv``／``none``）。**不含**凭证内容，
    #: 用于确认 .env 是否被真正读取。
    model_credential_source: str = "none"
    #: 实际生效的模型提供方：``mock``／``deepseek``／``local``（PRD 第 8 节）。
    model_provider: str = "mock"


class ApiError(BaseModel):
    """统一错误响应。``request_id`` 便于与幂等命令对账（PRD 5.4）。"""

    model_config = ConfigDict(extra="forbid")

    error: str
    detail: str = ""
    request_id: str | None = None
    retryable: bool = Field(default=False)


def build_contract_summary() -> ContractSummary:
    """从契约常量构建自检摘要（单一来源，不手写重复常量）。"""

    return ContractSummary(
        enums=[
            EnumSummary(name=name, values=[member.value for member in enum_cls])
            for name, enum_cls in CONTRACT_ENUMS.items()
        ],
        limit_codepoints=dict(CONTRACT_LIMIT_CODEPOINTS),
        agent_count={
            "min": MIN_AGENTS_PER_SCENE,
            "max": MAX_AGENTS_PER_SCENE,
            "default": DEFAULT_AGENTS_PER_SCENE,
        },
        budgets={
            "max_role_requests_per_scene": MAX_ROLE_REQUESTS_PER_SCENE,
            "max_analysis_requests_per_scene": MAX_ANALYSIS_REQUESTS_PER_SCENE,
        },
        model_params={
            "model": DEFAULT_MODEL_NAME,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "request_timeout_seconds": REQUEST_TIMEOUT_SECONDS,
            "sdk_max_retries": SDK_MAX_RETRIES,
            "thinking_enabled": THINKING_ENABLED_BY_DEFAULT,
            "stream": STREAM_BY_DEFAULT,
            "send_tools": SEND_TOOLS,
            "min_speak_text_codepoints": MIN_SPEAK_TEXT_CODEPOINTS,
        },
        ports=list(EXTERNAL_PORTS),
        run_states=[member.value for member in RunState],
    )
