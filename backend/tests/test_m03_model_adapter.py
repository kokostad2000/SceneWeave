"""M03 模型适配（PRD 2.2、4.2、5.3；tasks/M03.md A1–A12）。

全部用例通过 ``httpx.MockTransport`` 运行：**不联网、不需要密钥**，同时验证
真实请求体、失败分类与"关闭隐式重试"。
"""

from __future__ import annotations

import json

import httpx
import pytest

from role_theater.contracts import (
    ActionDraft,
    ActionType,
    ModelActionRequest,
    ModelFailureKind,
    ModelParams,
    ReferenceScope,
)
from role_theater.ports import (
    DeepSeekModelClient,
    MockModelPort,
    ModelPort,
    build_model_port,
    parse_action_content,
    validate_references,
)


def _request(
    *,
    prompt: str = "共同情境……",
    params: ModelParams | None = None,
    references: ReferenceScope | None = None,
) -> ModelActionRequest:
    return ModelActionRequest(
        scene_id="scn-1",
        actor_id="agt-an",
        prompt_template_id="role_action@m02",
        prompt=prompt,
        cursor_seq=3,
        params=params or ModelParams(max_output_tokens=1024),
        references=references,
    )


class RecordingTransport(httpx.AsyncBaseTransport):
    """记录请求并返回预设响应的传输层（替代真实网络）。"""

    def __init__(self, responses: list[httpx.Response] | None = None, *, exc: Exception | None = None):
        self.requests: list[httpx.Request] = []
        self.payloads: list[dict] = []
        self._responses = list(responses or [])
        self._exc = exc

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        self.payloads.append(json.loads(request.content.decode("utf-8")))
        if self._exc is not None:
            raise self._exc
        if self._responses:
            return self._responses.pop(0)
        return _completion("stop", '{"action": "PASS", "text": "", "reply_to_message_id": null, "requested_speaker_id": null}')


def _completion(
    finish_reason: str,
    content: str | None,
    *,
    model: str = "deepseek-flash-2026-09-10",
    usage: dict | None = None,
    request_id: str = "req-abc",
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": request_id,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": finish_reason,
                    "message": {"role": "assistant", "content": content},
                }
            ],
            "usage": usage if usage is not None else {"prompt_tokens": 120, "completion_tokens": 18},
        },
    )


def _client(transport: httpx.AsyncBaseTransport, *, api_key: str = "placeholder-key") -> DeepSeekModelClient:
    return DeepSeekModelClient(api_key=api_key, transport=transport)


# --- A1 请求参数 ---------------------------------------------------------------


async def test_request_payload_matches_prd_defaults() -> None:
    transport = RecordingTransport()
    client = _client(transport)

    await client.generate_action(_request())

    assert len(transport.payloads) == 1
    payload = transport.payloads[0]
    assert payload["model"] == "deepseek-flash"
    assert payload["stream"] is False
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["max_tokens"] == 1024
    assert "tools" not in payload, "运行聊天不得发送 tools"
    assert "tool_choice" not in payload
    assert payload["thinking"] == {"type": "disabled"}, "必须显式关闭思考"
    assert "temperature" not in payload, "不得靠 temperature 推断思考已关闭"
    assert "reasoning_effort" not in payload, "不得发送 reasoning_effort=100"
    assert payload["messages"][0]["content"] == "共同情境……"


async def test_request_targets_chat_completions_with_bearer_auth() -> None:
    transport = RecordingTransport()
    client = _client(transport, api_key="placeholder-key")

    await client.generate_action(_request())

    request = transport.requests[0]
    assert request.url.path.endswith("/chat/completions")
    assert request.headers["authorization"] == "Bearer placeholder-key"
    assert request.headers["content-type"] == "application/json"


async def test_tools_are_never_sent_even_when_params_change_other_fields() -> None:
    transport = RecordingTransport()
    client = _client(transport)

    await client.generate_action(
        _request(params=ModelParams(model="deepseek-v4-flash", max_output_tokens=256))
    )

    payload = transport.payloads[0]
    assert payload["model"] == "deepseek-v4-flash"
    assert payload["max_tokens"] == 256
    assert "tools" not in payload


