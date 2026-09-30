"""FC-07: lengths and failure paths are enforced per scene on real adapter boundaries."""
import json
import pytest
from role_theater.contracts import ActionDraft, ModelFailure, ModelFailureKind, ReferenceScope, ModelParams
from role_theater.ports.action_parser import parse_action_content, validate_references
from test_m03_model_adapter import _client, _request, _completion, RecordingTransport


@pytest.mark.parametrize("version,limit", [(1, 200), (2, 1000)])
@pytest.mark.parametrize("action", ["SPEAK", "PRIVATE"])
def test_parser_enforces_scene_limit_and_mock_draft_cannot_bypass_it(version, limit, action):
    scope = ReferenceScope(actor_id="a", allowed_speaker_ids=["b"], chat_policy_version=version)
    fields = {"action": action, "text": "😀" * limit}
    if action == "PRIVATE":
        fields["recipient_id"] = "b"
    assert isinstance(parse_action_content(json.dumps(fields), scope=scope), ActionDraft)
    failure = parse_action_content(json.dumps({**fields, "text": "😀" * (limit + 1)}), scope=scope)
    assert isinstance(failure, ModelFailure) and failure.kind is ModelFailureKind.SCHEMA_INVALID
    if version == 1:
        draft = ActionDraft(**{**fields, "text": "字" * 201})
        assert validate_references(draft, scope).kind is ModelFailureKind.SCHEMA_INVALID


@pytest.mark.parametrize("version,output", [(1, 1024), (2, 4096)])
async def test_adapter_payload_and_success_for_each_scene_policy(version, output):
    text = "字" * (200 if version == 1 else 1000)
    transport = RecordingTransport([_completion("stop", json.dumps({"action": "SPEAK", "text": text}))])
    request = _request().model_copy(update={
        "chat_policy_version": version, "params": ModelParams(max_output_tokens=output),
        "references": ReferenceScope(actor_id="a", chat_policy_version=version),
    })
    response = await _client(transport).generate_action(request)
    assert response.ok and response.draft.text == text
    assert transport.payloads[0]["max_tokens"] == output
    assert "tools" not in transport.payloads[0]
    assert len(transport.requests) == 1


@pytest.mark.parametrize("raw,finish,kind", [
    ("", "stop", ModelFailureKind.EMPTY_CONTENT),
    ("{broken", "stop", ModelFailureKind.INVALID_JSON),
    ('{"action":"SPEAK","text":"正文"}', "length", ModelFailureKind.TRUNCATED),
    ('{"action":"SPEAK","text":"正文","reply_to_message_id":"hidden"}', "stop", ModelFailureKind.REFERENCE_INVALID),
])
async def test_new_policy_retains_strict_failures_without_repair_request(raw, finish, kind):
    transport = RecordingTransport([_completion(finish, raw)])
    request = _request().model_copy(update={"chat_policy_version": 2, "references": ReferenceScope(actor_id="a", chat_policy_version=2)})
    response = await _client(transport).generate_action(request)
    assert not response.ok and response.failure.kind is kind
    assert len(transport.requests) == 1


async def test_request_policy_controls_length_without_reference_scope():
    transport = RecordingTransport([_completion("stop", json.dumps({"action": "SPEAK", "text": "字" * 1000}))])
    request = _request().model_copy(update={"chat_policy_version": 2, "references": None})
    response = await _client(transport).generate_action(request)
    assert response.ok and len(response.draft.text) == 1000


def test_mismatched_request_and_reference_policy_is_rejected():
    from pydantic import ValidationError
    from role_theater.contracts import ModelActionRequest
    with pytest.raises(ValidationError, match="策略版本不一致"):
        ModelActionRequest.model_validate({**_request().model_dump(), "chat_policy_version": 1,
                                           "references": ReferenceScope(actor_id="a", chat_policy_version=2).model_dump()})


@pytest.mark.parametrize('version,length,ok', [(1, 200, True), (1, 201, False), (2, 1000, True)])
async def test_mock_without_reference_scope_still_enforces_request_policy(version, length, ok):
    from role_theater.ports import MockModelPort
    port = MockModelPort(script=[ActionDraft(action='SPEAK', text='字' * length)])
    request = _request().model_copy(update={'chat_policy_version': version, 'references': None})
    result = await port.generate_action(request)
    assert result.ok is ok
    if not ok:
        assert result.failure.kind is ModelFailureKind.SCHEMA_INVALID
    assert port.call_count == 1
