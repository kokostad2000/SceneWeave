"""模型行动端口的请求／响应契约（PRD 2.2、4.2、5.3）。

端口边界只定义**结构与失败分类**；真实 DeepSeek 调用与 JSON 校验实现属于 M03。
失败路径必须显式存在：空 content、截断、非法 JSON、schema 非法、非法引用，
以及发送结果不明时的 ``UNKNOWN_REQUEST``（保守占用预算，不自动重发）。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .action import ActionDraft
from .enums import ModelFailureKind
from .ids import AgentId, MessageId, SceneId
from .limits import (
    DEFAULT_MODEL_NAME,
    MAX_OUTPUT_TOKENS,
    MAX_PROMPT_CHARS,
    REQUEST_TIMEOUT_SECONDS,
    RESPONSE_FORMAT_JSON_OBJECT,
    SDK_MAX_RETRIES,
    SEND_TOOLS,
    STREAM_BY_DEFAULT,
    THINKING_ENABLED_BY_DEFAULT,
)


class Usage(BaseModel):
    """用量。以服务端返回为准，**缺失记为 unknown，不是 0**（PRD 5.3）。

    本期不承诺货币费用；只记录原始用量，缓存命中字段在返回时记录。
    """

    model_config = ConfigDict(extra="forbid")

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cached_tokens: int | None = Field(default=None, ge=0)

    @property
    def is_unknown(self) -> bool:
        """三个字段全为 None 时视为 unknown。"""

        return self.input_tokens is None and self.output_tokens is None and self.cached_tokens is None


class ModelParams(BaseModel):
    """发送给模型服务端的参数（PRD 2.2 初值，联调后再评审）。

    注意：思考模式开启时温度参数无效，不能靠较低的 temperature 假设思考已关闭。
    本期不发送 ``reasoning_effort=100``，不发送 tools。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = DEFAULT_MODEL_NAME
    max_output_tokens: int = Field(default=MAX_OUTPUT_TOKENS, ge=1)
    thinking_enabled: bool = THINKING_ENABLED_BY_DEFAULT
    stream: bool = STREAM_BY_DEFAULT
    response_format: str = RESPONSE_FORMAT_JSON_OBJECT
    send_tools: bool = SEND_TOOLS
    request_timeout_seconds: int = Field(default=REQUEST_TIMEOUT_SECONDS, ge=1)
    sdk_max_retries: int = Field(default=SDK_MAX_RETRIES, ge=0, le=0)


class ModelActionRequest(BaseModel):
    """一次角色行动请求。

    ``prompt`` 由 ContextBuilder（M02）按实际可见性构建；``cursor_seq`` 是本次
    输入的截止序号快照，行动只能基于发送时的快照（PRD 5.1）。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    scene_id: SceneId
    actor_id: AgentId
    prompt_template_id: str = Field(min_length=1)
    prompt: str
    cursor_seq: int = Field(ge=0)
    params: ModelParams = ModelParams()
    #: 允许的引用范围；由 M04 构建。为空表示本次不做引用校验。
    references: ReferenceScope | None = None

    @model_validator(mode="after")
    def _check_prompt(self) -> ModelActionRequest:
        if len(self.prompt) > MAX_PROMPT_CHARS:
            raise ValueError(
                f"prompt 超过 max_prompt_chars={MAX_PROMPT_CHARS}，必须暂停而不是静默截断"
            )
        return self


class ModelFailure(BaseModel):
    """模型调用失败。失败**不**推进角色已处理位置，也不伪装成 PASS。"""

    model_config = ConfigDict(extra="forbid")

    kind: ModelFailureKind
    detail: str = ""
    http_status: int | None = None


class ReferenceScope(BaseModel):
    """本次调用允许出现的引用范围（PRD 4.2）。

    由 M04 从\"本场已提交且该角色可见的公开发言\"与\"本场其他有效角色\"构建；
    ``reply_to_message_id`` 与 ``requested_speaker_id`` 只能落在其中。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    actor_id: AgentId
    allowed_message_ids: list[MessageId] = Field(default_factory=list)
    allowed_speaker_ids: list[AgentId] = Field(default_factory=list)


class ModelActionResponse(BaseModel):
    """模型调用结果。

    ``ok=True`` 当且仅当存在合法 ``draft`` 且没有 ``failure``。

    ``sent`` 的语义是**是否可能已经送达服务端**：

    - ``sent=False`` + ``UNKNOWN_REQUEST``：发送结果不明，必须保守占用预算，**不得自动重发**（PRD 5.3）；
    - ``sent=False`` + 其他分类：本地拒绝发送（上下文超限、缺少配置、参数非法），
      未新增模型请求，因此**不占用预算**（PRD 5.3）。
    """

    model_config = ConfigDict(extra="forbid")

    ok: bool
    draft: ActionDraft | None = None
    failure: ModelFailure | None = None
    raw_content: str | None = None
    finish_reason: str | None = None
    requested_model: str = DEFAULT_MODEL_NAME
    returned_model: str | None = None
    prompt_template_id: str = Field(min_length=1)
    provider_request_id: str | None = None
    usage: Usage = Field(default_factory=Usage)
    latency_ms: int | None = Field(default=None, ge=0)
    sent: bool = True

    @model_validator(mode="after")
    def _check(self) -> ModelActionResponse:
        if self.ok:
            if self.draft is None:
                raise ValueError("ok=True 必须携带 draft")
            if self.failure is not None:
                raise ValueError("ok=True 不得同时携带 failure")
        elif self.failure is None:
            raise ValueError("ok=False 必须给出 failure 分类")

        if self.failure is not None and self.failure.kind is ModelFailureKind.UNKNOWN_REQUEST:
            if self.sent:
                raise ValueError("发送结果不明必须标记 sent=False")
            if self.draft is not None or self.ok:
                raise ValueError("发送结果不明不得携带 draft")

        if not self.sent:
            if self.ok or self.draft is not None:
                raise ValueError("未发送的调用不得返回 draft")
            if self.failure is None:
                raise ValueError("未发送的调用必须给出 failure 分类")

        # 成功的 PASS 同样是合法结果：不形成聊天气泡，但由 M04 落盘并推进游标。
        return self