async def test_single_call_token_limit_rejects_before_network() -> None:
    transport = RecordingTransport()
    response = await _client(transport).generate_action(
        _request(params=ModelParams(max_output_tokens=10_000_000))
    )

    assert response.ok is False
    assert response.failure is not None
    assert response.failure.kind is ModelFailureKind.CONTEXT_LIMIT
    assert response.sent is False
    assert transport.requests == []


async def test_provider_reported_token_limit_overrun_is_failure() -> None:
    transport = RecordingTransport([
        _completion(
            "stop", '{"action":"PASS","text":"","reply_to_message_id":null,"requested_speaker_id":null}',
            usage={"prompt_tokens": 9_999_999, "completion_tokens": 2},
        )
    ])
    response = await _client(transport).generate_action(_request())

    assert response.ok is False
    assert response.failure is not None
    assert response.failure.kind is ModelFailureKind.PROVIDER_ERROR
    assert response.usage.input_tokens == 9_999_999
    assert response.usage.output_tokens == 2


async def test_thinking_enabled_switches_the_explicit_flag() -> None:
    transport = RecordingTransport()
    client = _client(transport)

    await client.generate_action(_request(params=ModelParams(thinking_enabled=True)))

    assert transport.payloads[0]["thinking"] == {"type": "enabled"}


# --- A2 成功解析与用量 ---------------------------------------------------------


async def test_successful_speak_is_parsed_and_usage_recorded() -> None:
    transport = RecordingTransport(
        [
            _completion(
                "stop",
                '{"action": "SPEAK", "text": "今晚一起吃饭吗？", "reply_to_message_id": null, "requested_speaker_id": null}',
                usage={"prompt_tokens": 321, "completion_tokens": 12, "prompt_cache_hit_tokens": 64},
            )
        ]
    )

    response = await _client(transport).generate_action(_request())

    assert response.ok is True
    assert response.draft is not None
    assert response.draft.action is ActionType.SPEAK
    assert response.draft.text == "今晚一起吃饭吗？"
    # 记录请求模型名与**服务端返回**模型名（PRD 2.2）。
    assert response.requested_model == "deepseek-flash"
    assert response.returned_model == "deepseek-flash-2026-09-10"
    assert response.prompt_template_id == "role_action@m02"
    assert response.provider_request_id == "req-abc"
    assert response.usage.input_tokens == 321
    assert response.usage.output_tokens == 12
    assert response.usage.cached_tokens == 64
    assert response.latency_ms is not None and response.latency_ms >= 0
    assert response.sent is True


async def test_missing_usage_is_unknown_not_zero() -> None:
    transport = RecordingTransport([_completion("stop", '{"action": "PASS"}', usage={})])

    response = await _client(transport).generate_action(_request())

    assert response.ok is True
    assert response.usage.is_unknown
    assert response.usage.input_tokens is None


async def test_successful_pass_is_accepted() -> None:
    transport = RecordingTransport([_completion("stop", '{"action": "PASS"}')])

    response = await _client(transport).generate_action(_request())

    assert response.ok is True
    assert response.draft is not None
    assert response.draft.action is ActionType.PASS


# --- A3 失败分类 ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "finish_reason", "expected"),
    [
        (None, "stop", ModelFailureKind.EMPTY_CONTENT),
        ("", "stop", ModelFailureKind.EMPTY_CONTENT),
        ("   \n  ", "stop", ModelFailureKind.EMPTY_CONTENT),
        ("{}", "length", ModelFailureKind.TRUNCATED),
        ("不是 JSON", "stop", ModelFailureKind.INVALID_JSON),
        ('{"action": "SHOUT", "text": "喂"}', "stop", ModelFailureKind.SCHEMA_INVALID),
        ('{"action": "SPEAK", "text": ""}', "stop", ModelFailureKind.SCHEMA_INVALID),
        ('{"action": "SPEAK", "text": "' + "字" * 201 + '"}', "stop", ModelFailureKind.SCHEMA_INVALID),
        ('{"action": "PASS", "text": "我不想说话"}', "stop", ModelFailureKind.SCHEMA_INVALID),
        ('{"action": "SPEAK", "text": "好", "thought": "内心独白"}', "stop", ModelFailureKind.SCHEMA_INVALID),
        ('{"action": "SPEAK", "text": "好", "actor_id": "agt-xu"}', "stop", ModelFailureKind.SCHEMA_INVALID),
        ("[1, 2, 3]", "stop", ModelFailureKind.SCHEMA_INVALID),
    ],
)
async def test_content_failures_are_classified_not_silently_fixed(
    content, finish_reason, expected: ModelFailureKind
) -> None:
    transport = RecordingTransport([_completion(finish_reason, content)])

    response = await _client(transport).generate_action(_request())

    assert response.ok is False
    assert response.draft is None
    assert response.failure is not None
    assert response.failure.kind is expected
    assert response.sent is True


