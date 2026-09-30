"""M02 调度（PRD 5.1；tasks/M02.md A4–A9）。

PRD 通过条件中的两条由本文件证明：**自发言不自唤醒**、**PASS 能使场景停下来**。
所有用例都是纯数据驱动的确定性用例，不涉及数据库、时间或模型。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from role_theater.context import AgentProfileView, SceneSnapshot, TimelineItem, TimelineKind
from role_theater.contracts import (
    AgentSnapshot,
    EventVisibility,
    PauseReason,
    RoleCursor,
    SchedulerReason,
)
from role_theater.scheduling import Scheduler, SchedulerState

NOW = datetime(2026, 9, 26, 20, 0, tzinfo=UTC)


def _snapshot(name: str) -> AgentSnapshot:
    return AgentSnapshot(
        source_template_id=f"tpl-{name}",
        name=name,
        persona=f"{name}的人物设定",
        speech_style="",
        initial_goal="",
        private_background=f"{name}的私有背景",
        captured_at=NOW,
    )


AGENTS = (
    AgentProfileView(agent_id="agt-an", name="安然", order_index=0, snapshot=_snapshot("安然")),
    AgentProfileView(agent_id="agt-xu", name="许川", order_index=1, snapshot=_snapshot("许川")),
    AgentProfileView(agent_id="agt-ch", name="陈禾", order_index=2, snapshot=_snapshot("陈禾")),
)


def _message(
    seq: int, agent_id: str, name: str, text: str = "……", *, requested: str | None = None
) -> TimelineItem:
    return TimelineItem(
        kind=TimelineKind.MESSAGE,
        seq=seq,
        body=text,
        author_agent_id=agent_id,
        author_name=name,
        requested_speaker_id=requested,
    )


def _event(
    seq: int, body: str, visibility: EventVisibility, target: str | None = None
) -> TimelineItem:
    return TimelineItem(
        kind=TimelineKind.EVENT,
        seq=seq,
        body=body,
        author_agent_id=None,
        author_name=None,
        visibility=visibility,
        target_agent_id=target,
    )


def _state(
    timeline: tuple[TimelineItem, ...] = (),
    cursors: tuple[RoleCursor, ...] = (),
    *,
    priority_used: int = 0,
) -> SchedulerState:
    return SchedulerState(
        scene=SceneSnapshot(
            scene_id="scn-1",
            background="背景。",
            agents=AGENTS,
            timeline=timeline,
        ),
        cursors=cursors,
        consecutive_requested_priority=priority_used,
    )


def _cursor(
    agent_id: str,
    *,
    processed_seq: int,
    startup_consumed: bool = True,
    last: datetime | None = None,
) -> RoleCursor:
    return RoleCursor(
        scene_id="scn-1",
        agent_id=agent_id,
        processed_seq=processed_seq,
        startup_opportunity_consumed=startup_consumed,
        last_action_at=last,
    )


# --- A8 启动机会只用一次 -------------------------------------------------------


def test_all_roles_get_one_startup_opportunity() -> None:
    scheduler = Scheduler()
    state = _state()

    outcome = scheduler.select(state)

    assert outcome.actor_id == "agt-an", "全员平局时按固定角色顺序"
    assert outcome.reason is SchedulerReason.STARTUP_OPPORTUNITY
    assert [c.agent.agent_id for c in scheduler.candidates(state)] == [
        "agt-an",
        "agt-xu",
        "agt-ch",
    ]


def test_consumed_startup_opportunity_is_not_offered_again() -> None:
    scheduler = Scheduler()
    state = _state(
        cursors=(
            _cursor("agt-an", processed_seq=0),
            _cursor("agt-xu", processed_seq=0),
            _cursor("agt-ch", processed_seq=0, startup_consumed=False),
        )
    )

    outcome = scheduler.select(state)

    assert outcome.actor_id == "agt-ch"
    assert outcome.reason is SchedulerReason.STARTUP_OPPORTUNITY
    assert [c.agent.agent_id for c in scheduler.candidates(state)] == ["agt-ch"]


# --- A4 自发言不自唤醒 ---------------------------------------------------------


def test_a_role_is_not_woken_by_its_own_message() -> None:
    scheduler = Scheduler()
    state = _state(
        timeline=(_message(1, "agt-an", "安然", "我先说一句。"),),
        cursors=(
            _cursor("agt-an", processed_seq=1),
            _cursor("agt-xu", processed_seq=0),
            _cursor("agt-ch", processed_seq=0),
        ),
    )

    candidates = {c.agent.agent_id for c in scheduler.candidates(state)}

    assert "agt-an" not in candidates, "不能仅凭自己的发言再次唤醒自己"
    assert candidates == {"agt-xu", "agt-ch"}


def test_only_own_output_means_no_candidate() -> None:
    scheduler = Scheduler()
    state = _state(
        timeline=(_message(7, "agt-an", "安然", "只有我说过话。"),),
        cursors=(
            _cursor("agt-an", processed_seq=7),
            _cursor("agt-xu", processed_seq=7),
            _cursor("agt-ch", processed_seq=7),
        ),
    )

    outcome = scheduler.select(state)

    assert outcome.actor_id is None
    assert outcome.pause_reason is PauseReason.NO_NEW_INFORMATION


# --- A5 PASS 能使场景停下来 ----------------------------------------------------


def test_passing_until_no_new_information_stops_the_scene() -> None:
    """全员消费启动机会后只剩自己的输出 → 候选为空 → 暂停而不是会话结束。"""

    scheduler = Scheduler()
    timeline = (
        _message(1, "agt-an", "安然"),
        _message(2, "agt-xu", "许川"),
        _message(3, "agt-ch", "陈禾"),
    )
    partial = _state(
        timeline,
        (
            _cursor("agt-an", processed_seq=1),
            _cursor("agt-xu", processed_seq=2),
            _cursor("agt-ch", processed_seq=3),
        ),
    )

    # 安然/许川仍有别人更晚的发言未处理；陈禾已处理到最后（seq3 是自己的发言）。
    assert scheduler.is_candidate(partial, "agt-an")
    assert scheduler.is_candidate(partial, "agt-xu")
    assert not scheduler.is_candidate(partial, "agt-ch")

    settled = _state(
        timeline,
        (
            _cursor("agt-an", processed_seq=3),
            _cursor("agt-xu", processed_seq=3),
            _cursor("agt-ch", processed_seq=3),
        ),
    )
    outcome = scheduler.select(settled)

    assert scheduler.candidates(settled) == ()
    assert outcome.actor_id is None
    assert outcome.pause_reason is PauseReason.NO_NEW_INFORMATION


def test_targeted_event_keeps_only_its_audience_alive() -> None:
    scheduler = Scheduler()
    timeline = (
        _message(1, "agt-an", "安然"),
        _event(2, "只通知许川。", EventVisibility.TARGETED, "agt-xu"),
    )
    state = _state(
        timeline,
        (
            _cursor("agt-an", processed_seq=1),
            _cursor("agt-xu", processed_seq=0),
            _cursor("agt-ch", processed_seq=1),
        ),
    )

    assert scheduler.is_candidate(state, "agt-xu")
    assert not scheduler.is_candidate(state, "agt-an")
    assert not scheduler.is_candidate(state, "agt-ch")
    assert scheduler.select(state).actor_id == "agt-xu"


def test_public_event_wakes_everyone() -> None:
    scheduler = Scheduler()
    timeline = (_event(5, "客厅的灯突然灭了。", EventVisibility.ALL),)
    state = _state(
        timeline,
        (
            _cursor("agt-an", processed_seq=0),
            _cursor("agt-xu", processed_seq=0),
            _cursor("agt-ch", processed_seq=0),
        ),
    )

    assert {c.agent.agent_id for c in scheduler.candidates(state)} == {
        "agt-an",
        "agt-xu",
        "agt-ch",
    }


# --- A6 点名优先最多连续两次 ---------------------------------------------------


def test_requested_speaker_priority_is_honoured() -> None:
    scheduler = Scheduler()
    state = _state(
        timeline=(_message(1, "agt-an", "安然", "许川你说呢？", requested="agt-xu"),),
        cursors=(
            _cursor("agt-an", processed_seq=0),
            _cursor("agt-xu", processed_seq=0),
            _cursor("agt-ch", processed_seq=1),
        ),
    )

    outcome = scheduler.select(state)

    assert outcome.actor_id == "agt-xu"
    assert outcome.reason is SchedulerReason.REQUESTED_SPEAKER_PRIORITY
    assert outcome.requested_by_agent_id == "agt-an"


def test_requested_speaker_priority_is_capped_at_two_consecutive_uses() -> None:
    scheduler = Scheduler()
    timeline = (_message(1, "agt-an", "安然", "许川你说呢？", requested="agt-xu"),)
    cursors = (
        _cursor("agt-an", processed_seq=1, last=NOW - timedelta(minutes=5)),
        _cursor("agt-xu", processed_seq=0, last=NOW),
        _cursor("agt-ch", processed_seq=0, last=NOW - timedelta(minutes=10)),
    )

    first = scheduler.select(_state(timeline, cursors, priority_used=0))
    second = scheduler.select(_state(timeline, cursors, priority_used=1))
    third = scheduler.select(_state(timeline, cursors, priority_used=2))

    assert first.reason is SchedulerReason.REQUESTED_SPEAKER_PRIORITY
    assert second.reason is SchedulerReason.REQUESTED_SPEAKER_PRIORITY
    # 第三次必须普通轮转：最久未行动的候选是陈禾。
    assert third.reason is SchedulerReason.NEW_VISIBLE_INFORMATION
    assert third.actor_id == "agt-ch"


def test_request_window_is_only_the_latest_message() -> None:
    """更早的点名视为过期（tasks/M02.md §3.6 I1）。"""

    scheduler = Scheduler()
    timeline = (
        _message(1, "agt-an", "安然", "许川你说呢？", requested="agt-xu"),
        _message(2, "agt-ch", "陈禾", "我先看看。"),
    )
    cursors = (
        _cursor("agt-an", processed_seq=1, last=NOW),
        _cursor("agt-xu", processed_seq=1, last=NOW),
        _cursor("agt-ch", processed_seq=2, last=NOW),
    )

    outcome = scheduler.select(_state(timeline, cursors))

    assert outcome.reason is SchedulerReason.NEW_VISIBLE_INFORMATION
    assert outcome.actor_id == "agt-an", "最新一条发言没有点名，回落到轮转"


def test_requested_speaker_must_itself_be_a_candidate() -> None:
    scheduler = Scheduler()
    timeline = (_message(1, "agt-an", "安然", "陈禾你说呢？", requested="agt-ch"),)
    cursors = (
        _cursor("agt-an", processed_seq=0, last=NOW),
        _cursor("agt-ch", processed_seq=1, last=NOW),
        _cursor("agt-xu", processed_seq=0, last=NOW - timedelta(minutes=1)),
    )

    outcome = scheduler.select(_state(timeline, cursors))

    assert outcome.reason is SchedulerReason.NEW_VISIBLE_INFORMATION
    assert outcome.actor_id == "agt-xu", "被点名的陈禾没有新信息，不得被凭空唤醒"


# --- A7 轮转取最久未行动者，平局按固定顺序 -------------------------------------


def test_round_robin_picks_the_least_recent_actor() -> None:
    scheduler = Scheduler()
    timeline = (_message(4, "agt-an", "安然", "大家都说点什么吧。"),)
    state = _state(
        timeline,
        (
            _cursor("agt-an", processed_seq=4, last=NOW),
            _cursor("agt-xu", processed_seq=3, last=NOW - timedelta(minutes=30)),
            _cursor("agt-ch", processed_seq=3, last=NOW - timedelta(minutes=10)),
        ),
    )

    outcome = scheduler.select(state)

    assert outcome.actor_id == "agt-xu"
    assert outcome.reason is SchedulerReason.NEW_VISIBLE_INFORMATION


def test_ties_break_on_fixed_role_order() -> None:
    scheduler = Scheduler()
    state = _state(
        (_message(1, "agt-an", "安然", "你好。"),),
        (
            _cursor("agt-an", processed_seq=1, last=NOW),
            _cursor("agt-xu", processed_seq=0, last=NOW),
            _cursor("agt-ch", processed_seq=0, last=NOW),
        ),
    )

    assert scheduler.select(state).actor_id == "agt-xu", "平局按固定角色顺序"


def test_never_acted_roles_sort_before_recent_actors() -> None:
    scheduler = Scheduler()
    state = _state(
        (_message(1, "agt-an", "安然", "你好。"),),
        (
            _cursor("agt-an", processed_seq=1, startup_consumed=True, last=NOW),
            _cursor("agt-ch", processed_seq=0, startup_consumed=True, last=None),
        ),
    )

    # 许川没有游标（视为从未行动），因此排在刚行动过的陈禾之前。
    assert scheduler.select(state).actor_id == "agt-xu"


def test_based_on_seq_is_the_actor_visible_cutoff() -> None:
    scheduler = Scheduler()
    timeline = (
        _message(1, "agt-an", "安然", "你好。"),
        _event(2, "只给陈禾。", EventVisibility.TARGETED, "agt-ch"),
    )
    state = _state(
        timeline,
        (
            _cursor("agt-an", processed_seq=1, last=NOW),
            _cursor("agt-ch", processed_seq=2, last=NOW),
            _cursor("agt-xu", processed_seq=0, last=NOW),
        ),
    )

    outcome = scheduler.select(state)

    assert outcome.actor_id == "agt-xu"
    # 许川看不到定向给陈禾的事件，因此截止序号是 1。
    assert outcome.based_on_seq == 1


def test_outcome_is_reproducible_and_scheduler_is_stateless() -> None:
    scheduler = Scheduler()
    state = _state((_message(1, "agt-an", "安然", "你好。"),))

    assert scheduler.select(state) == scheduler.select(state)
    assert scheduler.max_consecutive_requested_priority == 2


def test_empty_scene_has_no_candidate() -> None:
    scheduler = Scheduler()
    empty = SchedulerState(
        scene=SceneSnapshot(scene_id="scn-empty", background="", agents=(), timeline=())
    )

    outcome = scheduler.select(empty)

    assert outcome.actor_id is None
    assert outcome.pause_reason is PauseReason.NO_NEW_INFORMATION


def test_pc_private_shared_priority_and_silence_consumption():
    from dataclasses import replace
    from role_theater.contracts.enums import MessageVisibility
    private = replace(_message(5, "agt-an", "安然"), message_visibility=MessageVisibility.PRIVATE, recipient_id="agt-xu")
    consumed = tuple(_cursor(a.agent_id, processed_seq=0, last=NOW) for a in AGENTS)
    state = _state((private,), consumed)
    assert [x.agent.agent_id for x in Scheduler().candidates(state)] == ["agt-xu"]
    assert Scheduler().select(state).reason is SchedulerReason.REQUESTED_SPEAKER_PRIORITY
    passed = tuple(_cursor(a.agent_id, processed_seq=5, last=NOW) for a in AGENTS)
    assert Scheduler().select(_state((private,), passed)).pause_reason is PauseReason.NO_NEW_INFORMATION
    # 三人仍有启动资格；两次公私共用优先后最久未行动第三人得到轮转。
    cursors = (_cursor("agt-an", processed_seq=0, startup_consumed=False, last=NOW),
               _cursor("agt-xu", processed_seq=0, startup_consumed=False, last=NOW),
               _cursor("agt-ch", processed_seq=0, startup_consumed=False))
    assert Scheduler().select(_state((private,), cursors, priority_used=2)).actor_id == "agt-ch"
