"""状态机（PRD 5.2）。

状态固定为六个，迁移规则集中在这里；`ENDED` 是终态，不可恢复运行。
"""

from __future__ import annotations

from ..contracts import PauseReason, RunState

#: 允许的状态迁移。`PAUSED` 可以再次进入 `PAUSED`（原因可能变化）。
ALLOWED_TRANSITIONS: dict[RunState, frozenset[RunState]] = {
    RunState.READY: frozenset({RunState.RUNNING, RunState.PAUSED, RunState.ENDED}),
    RunState.RUNNING: frozenset(
        {RunState.PAUSING, RunState.PAUSED, RunState.STOPPING, RunState.ENDED}
    ),
    RunState.PAUSING: frozenset({RunState.PAUSED, RunState.STOPPING, RunState.ENDED}),
    RunState.PAUSED: frozenset({RunState.RUNNING, RunState.STOPPING, RunState.ENDED}),
    RunState.STOPPING: frozenset({RunState.ENDED}),
    RunState.ENDED: frozenset(),
}

#: 每个暂停原因允许出现的来源状态（防止把“无新信息”记到人工暂停上）。
ALLOWED_PAUSE_REASONS = frozenset(PauseReason)

#: 原因与是否表示“会话自然停下”的关系：`NO_NEW_INFORMATION` 不是会话结束。
TERMINAL_STATES = frozenset({RunState.ENDED})


class InvalidTransition(RuntimeError):
    """非法状态迁移。"""

    def __init__(self, current: RunState, target: RunState) -> None:
        super().__init__(f"非法状态迁移：{current.value} → {target.value}")
        self.current = current
        self.target = target


def can_transition(current: RunState, target: RunState) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


def assert_transition(current: RunState, target: RunState) -> None:
    if not can_transition(current, target):
        raise InvalidTransition(current, target)


def validate_pause(reason: PauseReason | None) -> PauseReason:
    """暂停必须有可区分的原因（PRD 5.2）。"""

    if reason is None:
        raise ValueError("进入 PAUSED 必须给出 pause_reason")
    if reason not in ALLOWED_PAUSE_REASONS:  # pragma: no cover - 枚举已封闭
        raise ValueError(f"未知的暂停原因：{reason}")
    return reason


def is_running_like(state: RunState) -> bool:
    """是否处于“循环应当继续”的状态。"""

    return state in (RunState.RUNNING, RunState.PAUSING)


def is_terminal(state: RunState) -> bool:
    return state in TERMINAL_STATES


__all__ = [
    "ALLOWED_PAUSE_REASONS",
    "ALLOWED_TRANSITIONS",
    "InvalidTransition",
    "TERMINAL_STATES",
    "assert_transition",
    "can_transition",
    "is_running_like",
    "is_terminal",
    "validate_pause",
]
