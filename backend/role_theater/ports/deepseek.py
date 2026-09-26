"""DeepSeek Chat Completions 客户端（PRD 2.2、4.2、5.3）。

首版固定行为：

- 接口：Chat Completions；``model=deepseek-flash``（可配置）
- ``stream=false``、``response_format={"type": "json_object"}``、**不发送 tools**
- **显式关闭思考**（PRD 2.2 要求显式关闭，且不能用较低 temperature 推断已关闭）
- 请求总期限 90 秒；**关闭隐式重试**（httpx 默认不重试，且这里也不自行重试）
- 记录请求模型名、服务端返回模型名、参数、提示模板标识、请求 ID 与用量

``thinking`` 字段的名称与取值已按官方 Chat Completions 文档核对
（``{"type": "enabled" | "disabled"}``，默认 ``enabled``），来源见 `docs/SOURCES.md`。
它仍集中在 :data:`DEFAULT_THINKING_DISABLED_PAYLOAD`，便于整体替换。

共用机制在 :mod:`role_theater.ports.openai_chat`；本模块只提供 DeepSeek 的 profile。
"""

from __future__ import annotations

from typing import Any

import httpx

from .openai_chat import (
    CHAT_COMPLETIONS_PATH,
    MAX_PROMPT_CHARS_LIMIT,
    ChatProfile,
    OpenAICompatibleChatClient,
)

DEFAULT_BASE_URL = "https://api.deepseek.com"

#: 显式关闭思考的请求片段（PRD 2.2）。
DEFAULT_THINKING_DISABLED_PAYLOAD: dict[str, Any] = {"thinking": {"type": "disabled"}}
DEFAULT_THINKING_ENABLED_PAYLOAD: dict[str, Any] = {"thinking": {"type": "enabled"}}

#: DeepSeek 的请求差异：必须发送 thinking 开关，且必须有凭证。
DEEPSEEK_PROFILE = ChatProfile(
    name="deepseek",
    thinking_payload=DEFAULT_THINKING_DISABLED_PAYLOAD,
    thinking_enabled_payload=DEFAULT_THINKING_ENABLED_PAYLOAD,
    include_response_format=True,
    require_api_key=True,
)


class DeepSeekModelClient(OpenAICompatibleChatClient):
    """实现 :class:`role_theater.ports.model.ModelPort`（DeepSeek 云服务）。"""

    profile = DEEPSEEK_PROFILE

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        thinking_disabled_payload: dict[str, Any] | None = None,
        thinking_enabled_payload: dict[str, Any] | None = None,
        monotonic=None,
    ) -> None:
        # 允许整体替换 thinking 片段（便于契约变化时一次性切换）。
        if thinking_disabled_payload is not None or thinking_enabled_payload is not None:
            self.profile = ChatProfile(
                name=DEEPSEEK_PROFILE.name,
                thinking_payload=dict(thinking_disabled_payload)
                if thinking_disabled_payload is not None
                else DEEPSEEK_PROFILE.thinking_payload,
                thinking_enabled_payload=dict(thinking_enabled_payload)
                if thinking_enabled_payload is not None
                else DEEPSEEK_PROFILE.thinking_enabled_payload,
                include_response_format=DEEPSEEK_PROFILE.include_response_format,
                require_api_key=DEEPSEEK_PROFILE.require_api_key,
            )
        kwargs: dict[str, Any] = {
            "api_key": api_key,
            "base_url": base_url or DEFAULT_BASE_URL,
            "transport": transport,
        }
        if monotonic is not None:
            kwargs["monotonic"] = monotonic
        super().__init__(**kwargs)


__all__ = [
    "CHAT_COMPLETIONS_PATH",
    "DEEPSEEK_PROFILE",
    "DEFAULT_BASE_URL",
    "DEFAULT_THINKING_DISABLED_PAYLOAD",
    "DEFAULT_THINKING_ENABLED_PAYLOAD",
    "MAX_PROMPT_CHARS_LIMIT",
    "DeepSeekModelClient",
]
