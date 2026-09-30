import json
import pytest
from role_theater.contracts import ActionDraft, ModelFailure, ReferenceScope
from role_theater.ports.action_parser import parse_action_content

SCOPE = ReferenceScope(actor_id="b", allowed_speaker_ids=["a", "c"], allowed_message_ids=["pub"],
    allowed_message_seqs={2: "pub"}, received_private_messages={"ab": "a", "cb": "c"}, private_message_seqs={1: "ab", 3: "cb"})

@pytest.mark.parametrize("action,recipient,reply,ok", [
    ("PRIVATE", "a", None, True), ("PRIVATE", "a", "ab", True), ("PRIVATE", "a", "#1", True),
    ("PRIVATE", "c", "cb", True), ("PRIVATE", "a", "cb", False), ("PRIVATE", "a", "pub", False),
    ("PRIVATE", "b", None, False), ("PRIVATE", "outside", None, False),
    ("PRIVATE", "a", "own", False), ("PRIVATE", "a", "future", False),
    ("SPEAK", None, "ab", False), ("SPEAK", None, "#1", False), ("SPEAK", None, "#2", True),
    ("PRIVATE", "a", "#2", False), ("PRIVATE", "a", "#999", False),
])
def test_pc_reference_channels(action, recipient, reply, ok):
    result = parse_action_content(json.dumps(dict(action=action, text="hi", recipient_id=recipient,
        reply_to_message_id=reply, requested_speaker_id=None)), scope=SCOPE)
    assert isinstance(result, ActionDraft if ok else ModelFailure)
    if not ok: assert result.kind == "REFERENCE_INVALID"

@pytest.mark.parametrize("action,recipient,reply,text", [
    ("PRIVATE", "a", "ab", "hi"), ("PRIVATE", "c", None, "relay"),
    ("SPEAK", None, None, "public relay"), ("PASS", None, None, ""),
])
def test_pc_recipient_can_choose_four_actions(action, recipient, reply, text):
    result = parse_action_content(json.dumps(dict(action=action, text=text, recipient_id=recipient,
        reply_to_message_id=reply)), scope=SCOPE)
    assert isinstance(result, ActionDraft)
