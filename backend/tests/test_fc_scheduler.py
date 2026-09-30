"""FC-04/05/06: free rotation, distinct silence, and one-time visible priority."""
from dataclasses import replace
from datetime import UTC, datetime
import pytest
from role_theater.contracts import ActionType, EventVisibility, PauseReason, RoleCursor
from role_theater.context import TimelineItem, TimelineKind
from role_theater.context.builder import ContextBuilder
from role_theater.scheduling import Scheduler, SchedulerState
from test_m02_scheduler import _state, _message


def free_state(timeline=(), cursors=(), priority=0):
    old = _state(timeline, cursors, priority_used=priority)
    return replace(old, scene=replace(old.scene, chat_policy_version=2))


def cursor(name, order, action="PASS", seq=0):
    return RoleCursor(scene_id="scn-1", agent_id=name, startup_opportunity_consumed=True,
                      last_action_at=datetime(2026, 9, 29, tzinfo=UTC), last_success_order=order,
                      last_success_action=action, processed_seq=seq)


def test_no_new_information_still_allows_original_speaker_to_continue():
    state = free_state((_message(1, "agt-an", "安然"),),
                       (cursor("agt-an", 1, "SPEAK"), cursor("agt-xu", 2, seq=1), cursor("agt-ch", 3, seq=1)))
    assert Scheduler().select(state).actor_id == "agt-an"
    assert {c.agent.agent_id for c in Scheduler().candidates(state)} == {"agt-an", "agt-xu", "agt-ch"}


def test_monotonic_order_makes_same_clock_rotation_fair():
    state = free_state()
    selected = []
    for order in range(1, 10):
        actor = Scheduler().select(state).actor_id
        selected.append(actor)
        cursors = {c.agent_id: c for c in state.cursors}
        cursors[actor] = cursor(actor, order, "SPEAK")
        state = replace(state, cursors=tuple(cursors.values()))
    assert selected == ["agt-an", "agt-xu", "agt-ch"] * 3


def test_every_distinct_role_must_pass_and_own_speech_is_not_silence():
    state = free_state(cursors=(cursor("agt-an", 1), cursor("agt-xu", 2)))
    assert Scheduler().select(state).actor_id == "agt-ch"
    silent = replace(state, cursors=(*state.cursors, cursor("agt-ch", 3)))
    assert Scheduler().select(silent).pause_reason is PauseReason.COLLECTIVE_SILENCE
    talking = replace(silent, cursors=(cursor("agt-an", 1, "SPEAK"), *silent.cursors[1:]))
    assert Scheduler().select(talking).has_candidate


def test_priority_is_consumed_after_successful_target_action_and_is_capped():
    message = _message(4, "agt-an", "安然", requested="agt-ch")
    cursors = (cursor("agt-an", 1, "SPEAK"), cursor("agt-xu", 2), cursor("agt-ch", 3))
    state = free_state((message,), cursors)
    assert Scheduler().select(state).actor_id == "agt-ch"
    assert Scheduler().select(replace(state, consecutive_requested_priority=2)).actor_id == "agt-an"
    consumed = replace(state, cursors=(*cursors[:2], cursor("agt-ch", 4, seq=4)))
    assert Scheduler().select(consumed).actor_id == "agt-an"


def test_unseen_private_information_does_not_invalidate_third_party_pass_or_prompt():
    old = free_state(cursors=tuple(cursor(a, i + 1) for i, a in enumerate(["agt-an", "agt-xu", "agt-ch"])))
    hidden = TimelineItem(kind=TimelineKind.MESSAGE, seq=9, body="SECRET_FC", author_agent_id="agt-an",
                          author_name="安然", message_visibility="PRIVATE", recipient_id="agt-xu", message_id="secret-id")
    # Timeline visibility uses the contract enum, matching persisted snapshots.
    from role_theater.contracts.enums import MessageVisibility
    hidden = replace(hidden, message_visibility=MessageVisibility.PRIVATE)
    new = replace(old, scene=replace(old.scene, timeline=(hidden,)))
    assert not Scheduler.collectively_silent(new)
    before = ContextBuilder().build(old.scene, "agt-ch")
    after = ContextBuilder().build(new.scene, "agt-ch")
    assert after.prompt == before.prompt
    assert after.cutoff_seq == before.cutoff_seq == 0
    assert new.cursor_for("agt-ch").last_success_action is ActionType.PASS
    received = replace(new, cursors=(new.cursors[0], cursor("agt-xu", 4, seq=9), new.cursors[2]))
    assert Scheduler.collectively_silent(received)


@pytest.mark.parametrize("mode", ["simulation", "discussion"])
def test_new_prompt_changes_length_and_continuation_but_old_prompt_remains(mode):
    from role_theater.contracts import SceneMode, DiscussionConfig
    state = free_state()
    scene = replace(state.scene, background="", mode=SceneMode(mode),
                    mode_config=DiscussionConfig(topic="测试") if mode == "discussion" else None)
    prompt = ContextBuilder().build(scene, "agt-an")
    assert "1～1000" in prompt.prompt and "即使没有新消息" in prompt.prompt
    assert prompt.prompt_template_id == f"role_action@{mode}.fc.1"
    legacy = ContextBuilder().build(replace(scene, chat_policy_version=1), "agt-an")
    assert "1～200" in legacy.prompt and "即使没有新消息" not in legacy.prompt


@pytest.mark.parametrize("count", [2, 3, 5, 8])
def test_arbitrary_scene_size_all_distinct_passes_stop(count):
    state = free_state()
    agents = tuple(replace(state.scene.agents[0], agent_id=f"role-{i}", name=f"人物{i}", order_index=i)
                   for i in range(count))
    state = replace(state, scene=replace(state.scene, agents=agents))
    selected = []
    for order in range(1, count + 1):
        result = Scheduler().select(state)
        assert result.has_candidate
        selected.append(result.actor_id)
        state = replace(state, cursors=(*state.cursors, cursor(result.actor_id, order)))
    assert selected == [a.agent_id for a in agents]
    assert Scheduler().select(state).pause_reason is PauseReason.COLLECTIVE_SILENCE