@pytest.mark.parametrize(
    ("finish_reason", "expected"),
    [
        ("length", ModelFailureKind.TRUNCATED),
        ("content_filter", ModelFailureKind.PROVIDER_ERROR),
        ("insufficient_system_resource", ModelFailureKind.PROVIDER_ERROR),
        ("aborted", ModelFailureKind.PROVIDER_ERROR),
        ("tool_calls", ModelFailureKind.PROVIDER_ERROR),
    ],
)
async def test_every_abnormal_finish_reason_is_classified_explicitly(
    finish_reason: str, expected: ModelFailureKind
) -> None:
    """官方文档列出的异常 finish_reason 必须各有分类，而不是笼统的“空 content”。"""

    transport = RecordingTransport([_completion(finish_reason, None)])

    response = await _client(transport).generate_action(_request())

    assert response.ok is False
    assert response.failure is not None
    assert response.failure.kind is expected
    assert finish_reason in response.failure.detail


async def test_abnormal_finish_reason_wins_over_empty_content() -> None:
    """服务端未正常完成时先报原因（content 为空是结果，不是原因）。"""

    transport = RecordingTransport([_completion("aborted", "")])

    response = await _client(transport).generate_action(_request())

    assert response.failure is not None
    assert response.failure.kind is ModelFailureKind.PROVIDER_ERROR


async def test_normal_stop_with_empty_content_is_still_empty_content() -> None:
    transport = RecordingTransport([_completion("stop", "")])

    response = await _client(transport).generate_action(_request())

    assert response.failure is not None
    assert response.failure.kind is ModelFailureKind.EMPTY_CONTENT


async def test_thinking_field_matches_the_official_contract() -> None:
    """官方文档确认 thinking 为 {"type": "enabled"|"disabled"}，默认 enabled。

    来源：DeepSeek Chat Completions API 文档（docs/SOURCES.md）。
    """

    transport = RecordingTransport()
    client = _client(transport)

    await client.generate_action(_request())

    assert transport.payloads[0]["thinking"] == {"type": "disabled"}
    assert "reasoning_effort" not in transport.payloads[0], "不得发送 reasoning_effort"


async def test_truncated_output_is_never_accepted_even_if_parseable() -> None:
    """finish_reason=length 优先于内容合法性（PRD 4.2）。"""

    transport = RecordingTransport([_completion("length", '{"action": "PASS"}')])

    response = await _client(transport).generate_action(_request())

    assert response.ok is False
    assert response.failure is not None
    assert response.failure.kind is ModelFailureKind.TRUNCATED
    assert response.finish_reason == "length"


async def test_http_error_becomes_provider_error_with_status() -> None:
    transport = RecordingTransport([httpx.Response(500, text="internal error")])

    response = await _client(transport).generate_action(_request())

    assert response.ok is False
    assert response.failure is not None
    assert response.failure.kind is ModelFailureKind.PROVIDER_ERROR
    assert response.failure.http_status == 500


async def test_timeout_is_classified() -> None:
    transport = RecordingTransport(exc=httpx.ReadTimeout("too slow"))

    response = await _client(transport).generate_action(_request())

    assert response.failure is not None
    assert response.failure.kind is ModelFailureKind.TIMEOUT


async def test_network_error_is_marked_unknown_and_not_retried() -> None:
    transport = RecordingTransport(exc=httpx.ConnectError("connection reset"))

    response = await _client(transport).generate_action(_request())

    assert response.sent is False
    assert response.failure is not None
    assert response.failure.kind is ModelFailureKind.UNKNOWN_REQUEST


async def test_response_that_is_not_json_object_is_provider_error() -> None:
    transport = RecordingTransport([httpx.Response(200, text="<html>oops</html>")])

    response = await _client(transport).generate_action(_request())

    assert response.failure is not None
    assert response.failure.kind is ModelFailureKind.PROVIDER_ERROR


