"""本地模型客户端（OpenAI 兼容端点；PRD 第 8 节「可替换模型适配器」）。

适配的本地推理服务（都提供 OpenAI 兼容的 ``/chat/completions``）：

| 服务 | 默认基地址 |
|---|---|
| Ollama | ``http://127.0.0.1:11434/v1`` |
| LM Studio | ``http://127.0.0.1:1234/v1`` |
| vLLM | ``http://127.0.0.1:8000/v1`` |
| llama.cpp（``llama-server``） | ``http://127.0.0.1:8080/v1`` |

与 DeepSeek 的三点差异（这是本地服务常见的坑）：

1. **不需要凭证**：因此不能沿用「没有密钥就回落 Mock」的规则，否则本地模型永远用不上；
2. **不发送 ``thinking``**：该字段是 DeepSeek 专有，多数本地实现会因未知字段直接报错；
3. **``response_format`` 可关闭**：部分实现的 JSON 模式支持不完整；关闭后仍由提示词
   约束「只返回 JSON」，解析与失败分类**不变**。

除以上三点，发送、解析、用量与失败分类与云服务**完全共用**
（:mod:`role_theater.ports.openai_chat`），不因换后端而放宽判定。
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

#: 常见本地服务的默认基地址（OpenAI 兼容路径需带 ``/v1``）。
OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"
LM_STUDIO_BASE_URL = "http://127.0.0.1:1234/v1"
VLLM_BASE_URL = "http://127.0.0.1:8000/v1"
LLAMA_CPP_BASE_URL = "http://127.0.0.1:8080/v1"

#: 本地默认基地址（Ollama 最常见）。
DEFAULT_LOCAL_BASE_URL = OLLAMA_BASE_URL

#: 本地模型的默认模型名（仅作占位，应按实际拉取的模型改写）。
DEFAULT_LOCAL_MODEL_NAME = "qwen2.5:7b"


def local_profile(*, include_response_format: bool = True) -> ChatProfile:
    """本地服务的请求差异：无 thinking、无凭证要求。"""

    return ChatProfile(
        name="local",
        thinking_payload=None,
        include_response_format=include_response_format,
        require_api_key=False,
    )


class LocalModelClient(OpenAICompatibleChatClient):
    """连接本机（或局域网内）OpenAI 兼容推理服务的客户端。"""

    profile = local_profile()

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        include_response_format: bool = True,
        monotonic=None,
    ) -> None:
        self.profile = local_profile(include_response_format=include_response_format)
        kwargs: dict[str, Any] = {
            # 本地服务通常不校验凭证；提供了就照常发送（部分网关需要）。
            "api_key": api_key,
            "base_url": base_url or DEFAULT_LOCAL_BASE_URL,
            "transport": transport,
        }
        if monotonic is not None:
            kwargs["monotonic"] = monotonic
        super().__init__(**kwargs)

    @property
    def endpoint(self) -> str:
        """完整的 Chat Completions 地址（不含凭证），便于排错时打印。"""

        return f"{self._base_url}{CHAT_COMPLETIONS_PATH}"


__all__ = [
    "CHAT_COMPLETIONS_PATH",
    "DEFAULT_LOCAL_BASE_URL",
    "DEFAULT_LOCAL_MODEL_NAME",
    "LLAMA_CPP_BASE_URL",
    "LM_STUDIO_BASE_URL",
    "MAX_PROMPT_CHARS_LIMIT",
    "OLLAMA_BASE_URL",
    "VLLM_BASE_URL",
    "LocalModelClient",
    "local_profile",
]
