"""模型行动端口（PRD 第 8 节：首版只定义两个外部端口之一）。

- 协议 :class:`ModelPort` 与确定性 :class:`MockModelPort`（M00，不联网、不需要密钥）；
- 真实 DeepSeek Chat Completions 客户端在 :mod:`role_theater.ports.deepseek`（M03）；
- :func:`build_model_port` 按配置选择实现：**未配置凭证时一律使用 Mock**，
  绝不发起网络调用。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from ..contracts import (
    ActionDraft,
    ActionType,
    ModelActionRequest,
    ModelActionResponse,
    ModelFailure,
    ModelFailureKind,
    Usage,
)

if TYPE_CHECKING:  # pragma: no cover - 仅用于类型标注，避免运行期循环导入
    import httpx


@runtime_checkable
class ModelPort(Protocol):
    """一次调用只为**一个**指定角色生成一个行动。"""

    async def generate_action(self, request: ModelActionRequest) -> ModelActionResponse:
        """返回行动草稿或结构化失败；不得抛出未分类的异常。"""
        ...


class MockModelPort:
    """确定性的假模型实现，用于无密钥测试（PRD 10：确定性验收用可控 Mock）。

    用法：传入脚本序列（``ActionDraft`` 或 ``ModelFailure``）；脚本用尽后使用
    ``default_draft``（默认 PASS）。所有调用记录在 ``calls`` 中以便断言。

    该实现**不伪造用量**：未显式提供 usage 时返回 unknown（三个字段为 None），
    与 PRD 5.3“缺失为 unknown 而非零”一致。
    """

    def __init__(
        self,
        script: Sequence[ActionDraft | ModelFailure] | None = None,
        *,
        default_draft: ActionDraft | None = None,
        usage: Usage | None = None,
        requested_model: str | None = None,
    ) -> None:
        self._script: list[ActionDraft | ModelFailure] = list(script or [])
        self._default_draft = (
            default_draft if default_draft is not None else ActionDraft(action=ActionType.PASS)
        )
        self._usage = usage
        self._requested_model = requested_model
        self.calls: list[ModelActionRequest] = []

    @property
    def call_count(self) -> int:
        """已接收的请求次数（用于断言“校验失败不新增模型请求”）。"""

        return len(self.calls)

    async def generate_action(self, request: ModelActionRequest) -> ModelActionResponse:
        self.calls.append(request)
        resolved_model = self._requested_model or request.params.model
        usage = self._usage if self._usage is not None else Usage()

        item: ActionDraft | ModelFailure = (
            self._script.pop(0) if self._script else self._default_draft
        )

        if isinstance(item, ModelFailure):
            # 发送结果不明必须与 sent=False 绑定（PRD 5.3）。
            sent = item.kind is not ModelFailureKind.UNKNOWN_REQUEST
            return ModelActionResponse(
                ok=False,
                sent=sent,
                failure=item,
                raw_content=None,
                finish_reason=None,
                requested_model=resolved_model,
                returned_model=None,
                prompt_template_id=request.prompt_template_id,
                usage=usage,
            )

        from .action_parser import validate_references
        failure = validate_references(item, request.references, chat_policy_version=request.chat_policy_version)
        if failure is not None:
            return ModelActionResponse(ok=False, failure=failure, raw_content=item.model_dump_json(),
                prompt_template_id=request.prompt_template_id, requested_model=resolved_model, usage=usage)
        return ModelActionResponse(
            ok=True,
            draft=item,
            failure=None,
            raw_content=item.model_dump_json(),
            finish_reason="stop",
            requested_model=resolved_model,
            returned_model=resolved_model,
            prompt_template_id=request.prompt_template_id,
            usage=usage,
        )


#: 模型提供方取值（PRD 第 8 节「可替换模型适配器」）。
PROVIDER_AUTO = "auto"
PROVIDER_MOCK = "mock"
PROVIDER_DEEPSEEK = "deepseek"
PROVIDER_LOCAL = "local"

MODEL_PROVIDERS: tuple[str, ...] = (
    PROVIDER_AUTO,
    PROVIDER_MOCK,
    PROVIDER_DEEPSEEK,
    PROVIDER_LOCAL,
)

#: 本地服务通常不需要凭证；DeepSeek 必须有凭证。
PROVIDERS_REQUIRING_KEY: frozenset[str] = frozenset({PROVIDER_DEEPSEEK})


def build_model_port(
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    transport: "httpx.AsyncBaseTransport | None" = None,
    force_mock: bool = False,
    provider: str = PROVIDER_AUTO,
    include_response_format: bool = True,
    mock_script: Sequence[ActionDraft | ModelFailure] | None = None,
    mock_default_draft: ActionDraft | None = None,
    extra_client_kwargs: dict[str, Any] | None = None,
) -> ModelPort:
    """按配置返回模型端口（PRD 第 8 节：可替换模型适配器）。

    选择规则：

    - ``force_mock=True`` 或 ``provider="mock"`` → :class:`MockModelPort`；
    - ``provider="local"`` → :class:`~role_theater.ports.local.LocalModelClient`
      （**不需要凭证**，不发送 DeepSeek 专有的 ``thinking`` 字段）；
    - ``provider="deepseek"`` → :class:`~role_theater.ports.deepseek.DeepSeekModelClient`；
    - ``provider="auto"``（默认）→ 有凭证走 DeepSeek，否则回落 Mock。

    ``transport`` 用于测试注入 ``httpx.MockTransport``，从而在无网络环境下验证
    请求参数与失败分类。
    """

    if force_mock or provider == PROVIDER_MOCK:
        return MockModelPort(script=mock_script, default_draft=mock_default_draft)

    if provider == PROVIDER_LOCAL:
        from .local import LocalModelClient

        return LocalModelClient(
            base_url=base_url,
            api_key=api_key,
            transport=transport,
            include_response_format=include_response_format,
            **(extra_client_kwargs or {}),
        )

    if provider == PROVIDER_DEEPSEEK or (api_key or "").strip():
        # 显式选择 deepseek 但没有凭证时，**不静默回落 Mock**：
        # 交给客户端按 MISSING_CONFIG 报告，避免“以为在真实调用”。
        from .deepseek import DeepSeekModelClient

        return DeepSeekModelClient(
            api_key=api_key,
            base_url=base_url,
            transport=transport,
            **(extra_client_kwargs or {}),
        )

    return MockModelPort(script=mock_script, default_draft=mock_default_draft)
