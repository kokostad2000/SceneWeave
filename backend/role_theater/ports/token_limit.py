"""单次真实模型请求的应用侧 token 上界。

只发送文本。UTF-8 字节数大于通常的文本 token 数，并预留消息包装开销；
供应商返回的 usage 仍是实际用量的事实来源。此检查在构造认证头或发送前运行。
"""

from __future__ import annotations

import json
from typing import Any

MAX_SINGLE_CALL_TOKENS = 10_000_000
MESSAGE_OVERHEAD_RESERVE = 4_096


class SingleCallTokenLimitExceeded(ValueError):
    """请求的保守输入上界与最大输出之和超过单次额度。"""


def check_single_call_token_limit(messages: Any, max_output_tokens: Any) -> None:
    """拒绝无法确认上界的请求；错误信息不包含原始消息。"""

    if (
        not isinstance(max_output_tokens, int)
        or isinstance(max_output_tokens, bool)
        or max_output_tokens < 1
    ):
        raise SingleCallTokenLimitExceeded("单次模型请求缺少有效的 max_tokens")
    try:
        message_bytes = len(
            json.dumps(messages, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
    except (TypeError, ValueError) as exc:
        raise SingleCallTokenLimitExceeded("单次模型请求的消息无法计算 token 上界") from exc

    conservative_upper_bound = (
        message_bytes + MESSAGE_OVERHEAD_RESERVE + max_output_tokens
    )
    if conservative_upper_bound > MAX_SINGLE_CALL_TOKENS:
        raise SingleCallTokenLimitExceeded(
            f"单次模型请求的保守上界 {conservative_upper_bound} 超过 "
            f"{MAX_SINGLE_CALL_TOKENS} tokens"
        )


def actual_usage_exceeds_single_call_limit(
    input_tokens: int | None, output_tokens: int | None,
) -> bool:
    """只有服务端同时给出输入与输出用量时，才能判定实际是否超限。"""

    return (
        input_tokens is not None
        and output_tokens is not None
        and input_tokens + output_tokens > MAX_SINGLE_CALL_TOKENS
    )
