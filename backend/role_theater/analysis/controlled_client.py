"""受控兼容客户端（PRD 6.2）。

外部分析器在调用供应商模型时使用本客户端，从而由**本项目**决定：

- 显式 API 行为（模型名、``response_format``、关闭思考、不发 tools、不流式）；
- **关闭隐式重试**（只尝试一次，失败即上报，由上层决定是否重试）；
- **追踪使用量**（每次尝试与 token 用量都记录下来，缺失即 unknown）。

注意：受控客户端的兼容性**必须由真实联调证明**，不能假定所有供应商接口相同；
本环境不进行真实调用，因此它只在本模块的测试中用假传输层验证。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..contracts import Usage
from ..contracts.limits import (
    DEFAULT_MODEL_NAME,
    MAX_OUTPUT_TOKENS,
    RESPONSE_FORMAT_JSON_OBJECT,
    SDK_MAX_RETRIES,
    SEND_TOOLS,
    STREAM_BY_DEFAULT,
    THINKING_ENABLED_BY_DEFAULT,
)


@dataclass(slots=True)
class AttemptRecord:
    """一次供应商尝试的记录（不含密钥、不含认证头）。"""

    provider_attempt: int
    model: str
    ok: bool
    usage: Usage = field(default_factory=Usage)
    error: str | None = None


class ControlledAnalysisClient:
    """注入给外部分析器的受控客户端。

    ``transport`` 是``Callable[[dict], dict]``：接收请求片段，返回响应字典。
    生产环境下由 M03 的模型客户端承担；测试中注入假实现。
    """

    def __init__(
        self,
        *,
        transport=None,
        model: str = DEFAULT_MODEL_NAME,
        max_output_tokens: int = MAX_OUTPUT_TOKENS,
        thinking_enabled: bool = THINKING_ENABLED_BY_DEFAULT,
        stream: bool = STREAM_BY_DEFAULT,
        response_format: str = RESPONSE_FORMAT_JSON_OBJECT,
        send_tools: bool = SEND_TOOLS,
        sdk_max_retries: int = SDK_MAX_RETRIES,
    ) -> None:
        if sdk_max_retries != 0:  # pragma: no cover - 契约层已限制
            raise ValueError("受控客户端必须关闭隐式重试（sdk_max_retries=0）")
        self._transport = transport
        self.attempts: list[AttemptRecord] = []
        self.settings = {
            "model": model,
            "max_output_tokens": max_output_tokens,
            "thinking_enabled": thinking_enabled,
            "stream": stream,
            "response_format": response_format,
            "send_tools": send_tools,
            "sdk_max_retries": sdk_max_retries,
        }

    @property
    def provider_attempts(self) -> int:
        return len(self.attempts)

    @property
    def usage(self) -> Usage:
        """汇总各次尝试的用量；缺失记为 unknown（不是 0，PRD 5.3）。"""

        def total(values: list[int | None]) -> int | None:
            present = [value for value in values if value is not None]
            return sum(present) if present else None

        return Usage(
            input_tokens=total([attempt.usage.input_tokens for attempt in self.attempts]),
            output_tokens=total([attempt.usage.output_tokens for attempt in self.attempts]),
            cached_tokens=total([attempt.usage.cached_tokens for attempt in self.attempts]),
        )

    def build_request(self, *, prompt: str) -> dict:
        """显式构造请求片段；不发送 tools，不使用 temperature 推断思考模式。"""

        payload: dict = {
            "model": self.settings["model"],
            "stream": self.settings["stream"],
            "max_tokens": self.settings["max_output_tokens"],
            "response_format": {"type": self.settings["response_format"]},
            "messages": [{"role": "user", "content": prompt}],
        }
        payload["thinking"] = {
            "type": "enabled" if self.settings["thinking_enabled"] else "disabled"
        }
        return payload

    def create_completion(self, *, prompt: str) -> dict:
        """执行**一次**供应商调用；失败不重试，直接抛出。"""

        payload = self.build_request(prompt=prompt)
        attempt_number = len(self.attempts) + 1
        if self._transport is None:
            self.attempts.append(
                AttemptRecord(
                    provider_attempt=attempt_number,
                    model=self.settings["model"],
                    ok=False,
                    error="受控客户端未配置传输层",
                )
            )
            raise RuntimeError("受控客户端未配置传输层")

        try:
            response = self._transport(payload)
        except Exception as exc:
            self.attempts.append(
                AttemptRecord(
                    provider_attempt=attempt_number,
                    model=self.settings["model"],
                    ok=False,
                    error=f"{exc.__class__.__name__}: {exc}",
                )
            )
            raise

        self.attempts.append(
            AttemptRecord(
                provider_attempt=attempt_number,
                model=self.settings["model"],
                ok=True,
                usage=_usage_from(response.get("usage") if isinstance(response, dict) else None),
            )
        )
        return response


def _usage_from(raw) -> Usage:
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


__all__ = ["AttemptRecord", "ControlledAnalysisClient"]
