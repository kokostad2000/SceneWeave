"""事件契约：可见范围与接受／生效生命周期（PRD 4.3）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from role_theater.contracts import Event, EventStatus, EventSubmission, EventVisibility


def test_all_event_must_not_carry_target() -> None:
    EventSubmission(body="灯突然灭了。", visibility=EventVisibility.ALL)

    with pytest.raises(ValidationError):
        EventSubmission(
            body="灯突然灭了。",
            visibility=EventVisibility.ALL,
            target_agent_id="agent-1",
        )


def test_targeted_event_requires_target() -> None:
    submission = EventSubmission(
        body="你的朋友发来消息说今晚来不了。",
        visibility=EventVisibility.TARGETED,
        target_agent_id="agent-1",
    )
    assert submission.target_agent_id == "agent-1"

    with pytest.raises(ValidationError):
        EventSubmission(body="只给一个人看。", visibility=EventVisibility.TARGETED)


def test_event_body_limits_and_trimming() -> None:
    assert EventSubmission(body="  停电了  ", visibility=EventVisibility.ALL).body == "停电了"

    EventSubmission(body="字" * 1000, visibility=EventVisibility.ALL)
    with pytest.raises(ValidationError):
        EventSubmission(body="字" * 1001, visibility=EventVisibility.ALL)
    with pytest.raises(ValidationError):
        EventSubmission(body="   ", visibility=EventVisibility.ALL)
    # emoji 按码点计数：1000 个 emoji 合法，1001 个不合法。
    EventSubmission(body="😀" * 1000, visibility=EventVisibility.ALL)
    with pytest.raises(ValidationError):
        EventSubmission(body="😀" * 1001, visibility=EventVisibility.ALL)


def _event_kwargs(**overrides: object) -> dict[str, object]:
    now = datetime(2026, 9, 26, 20, 0, tzinfo=UTC)
    base: dict[str, object] = {
        "event_id": "evt-1",
        "scene_id": "scene-1",
        # 已接受但尚未生效：不占用场景内序号（PRD 4.3）。
        "seq": None,
        "body": "停电了。",
        "visibility": EventVisibility.ALL,
        "status": EventStatus.ACCEPTED,
        "accepted_at": now,
    }
    base.update(overrides)
    return base


def test_accepted_event_has_neither_seq_nor_effective_time() -> None:
    """未生效事件不占序号：时间线顺序必须等于生效顺序（PRD 4.3）。"""

    event = Event(**_event_kwargs())
    assert event.status is EventStatus.ACCEPTED
    assert event.seq is None
    assert event.effective_at is None
    assert event.schema_version == 1

    with pytest.raises(ValidationError):
        Event(**_event_kwargs(effective_at=datetime.now(UTC)))
    with pytest.raises(ValidationError):
        Event(**_event_kwargs(seq=1))


def test_effective_event_requires_seq_and_effective_time() -> None:
    accepted_at = datetime(2026, 9, 26, 20, 0, tzinfo=UTC)
    event = Event(
        **_event_kwargs(
            status=EventStatus.EFFECTIVE,
            seq=1,
            effective_at=accepted_at + timedelta(seconds=3),
        )
    )
    assert event.effective_at is not None
    assert event.seq == 1

    with pytest.raises(ValidationError):
        Event(**_event_kwargs(status=EventStatus.EFFECTIVE, seq=1))
    with pytest.raises(ValidationError):
        Event(
            **_event_kwargs(
                status=EventStatus.EFFECTIVE, effective_at=accepted_at
            )
        )


def test_effective_seq_must_start_at_one() -> None:
    with pytest.raises(ValidationError):
        Event(**_event_kwargs(status=EventStatus.EFFECTIVE, seq=0, effective_at=datetime.now(UTC)))


def test_event_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Event(**_event_kwargs(author_agent_id="agent-1"))