async def test_empty_choices_is_empty_content() -> None:
    transport = RecordingTransport([httpx.Response(200, json={"id": "r", "choices": []})])

    response = await _client(transport).generate_action(_request())

    assert response.failure is not None
    assert response.failure.kind is ModelFailureKind.EMPTY_CONTENT


# --- A4 关闭隐式重试 -----------------------------------------------------------


async def test_no_implicit_retry_on_failure() -> None:
    """服务端连续报错时只发送一次（PRD 2.2：SDK 自动重试为零）。"""

    transport = RecordingTransport(
        [httpx.Response(500, text="boom"), httpx.Response(500, text="boom again")]
    )

    response = await _client(transport).generate_action(_request())

    assert response.ok is False
    assert len(transport.requests) == 1, "不得自动重试"


async def test_params_force_zero_retries() -> None:
    params = ModelParams()

    assert params.sdk_max_retries == 0
    with pytest.raises(Exception):
        ModelParams(sdk_max_retries=3)


# --- A5 本地拒绝不发送 ---------------------------------------------------------


async def test_context_limit_is_refused_before_sending() -> None:
    transport = RecordingTransport()
    client = _client(transport)
    huge = ModelActionRequest.model_construct(
        scene_id="scn-1",
        actor_id="agt-an",
        prompt_template_id="role_action@m02",
        prompt="字" * 40_000,
        cursor_seq=0,
        params=ModelParams(max_output_tokens=1024),
        references=None,
    )

    response = await client.generate_action(huge)

    assert response.sent is False, "本地拒绝不得占用预算"
    assert response.failure is not None
    assert response.failure.kind is ModelFailureKind.CONTEXT_LIMIT
    assert transport.requests == [], "超限时不得发送"


async def test_missing_config_is_refused_before_sending() -> None:
    transport = RecordingTransport()
    client = DeepSeekModelClient(api_key=None, transport=transport)

    response = await client.generate_action(_request())

    assert response.sent is False
    assert response.failure is not None
    assert response.failure.kind is ModelFailureKind.MISSING_CONFIG
    assert transport.requests == []

    assert client.configured is False
    assert "placeholder" not in repr(client)


async def test_repr_and_attributes_never_leak_the_key() -> None:
    client = DeepSeekModelClient(api_key="placeholder-secret-value")

    assert "placeholder-secret-value" not in repr(client)
    assert "placeholder-secret-value" not in str(client.__dict__)


# --- A6 引用校验 ---------------------------------------------------------------


def test_reply_reference_must_be_an_allowed_message() -> None:
    scope = ReferenceScope(
        actor_id="agt-an",
        allowed_message_ids=["msg-1"],
        allowed_speaker_ids=["agt-xu"],
    )
    request = _request(references=scope)

    payload = {
        "action": "SPEAK",
        "text": "回应一下。",
        "reply_to_message_id": "msg-1",
        "requested_speaker_id": "agt-xu",
    }
    assert parse_action_content(json.dumps(payload), scope=scope).action is ActionType.SPEAK  # type: ignore[union-attr]

    payload["reply_to_message_id"] = "msg-999"
    outcome = parse_action_content(json.dumps(payload), scope=scope)
    assert outcome.kind is ModelFailureKind.REFERENCE_INVALID  # type: ignore[union-attr]
    assert request.references is scope


def test_requested_speaker_must_be_another_valid_role() -> None:
    scope = ReferenceScope(actor_id="agt-an", allowed_message_ids=[], allowed_speaker_ids=["agt-xu"])

    unknown = parse_action_content(
        '{"action": "SPEAK", "text": "你来。", "requested_speaker_id": "agt-999"}', scope=scope
    )
    assert unknown.kind is ModelFailureKind.REFERENCE_INVALID  # type: ignore[union-attr]

    oneself = parse_action_content(
        '{"action": "SPEAK", "text": "我来。", "requested_speaker_id": "agt-an"}', scope=scope
    )
    assert oneself.kind is ModelFailureKind.REFERENCE_INVALID  # type: ignore[union-attr]


def test_reference_validation_skipped_without_scope() -> None:
    draft = ActionDraft.model_validate(
        {"action": "SPEAK", "text": "好。", "reply_to_message_id": "msg-anything"}
    )

    assert validate_references(draft, None) is None


# --- A6b 序号别名解析（真实联调回归） ------------------------------------------


