"""OpenAI 兼容的 Chat Completions 客户端基类（PRD 2.2、4.2、5.3、第 8 节）。

DeepSeek 云服务与本地推理服务（Ollama／LM Studio／vLLM／llama.cpp 等）都提供
OpenAI 兼容的 ``/chat/completions``，差异只在**请求片段**上：

- DeepSeek 要求显式关闭思考（``thinking``），本地服务通常**不认识**该字段；
- 本地服务一般不需要凭证，部分实现不支持 ``response_format``。

因此把差异集中到 :class:`ChatProfile`，把「发送 → 解析 → 用量 → 失败分类」的
机制放在这里共用；新增第三方兼容服务只需再加一个 profile（PRD 第 8 节要求
可替换模型适配器）。

成功／失败的判定一律走 :func:`role_theater.ports.action_parser.parse_action_content`，
不因换后端而放宽。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import SecretStr

from ..contracts import (
    MAX_PROMPT_CHARS,
    ModelActionRequest,
    ModelActionResponse,
    ModelFailure,
    ModelFailureKind,
    Usage,
    codepoint_length,
)
from .action_parser import parse_action_content
from .token_limit import (
    SingleCallTokenLimitExceeded,
    actual_usage_exceeds_single_call_limit,
    check_single_call_token_limit,
)

CHAT_COMPLETIONS_PATH = "/chat/completions"

#: 应用侧的保守字符上限（PRD 5.3）：超过则**不发送**，交由 M04 暂停。
MAX_PROMPT_CHARS_LIMIT = MAX_PROMPT_CHARS


@dataclass(frozen=True, slots=True)
class ChatProfile:
    """某个 OpenAI 兼容服务的请求差异。"""

    name: str
    #: 是否发送 ``thinking`` 开关（DeepSeek 需要；本地服务通常不认识）。
    thinking_payload: dict[str, Any] | None = None
    thinking_enabled_payload: dict[str, Any] | None = None
    #: 是否发送 ``response_format``（部分本地实现不支持）。
    include_response_format: bool = True
    #: 是否必须提供凭证（本地服务通常不需要）。
    require_api_key: bool = True
    #: 附加请求头（不含 Authorization）。
    extra_headers: dict[str, str] = field(default_factory=dict)

    def payload_fragments(self, *, thinking_enabled: bool) -> dict[str, Any]:
        if self.thinking_payload is None:
            return {}
        if thinking_enabled and self.thinking_enabled_payload is not None:
            return dict(self.thinking_enabled_payload)
        return dict(self.thinking_payload)


class OpenAICompatibleChatClient:
    """实现 :class:`role_theater.ports.model.ModelPort` 的通用客户端。"""

    profile: ChatProfile = ChatProfile(name="openai-compatible")

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        # 用 SecretStr 保存：repr／str／意外 dump 都只显示掩码（AGENTS.md 第 3 节）。
        stripped = (api_key or "").strip()
        self._api_key: SecretStr | None = SecretStr(stripped) if stripped else None
        self._base_url = base_url.rstrip("/")
        self._transport = transport
        self._monotonic = monotonic

    # --- 配置 ---

    @property
    def configured(self) -> bool:
        """是否具备发送条件。密钥内容**不会**出现在返回值里。"""

        return self._api_key is not None

    def __repr__(self) -> str:  # pragma: no cover - 仅用于避免密钥进入日志
        return (
            f"{type(self).__name__}(profile={self.profile.name!r}, "
            f"base_url={self._base_url!r}, configured={self.configured})"
        )

    # --- 请求构造（可单独测试） ---

    def build_payload(self, request: ModelActionRequest) -> dict[str, Any]:
        """构造 Chat Completions 请求体（不含密钥）。"""

        params = request.params
        payload: dict[str, Any] = {
            "model": params.model,
            "messages": [{"role": "user", "content": request.prompt}],
            "stream": params.stream,
            "max_tokens": params.max_output_tokens,
        }
        if self.profile.include_response_format:
            payload["response_format"] = {"type": params.response_format}
        # 后端专属片段（DeepSeek 的 thinking 开关；本地服务不发）。
        payload.update(self.profile.payload_fragments(thinking_enabled=params.thinking_enabled))
        # 不发送 tools（PRD 2.2：运行聊天不发送 tools）。
        return payload

    # --- 调用 ---

    async def generate_action(self, request: ModelActionRequest) -> ModelActionResponse:
        prompt_template_id = request.prompt_template_id
        model = request.params.model

        def failure(
            kind: ModelFailureKind,
            detail: str,
            *,
            sent: bool,
            http_status: int | None = None,
            returned_model: str | None = None,
            raw_content: str | None = None,
            finish_reason: str | None = None,
            usage: Usage | None = None,
            latency_ms: int | None = None,
            provider_request_id: str | None = None,
        ) -> ModelActionResponse:
            return ModelActionResponse(
                ok=False,
                failure=ModelFailure(kind=kind, detail=detail, http_status=http_status),
                raw_content=raw_content,
                finish_reason=finish_reason,
                requested_model=model,
                returned_model=returned_model,
                prompt_template_id=prompt_template_id,
                provider_request_id=provider_request_id,
                usage=usage or Usage(),
                latency_ms=latency_ms,
                sent=sent,
            )

        # 1) 本地边界：上下文超限 → 不发送（PRD 5.3：不静默截断）。
        length = codepoint_length(request.prompt)
        if length > MAX_PROMPT_CHARS_LIMIT:
            return failure(
                ModelFailureKind.CONTEXT_LIMIT,
                f"prompt 长度 {length} 超过 max_prompt_chars={MAX_PROMPT_CHARS_LIMIT}",
                sent=False,
            )

        # 2) 本地边界：缺配置 → 不发送（PRD 5.3）。
        if self.profile.require_api_key and not self.configured:
            return failure(
                ModelFailureKind.MISSING_CONFIG,
                "未配置模型凭证，未发送任何请求",
                sent=False,
            )

        payload = self.build_payload(request)
        try:
            check_single_call_token_limit(payload["messages"], request.params.max_output_tokens)
        except SingleCallTokenLimitExceeded as exc:
            return failure(ModelFailureKind.CONTEXT_LIMIT, str(exc), sent=False)
        started = self._monotonic()

        timeout = httpx.Timeout(request.params.request_timeout_seconds)
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                transport=self._transport,
                timeout=timeout,
                # 关闭隐式重试：httpx 不自动重试，这里也不额外包装重试逻辑。
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    CHAT_COMPLETIONS_PATH,
                    json=payload,
                    headers=self._headers(),
                )
        except httpx.TimeoutException as exc:
            return failure(
                ModelFailureKind.TIMEOUT,
                f"请求超时：{exc.__class__.__name__}",
                sent=True,
                latency_ms=self._elapsed_ms(started),
            )
        except httpx.HTTPError as exc:
            # 网络层失败：请求可能已经送达，保守标记为发送结果不明。
            return failure(
                ModelFailureKind.UNKNOWN_REQUEST,
                f"网络异常，发送结果不明：{exc.__class__.__name__}",
                sent=False,
                latency_ms=self._elapsed_ms(started),
            )

        latency_ms = self._elapsed_ms(started)

        if response.status_code >= 400:
            return failure(
                ModelFailureKind.PROVIDER_ERROR,
                f"服务端返回 HTTP {response.status_code}：{self._short(response.text)}",
                sent=True,
                http_status=response.status_code,
                latency_ms=latency_ms,
            )

        try:
            body = response.json()
        except ValueError as exc:
            return failure(
                ModelFailureKind.PROVIDER_ERROR,
                f"响应不是合法 JSON：{exc}",
                sent=True,
                http_status=response.status_code,
                latency_ms=latency_ms,
            )

        return self._parse_response(
            body,
            request=request,
            scope=request.references,
            latency_ms=latency_ms,
            failure=failure,
        )

    # --- 响应解析 ---

    def _parse_response(
        self,
        body: Any,
        *,
        request: ModelActionRequest,
        scope,
        latency_ms: int,
        failure,
    ) -> ModelActionResponse:
        model = request.params.model
        if not isinstance(body, dict):
            return failure(
                ModelFailureKind.PROVIDER_ERROR,
                "响应顶层不是 JSON 对象",
                sent=True,
                latency_ms=latency_ms,
            )

        returned_model = body.get("model")
        provider_request_id = body.get("id")
        usage = self._usage_from(body.get("usage"))
        if actual_usage_exceeds_single_call_limit(usage.input_tokens, usage.output_tokens):
            return failure(
                ModelFailureKind.PROVIDER_ERROR,
                "供应商报告的单次 token 用量超过 10,000,000",
                sent=True,
                returned_model=returned_model,
                provider_request_id=provider_request_id,
                usage=usage,
                latency_ms=latency_ms,
            )

        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            return failure(
                ModelFailureKind.EMPTY_CONTENT,
                "响应中没有 choices",
                sent=True,
                returned_model=returned_model,
                provider_request_id=provider_request_id,
                usage=usage,
                latency_ms=latency_ms,
            )

        choice = choices[0] if isinstance(choices[0], dict) else {}
        finish_reason = choice.get("finish_reason")
        message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
        content = message.get("content")
        content_text = content if isinstance(content, str) else None

        outcome = parse_action_content(content_text, finish_reason=finish_reason, scope=scope)

        if isinstance(outcome, ModelFailure):
            return ModelActionResponse(
                ok=False,
                failure=outcome,
                raw_content=content_text,
                finish_reason=finish_reason,
                requested_model=model,
                returned_model=returned_model,
                prompt_template_id=request.prompt_template_id,
                provider_request_id=provider_request_id,
                usage=usage,
                latency_ms=latency_ms,
                sent=True,
            )

        return ModelActionResponse(
            ok=True,
            draft=outcome,
            raw_content=content_text,
            finish_reason=finish_reason,
            requested_model=model,
            returned_model=returned_model,
            prompt_template_id=request.prompt_template_id,
            provider_request_id=provider_request_id,
            usage=usage,
            latency_ms=latency_ms,
            sent=True,
        )

    @staticmethod
    def _usage_from(raw: Any) -> Usage:
        """用量以服务端返回为准；**缺失记为 unknown，不是 0**（PRD 5.3）。"""

        if not isinstance(raw, dict):
            return Usage()

        def pick(*keys: str) -> int | None:
            for key in keys:
                value = raw.get(key)
                if isinstance(value, int) and value >= 0:
                    return value
            return None

        return Usage(
            input_tokens=pick("prompt_tokens", "input_tokens"),
            output_tokens=pick("completion_tokens", "output_tokens"),
            cached_tokens=pick("prompt_cache_hit_tokens", "cached_tokens"),
        )

    def _headers(self) -> dict[str, str]:
        """请求头：只在有凭证时发送 Authorization（本地服务通常不需要）。"""

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            **self.profile.extra_headers,
        }
        if self._api_key is not None:
            headers["Authorization"] = f"Bearer {self._api_key.get_secret_value()}"
        return headers

    def _require_key(self) -> str:
        """取出密钥明文，仅用于构造 Authorization 头。"""

        assert self._api_key is not None  # 调用前已由 configured 检查保证
        return self._api_key.get_secret_value()

    def _elapsed_ms(self, started: float) -> int:
        return max(0, int((self._monotonic() - started) * 1000))

    @staticmethod
    def _short(text: str, limit: int = 300) -> str:
        return text if len(text) <= limit else f"{text[:limit]}…"


__all__ = [
    "CHAT_COMPLETIONS_PATH",
    "ChatProfile",
    "MAX_PROMPT_CHARS_LIMIT",
    "OpenAICompatibleChatClient",
]
