"""真实端口共用的单次 token 上限边界。"""

from __future__ import annotations

import json

import pytest

from role_theater.ports.token_limit import (
    MAX_SINGLE_CALL_TOKENS,
    MESSAGE_OVERHEAD_RESERVE,
    SingleCallTokenLimitExceeded,
    actual_usage_exceeds_single_call_limit,
    check_single_call_token_limit,
)


def test_single_call_limit_accepts_boundary_and_rejects_next_token() -> None:
    messages = [{"role": "user", "content": "测试"}]
    encoded_bytes = len(json.dumps(messages, ensure_ascii=False, separators=(",", ":")).encode())
    max_output = MAX_SINGLE_CALL_TOKENS - MESSAGE_OVERHEAD_RESERVE - encoded_bytes

    check_single_call_token_limit(messages, max_output)
    with pytest.raises(SingleCallTokenLimitExceeded):
        check_single_call_token_limit(messages, max_output + 1)


def test_single_call_limit_rejects_unknown_output_bound() -> None:
    with pytest.raises(SingleCallTokenLimitExceeded):
        check_single_call_token_limit([{"role": "user", "content": "测试"}], None)


def test_reported_input_and_output_are_checked_as_one_call() -> None:
    assert actual_usage_exceeds_single_call_limit(6_000_000, 4_000_001)
    assert not actual_usage_exceeds_single_call_limit(6_000_000, 4_000_000)
    assert not actual_usage_exceeds_single_call_limit(None, 4_000_001)
