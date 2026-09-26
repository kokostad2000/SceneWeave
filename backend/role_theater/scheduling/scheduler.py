"""Scheduler：规则调度（PRD 5.1）。

纯函数：输入是纯数据（角色固定顺序、游标、时间线），输出是可复核的决策。
不调用主持模型，不读写数据库，不依赖时间（时间只来自游标）。

规则（PRD 5.1）：

1. 首次开始为所有角色建立一次**启动机会**；之后候选必须有尚未处理的新可见
   外部信息，或尚未消费启动机会；
2. 优先满足**有效的指定回应者**，最多**连续两次**点名优先，然后必须执行一次
   普通轮转；
3. 普通轮转选择**最久未行动**的候选，平局按**固定角色顺序**；
4. 候选为空时暂停，原因 `NO_NEW_INFORMATION`（不是会话结束）。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts import PauseReason, RoleCursor, SchedulerReason
from ..context import SceneSnapshot, cutoff_seq, newest_external_seq
from ..context.models import AgentProfileView

#: 连续点名优先的次数上限（PRD 5.1：最多连续使用两次）。
MAX_CONSECUTIVE_REQUESTED_PRIORITY = 2


@dataclass(frozen=True, slots=True)
class SchedulerState:
    """调度输入（由 M04 从数据库装配成纯数据）。"""

    scene: SceneSnapshot
    cursors: tuple[RoleCursor, ...] = ()
    #: 已连续使用点名优先的次数；由 M04 在每次提交后维护。
    consecutive_requested_priority: int = 0

    def cursor_for(self, agent_id: str) -> RoleCursor:
        for cursor in self.cursors:
            if cursor.agent_id == agent_id:
                return cursor
        # 尚未建立游标的角色等价于“全新”：启动机会未消费、已处理位置为 0。
        return RoleCursor(scene_id=self.scene.scene_id, agent_id=agent_id)


@dataclass(frozen=True, slots=True)
class Candidate:
    """一个候选角色及其可复核的原因。"""

    agent: AgentProfileView
    reason: SchedulerReason
    based_on_seq: int


@dataclass(frozen=True, slots=True)
class SchedulingOutcome:
    """一次调度决策。``actor_id`` 为 None 表示没有候选。"""

    actor_id: str | None
    reason: SchedulerReason | None
    based_on_seq: int
    requested_by_agent_id: str | None = None
    pause_reason: PauseReason | None = None

    @property
    def has_candidate(self) -> bool:
        return self.actor_id is not None


class Scheduler:
    """规则调度器。"""

    def __init__(
        self,
        *,
        max_consecutive_requested_priority: int = MAX_CONSECUTIVE_REQUESTED_PRIORITY,
    ) -> None:
        self.max_consecutive_requested_priority = max_consecutive_requested_priority

    # --- 候选 ---

    def is_candidate(self, state: SchedulerState, agent_id: str) -> bool:
        cursor = state.cursor_for(agent_id)
        if not cursor.startup_opportunity_consumed:
            return True
        # 自己说的话不算“新可见外部信息”，因此不能仅凭自己的发言再次唤醒自己。
        return newest_external_seq(state.scene, agent_id) > cursor.processed_seq

    def candidates(self, state: SchedulerState) -> tuple[Candidate, ...]:
        """按固定角色顺序返回候选及其原因。"""

        result: list[Candidate] = []
        for agent in state.scene.ordered_agents:
            cursor = state.cursor_for(agent.agent_id)
            if not cursor.startup_opportunity_consumed:
                result.append(
                    Candidate(
                        agent=agent,
                        reason=SchedulerReason.STARTUP_OPPORTUNITY,
                        based_on_seq=self._based_on_seq(state, agent.agent_id),
                    )
                )
            elif newest_external_seq(state.scene, agent.agent_id) > cursor.processed_seq:
                result.append(
                    Candidate(
                        agent=agent,
                        reason=SchedulerReason.NEW_VISIBLE_INFORMATION,
                        based_on_seq=self._based_on_seq(state, agent.agent_id),
                    )
                )
        return tuple(result)

    # --- 决策 ---

    def select(self, state: SchedulerState) -> SchedulingOutcome:
        candidates = self.candidates(state)
        if not candidates:
            return SchedulingOutcome(
                actor_id=None,
                reason=None,
                based_on_seq=state.scene.last_seq,
                pause_reason=PauseReason.NO_NEW_INFORMATION,
            )

        by_id = {candidate.agent.agent_id: candidate for candidate in candidates}

        # 1) 点名优先（最多连续两次）。窗口只取时间线上最新一条发言。
        requested = self._requested_speaker(state)
        if requested is not None:
            speaker_agent_id, requester_agent_id = requested
            if (
                state.consecutive_requested_priority < self.max_consecutive_requested_priority
                and speaker_agent_id in by_id
            ):
                candidate = by_id[speaker_agent_id]
                return SchedulingOutcome(
                    actor_id=candidate.agent.agent_id,
                    reason=SchedulerReason.REQUESTED_SPEAKER_PRIORITY,
                    based_on_seq=candidate.based_on_seq,
                    requested_by_agent_id=requester_agent_id,
                )

        # 2) 普通轮转：最久未行动者优先，平局按固定角色顺序。
        chosen = min(
            candidates,
            key=lambda candidate: (
                self._last_action_key(state, candidate.agent.agent_id),
                candidate.agent.order_index,
            ),
        )
        return SchedulingOutcome(
            actor_id=chosen.agent.agent_id,
            reason=chosen.reason,
            based_on_seq=chosen.based_on_seq,
        )

    # --- 内部 ---

    @staticmethod
    def _last_action_key(state: SchedulerState, agent_id: str) -> tuple[int, float]:
        """排序键：从未行动者排最前（``(0, 0.0)``），其余按上次行动时间升序。"""

        last_action_at = state.cursor_for(agent_id).last_action_at
        if last_action_at is None:
            return (0, 0.0)
        return (1, last_action_at.timestamp())

    @staticmethod
    def _based_on_seq(state: SchedulerState, agent_id: str) -> int:
        return cutoff_seq(state.scene, agent_id)

    @staticmethod
    def _requested_speaker(state: SchedulerState) -> tuple[str, str] | None:
        """**最新一条发言**携带的 ``requested_speaker_id``（tasks/M02.md §3.6 I1）。

        更早的点名视为已过期：只回看最新一条发言，避免旧点名长期劫持调度。
        """

        messages = [item for item in state.scene.timeline if item.kind.value == "message"]
        if not messages:
            return None
        latest = max(messages, key=lambda item: item.seq)
        if not latest.requested_speaker_id or latest.author_agent_id is None:
            return None
        return latest.requested_speaker_id, latest.author_agent_id


__all__ = [
    "MAX_CONSECUTIVE_REQUESTED_PRIORITY",
    "Candidate",
    "Scheduler",
    "SchedulerState",
    "SchedulingOutcome",
]
