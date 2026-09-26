"""M02 调度：纯函数式的候选选择与点名优先。"""

from __future__ import annotations

from .scheduler import (
    MAX_CONSECUTIVE_REQUESTED_PRIORITY,
    Candidate,
    Scheduler,
    SchedulerState,
    SchedulingOutcome,
)

__all__ = [
    "MAX_CONSECUTIVE_REQUESTED_PRIORITY",
    "Candidate",
    "Scheduler",
    "SchedulerState",
    "SchedulingOutcome",
]
