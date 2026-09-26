"""M04 运行时：状态机、运行器与提交通知。"""

from __future__ import annotations

from .broadcaster import Broadcaster
from .runner import NOT_DISPATCHED_KINDS, SceneRunner, StepResult, utcnow
from .state_machine import (
    ALLOWED_TRANSITIONS,
    InvalidTransition,
    assert_transition,
    can_transition,
    is_terminal,
    validate_pause,
)

__all__ = [
    "ALLOWED_TRANSITIONS",
    "Broadcaster",
    "InvalidTransition",
    "NOT_DISPATCHED_KINDS",
    "SceneRunner",
    "StepResult",
    "assert_transition",
    "can_transition",
    "is_terminal",
    "utcnow",
    "validate_pause",
]