def _seq_scope() -> ReferenceScope:
    """模拟 M04 构建的范围：消息 ID 与序号别名指向同一批发言。"""

    return ReferenceScope(
        actor_id="agt-xu",
        allowed_message_ids=["msg_a1", "msg_b2"],
        allowed_message_seqs={1: "msg_a1", 2: "msg_b2"},
        allowed_speaker_ids=["agt-an"],
    )


@pytest.mark.parametrize("alias", [1, "1", "#1", "[#1]", " 1 "])
def test_seq_alias_resolves_to_the_real_message_id(alias: object) -> None:
    """模型把提示词里的 ``[#1]`` 回成序号时，必须解析成真实消息 ID 而不是报错。"""

    payload = {"action": "SPEAK", "text": "回应一下。", "reply_to_message_id": alias}
    outcome = parse_action_content(json.dumps(payload), scope=_seq_scope())

    assert isinstance(outcome, ActionDraft)
    assert outcome.reply_to_message_id == "msg_a1"


def test_seq_alias_out_of_range_is_an_invalid_reference_not_a_type_error() -> None:
    """序号越界要说清是引用非法，而不是笼统的字段类型错误。"""

    payload = {"action": "SPEAK", "text": "回应一下。", "reply_to_message_id": 99}
    outcome = parse_action_content(json.dumps(payload), scope=_seq_scope())

    assert outcome.kind is ModelFailureKind.REFERENCE_INVALID  # type: ignore[union-attr]


def test_real_message_id_still_wins_over_alias_lookup() -> None:
    """已经给出真实 ID 的值不做任何改写。"""

    payload = {"action": "SPEAK", "text": "回应一下。", "reply_to_message_id": "msg_b2"}
    outcome = parse_action_content(json.dumps(payload), scope=_seq_scope())

    assert outcome.reply_to_message_id == "msg_b2"  # type: ignore[union-attr]


def test_seq_alias_without_a_seq_table_keeps_the_strict_type_error() -> None:
    """没有序号表（例如旧调用方）时不得放宽：int 依旧按字段类型失败。"""

    scope = ReferenceScope(actor_id="agt-xu", allowed_message_ids=["msg_a1"])
    payload = {"action": "SPEAK", "text": "回应一下。", "reply_to_message_id": 1}
    outcome = parse_action_content(json.dumps(payload), scope=scope)

    assert outcome.kind is ModelFailureKind.SCHEMA_INVALID  # type: ignore[union-attr]


def test_boolean_is_never_treated_as_a_seq_alias() -> None:
    payload = {"action": "SPEAK", "text": "回应一下。", "reply_to_message_id": True}
    outcome = parse_action_content(json.dumps(payload), scope=_seq_scope())

    assert outcome.kind is ModelFailureKind.SCHEMA_INVALID  # type: ignore[union-attr]


async def test_client_applies_reference_scope_from_request() -> None:
    transport = RecordingTransport(
        [
            _completion(
                "stop",
                '{"action": "SPEAK", "text": "我吗？", "reply_to_message_id": "msg-404"}',
            )
        ]
    )
    scope = ReferenceScope(actor_id="agt-an", allowed_message_ids=["msg-1"], allowed_speaker_ids=[])

    response = await _client(transport).generate_action(_request(references=scope))

    assert response.ok is False
    assert response.failure is not None
    assert response.failure.kind is ModelFailureKind.REFERENCE_INVALID


# --- A7 端口工厂 ---------------------------------------------------------------


def test_factory_returns_mock_without_credentials() -> None:
    port = build_model_port(api_key=None)

    assert isinstance(port, MockModelPort)
    assert isinstance(port, ModelPort)


def test_factory_returns_mock_when_forced_even_with_credentials() -> None:
    port = build_model_port(api_key="placeholder-key", force_mock=True)

    assert isinstance(port, MockModelPort)


def test_factory_returns_deepseek_client_with_credentials() -> None:
    port = build_model_port(
        api_key="placeholder-key",
        base_url="http://127.0.0.1:9/never-called",
        transport=RecordingTransport(),
    )

    assert isinstance(port, DeepSeekModelClient)
    assert port.configured is True
    assert isinstance(port, ModelPort)


def test_empty_string_credential_is_treated_as_missing() -> None:
    assert isinstance(build_model_port(api_key="   "), MockModelPort)
