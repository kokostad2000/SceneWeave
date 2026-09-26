"""行动协议契约（PRD 4.2）。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from role_theater.contracts import (
    ActionDraft,
    ActionRecord,
    ActionType,
    TurnStatus,
    codepoint_length,
)


def test_speak_minimal_is_valid() -> None:
    draft = ActionDraft(action=ActionType.SPEAK, text="今晚要不要一起吃饭？")

    assert draft.text == "今晚要不要一起吃饭？"
    assert draft.reply_to_message_id is None
    assert draft.requested_speaker_id is None


def test_speak_trims_whitespace_before_length_check() -> None:
    draft = ActionDraft(action=ActionType.SPEAK, text="   你好   ")
    assert draft.text == "你好"


@pytest.mark.parametrize("bad", ["", "   ", "\n\t "])
def test_speak_rejects_empty_text(bad: str) -> None:
    with pytest.raises(ValidationError):
        ActionDraft(action=ActionType.SPEAK, text=bad)


def test_speak_accepts_exactly_200_codepoints_and_rejects_201() -> None:
    allowed = "字" * 200
    assert codepoint_length(allowed) == 200
    ActionDraft(action=ActionType.SPEAK, text=allowed)

    with pytest.raises(ValidationError):
        ActionDraft(action=ActionType.SPEAK, text="字" * 201)


def test_speak_length_uses_unicode_codepoints_not_utf16_units() -> None:
    """前后端必须统一按码点计数（PRD 3.3）。"""

    emoji = "😀"
    assert codepoint_length(emoji) == 1
    assert len(emoji.encode("utf-16-le")) // 2 == 2  # UTF-16 长度会是 2

    ActionDraft(action=ActionType.SPEAK, text=emoji * 200)
    with pytest.raises(ValidationError):
        ActionDraft(action=ActionType.SPEAK, text=emoji * 201)


def test_pass_must_be_completely_empty() -> None:
    ActionDraft(action=ActionType.PASS)

    with pytest.raises(ValidationError):
        ActionDraft(action=ActionType.PASS, text="我不想说话")
    with pytest.raises(ValidationError):
        ActionDraft(action=ActionType.PASS, reply_to_message_id="m-1")
    with pytest.raises(ValidationError):
        ActionDraft(action=ActionType.PASS, requested_speaker_id="a-2")


def test_extra_fields_are_rejected_not_ignored() -> None:
    with pytest.raises(ValidationError):
        ActionDraft.model_validate(
            {"action": "SPEAK", "text": "你好", "actor_id": "a-1"}  # 服务端才加 actor_id
        )
    with pytest.raises(ValidationError):
        ActionDraft.model_validate({"action": "SPEAK", "text": "你好", "thought": "内心独白"})


def test_unknown_action_enum_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ActionDraft.model_validate({"action": "SHOUT", "text": "喂"})


def test_record_requires_draft_only_when_succeeded() -> None:
    from datetime import UTC, datetime

    base = {
        "action_id": "act-1",
        "turn_id": "turn-1",
        "attempt_id": "attempt-1",
        "scene_id": "scene-1",
        "actor_id": "agent-1",
        "input_cursor_seq": 0,
        "prompt_template_id": "role_action@m00",
        "created_at": datetime.now(UTC),
    }

    record = ActionRecord(
        **base,
        status=TurnStatus.SUCCEEDED,
        draft=ActionDraft(action=ActionType.PASS),
    )
    assert record.message_id is None

    with pytest.raises(ValidationError):
        ActionRecord(**base, status=TurnStatus.SUCCEEDED)
    with pytest.raises(ValidationError):
        ActionRecord(
            **base,
            status=TurnStatus.FAILED,
            draft=ActionDraft(action=ActionType.PASS),
        )


def test_message_id_only_for_successful_speak() -> None:
    from datetime import UTC, datetime

    base = {
        "action_id": "act-2",
        "turn_id": "turn-2",
        "attempt_id": "attempt-2",
        "scene_id": "scene-1",
        "actor_id": "agent-1",
        "input_cursor_seq": 3,
        "prompt_template_id": "role_action@m00",
        "created_at": datetime.now(UTC),
        "message_id": "msg-1",
    }

    with pytest.raises(ValidationError):
        ActionRecord(**base, status=TurnStatus.SUCCEEDED, draft=ActionDraft(action=ActionType.PASS))

    ok = ActionRecord(
        **base,
        status=TurnStatus.SUCCEEDED,
        draft=ActionDraft(action=ActionType.SPEAK, text="好"),
    )
    assert ok.message_id == "msg-1"
