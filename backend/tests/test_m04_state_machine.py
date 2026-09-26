"""M04 状态机（PRD 5.2；tasks/M04.md A2、A4、A5）。"""

from __future__ import annotations

import pytest

from role_theater.contracts import PauseReason, RunState
from role_theater.runtime import (
    ALLOWED_TRANSITIONS,
    InvalidTransition,
    assert_transition,
    can_transition,
    is_terminal,
    validate_pause,
)

STATES = list(RunState)


def test_all_six_states_are_covered_exactly_once() -> None:
    assert [state.value for state in STATES] == [
        "READY",
        "RUNNING",
        "PAUSING",
        "STOPPING",
        "PAUSED",
        "ENDED",
    ]
    assert set(ALLOWED_TRANSITIONS) == set(STATES)


def test_ended_is_terminal() -> None:
    assert is_terminal(RunState.ENDED)
    assert ALLOWED_TRANSITIONS[RunState.ENDED] == frozenset()
    for target in STATES:
        assert not can_transition(RunState.ENDED, target)
    with pytest.raises(InvalidTransition):
        assert_transition(RunState.ENDED, RunState.RUNNING)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (RunState.READY, RunState.RUNNING),
        (RunState.READY, RunState.PAUSED),
        (RunState.RUNNING, RunState.PAUSING),
        (RunState.RUNNING, RunState.PAUSED),
        (RunState.RUNNING, RunState.STOPPING),
        (RunState.PAUSING, RunState.PAUSED),
        (RunState.PAUSING, RunState.STOPPING),
        (RunState.PAUSED, RunState.RUNNING),
        (RunState.PAUSED, RunState.STOPPING),
        (RunState.PAUSED, RunState.ENDED),
        (RunState.STOPPING, RunState.ENDED),
    ],
)
def test_allowed_transitions(current: RunState, target: RunState) -> None:
    assert can_transition(current, target)
    assert_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (RunState.READY, RunState.PAUSING),
        (RunState.READY, RunState.STOPPING),
        (RunState.PAUSING, RunState.RUNNING),
        (RunState.STOPPING, RunState.PAUSED),
        (RunState.STOPPING, RunState.RUNNING),
        (RunState.PAUSED, RunState.PAUSING),
    ],
)
def test_forbidden_transitions(current: RunState, target: RunState) -> None:
    assert not can_transition(current, target)
    with pytest.raises(InvalidTransition) as excinfo:
        assert_transition(current, target)
    assert excinfo.value.current is current
    assert excinfo.value.target is target


def test_pause_requires_a_distinguishable_reason() -> None:
    for reason in PauseReason:
        assert validate_pause(reason) is reason

    with pytest.raises(ValueError):
        validate_pause(None)


def test_no_new_information_is_not_a_terminal_state() -> None:
    """PRD 5.1：候选为空只是暂停，不是会话结束。"""

    assert not is_terminal(RunState.PAUSED)
    assert can_transition(RunState.PAUSED, RunState.RUNNING)


def test_paused_scene_resumes_or_stops_without_going_through_pausing() -> None:
    """`PAUSED` 可以直接 `RESUME` 或 `STOP`，但不应绕道 `PAUSING`。"""

    assert can_transition(RunState.PAUSED, RunState.RUNNING)
    assert can_transition(RunState.PAUSED, RunState.STOPPING)
    assert not can_transition(RunState.PAUSED, RunState.PAUSING)
