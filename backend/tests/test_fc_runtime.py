"""FC-08/09: actual runner + SQLite, isolated Mock and both policies."""
import asyncio
import json
import sqlite3
import pytest
from role_theater.contracts import ActionDraft, ActionType, ControlCommandType, EventSubmission, ModelFailure, ModelFailureKind, PauseReason, RunState
from role_theater.runtime import SceneRunner
from role_theater.storage import RuntimeRepository, SceneRepository
from test_m04_runner import build_env, GatedModelPort, Counter, CLOCK, speak


async def step(env, number):
    return await env.runner.run_command(env.scene_id, request_id=f"fc-step-{number}", command=ControlCommandType.STEP)


@pytest.mark.parametrize("mode", ["simulation", "discussion"])
@pytest.mark.parametrize("count", [2, 3, 5, 8])
async def test_all_distinct_passes_pause_and_new_command_reopens_opportunities(database, mode, count):
    env = build_env(database, mode=mode, agent_count=count, chat_policy_version=2)
    for number in range(count):
        ack = await step(env, number)
        assert ack.run_state is RunState.PAUSED
        assert ack.pause_reason is (PauseReason.COLLECTIVE_SILENCE if number == count - 1 else PauseReason.MANUAL)
    assert [call.actor_id for call in env.port.calls] == env.agent_ids
    assert env.runtime.list_messages(env.scene_id) == []
    assert [c.last_success_order for c in env.runtime.list_cursors(env.scene_id)] == list(range(1, count + 1))
    ack = await step(env, count)
    assert env.port.call_count == count + 1
    assert env.port.calls[-1].actor_id == env.agent_ids[0]
    again = await step(env, count)
    assert again.deduplicated
    assert env.port.call_count == count + 1
    assert sum(c.last_success_action is ActionType.PASS for c in env.runtime.list_cursors(env.scene_id)) == 1


@pytest.mark.parametrize("command", [ControlCommandType.START, ControlCommandType.RESUME])
async def test_auto_resume_after_silence_is_bounded_and_deduplicated(database, command):
    env = build_env(database, chat_policy_version=2)
    await env.runner.run_command(env.scene_id, request_id="start", command=ControlCommandType.START)
    assert await env.runner.wait_until_idle(env.scene_id, timeout=5)
    assert env.port.call_count == 3
    assert env.scene_repo.get_scene(env.scene_id).pause_reason is PauseReason.COLLECTIVE_SILENCE
    await env.runner.run_command(env.scene_id, request_id="continue", command=command)
    assert await env.runner.wait_until_idle(env.scene_id, timeout=5)
    assert env.port.call_count == 6
    assert (await env.runner.run_command(env.scene_id, request_id="continue", command=command)).deduplicated
    assert env.port.call_count == 6


async def test_original_speaker_can_continue_without_new_external_information(database):
    env = build_env(database, chat_policy_version=2, script=[speak("开始"), ActionDraft(action="PASS"),
                                                          ActionDraft(action="PASS"), speak("我再补充一点")])
    for n in range(4):
        await step(env, n)
    assert [call.actor_id for call in env.port.calls] == [*env.agent_ids, env.agent_ids[0]]
    assert [m.text for m in env.runtime.list_messages(env.scene_id)] == ["开始", "我再补充一点"]
    assert all(c.params.max_output_tokens == 4096 and c.references.chat_policy_version == 2 for c in env.port.calls)
    assert all(c.chat_policy_version == 2 and c.prompt_template_id.endswith(".fc.1") for c in env.port.calls)


async def test_private_priority_consumed_once_and_third_party_input_unchanged(database):
    env = build_env(database, chat_policy_version=2)
    a, b, c = env.agent_ids
    third_before = env.runner.viewpoint(env.scene_id, c)[1]
    env.port._script = [ActionDraft(action="PRIVATE", recipient_id=b, text="FC_SECRET"), ActionDraft(action="PASS")]
    await step(env, 0)
    await step(env, 1)
    await step(env, 2)
    assert [call.actor_id for call in env.port.calls] == [a, b, c]
    assert env.port.calls[2].prompt == third_before.prompt
    assert "FC_SECRET" not in env.port.calls[2].model_dump_json()
    await step(env, 3)
    assert env.port.calls[3].actor_id == a
    assert env.scene_repo.get_scene(env.scene_id).pause_reason is PauseReason.COLLECTIVE_SILENCE
    assert env.runtime.conversations(env.scene_id, viewer_id=c) == []


async def test_pending_targeted_event_after_final_pass_prevents_silent_pause(database):
    env = build_env(database, chat_policy_version=2)
    await step(env, 0)
    await step(env, 1)
    port = GatedModelPort(ActionDraft(action="PASS"))
    env.runner._model = port
    task = asyncio.create_task(step(env, 2))
    await asyncio.wait_for(port.started.wait(), timeout=5)
    await env.runner.inject_event(env.scene_id, request_id="event", submission=EventSubmission(
        body="NEW_VISIBLE", visibility="TARGETED", target_agent_id=env.agent_ids[0]))
    port.release.set()
    assert (await asyncio.wait_for(task, timeout=5)).pause_reason is PauseReason.MANUAL
    assert env.runtime.get_cursor(env.scene_id, env.agent_ids[0]).processed_seq == 0
    assert env.runtime.list_events(env.scene_id)[0].status.value == "EFFECTIVE"
    env.runner._model = env.port
    await step(env, 3)
    assert env.port.calls[-1].actor_id == env.agent_ids[0]
    assert "NEW_VISIBLE" in env.port.calls[-1].prompt
    assert env.scene_repo.get_scene(env.scene_id).pause_reason is PauseReason.COLLECTIVE_SILENCE


@pytest.mark.parametrize("kind,status", [(ModelFailureKind.PROVIDER_ERROR, "FAILED"), (ModelFailureKind.UNKNOWN_REQUEST, "UNKNOWN")])
async def test_failures_keep_success_order_and_silence_and_consume_sent_budget(database, kind, status):
    env = build_env(database, chat_policy_version=2, script=[speak("开始"), ModelFailure(kind=kind, detail="fixed failure")])
    await step(env, 0)
    before = env.runtime.list_cursors(env.scene_id)
    ack = await step(env, 1)
    assert ack.pause_reason is PauseReason.PROVIDER_ERROR
    assert env.runtime.list_cursors(env.scene_id) == before
    assert env.runtime.list_turns(env.scene_id)[-1]["status"] == status
    assert env.runtime.budget_used(env.scene_id)["role_requests_used"] == 2


@pytest.mark.parametrize("stage", ["turn", "cursor", "scheduler"])
async def test_success_fault_rolls_back_order_pass_and_message(database, stage):
    env = build_env(database, chat_policy_version=2, script=[speak("整体提交")])
    target = {"turn": "BEFORE UPDATE ON scene_turns WHEN NEW.status = 'SUCCEEDED'",
              "cursor": "BEFORE INSERT ON role_cursors", "scheduler": "BEFORE INSERT ON scene_scheduler_state"}[stage]
    with database.transaction() as conn:
        conn.execute(f"CREATE TRIGGER fail_fc {target} BEGIN SELECT RAISE(ABORT, 'fc fault'); END")
    with pytest.raises(sqlite3.IntegrityError, match="fc fault"):
        await step(env, 0)
    assert env.runtime.list_messages(env.scene_id) == []
    assert env.runtime.list_cursors(env.scene_id) == []
    assert env.runtime.last_seq(env.scene_id) == 0
    assert env.runtime.list_turns(env.scene_id)[0]["status"] == "PENDING"
    assert env.runner.recover_after_restart() == [env.scene_id]
    assert env.runtime.list_turns(env.scene_id)[0]["status"] == "UNKNOWN"
    assert env.port.call_count == 1


async def test_restart_keeps_rotation_silence_policy_and_budget_without_dispatch(database):
    env = build_env(database, chat_policy_version=2)
    await step(env, 0)
    await step(env, 1)
    before = env.runtime.list_cursors(env.scene_id)
    runner = SceneRunner(database=database, scenes=SceneRepository(database), runtime=RuntimeRepository(database),
                         model_port=env.port, clock=lambda: CLOCK, id_factory=Counter("reopen"))
    runner.recover_after_restart()
    assert env.runtime.list_cursors(env.scene_id) == before
    assert runner.snapshot(env.scene_id).chat_policy_version == 2
    assert env.port.call_count == 2
    env.runner = runner
    ack = await step(env, 2)
    assert env.port.calls[-1].actor_id == env.agent_ids[2]
    assert ack.pause_reason is PauseReason.COLLECTIVE_SILENCE
    assert env.runtime.budget_used(env.scene_id)["role_requests_used"] == 3


async def test_restart_recovers_post_success_state_fault_without_replaying_action(database):
    env = build_env(database, chat_policy_version=2)
    await step(env, 0)
    await step(env, 1)
    with database.transaction() as conn:
        conn.execute("CREATE TRIGGER fail_final BEFORE UPDATE ON scenes WHEN NEW.pause_reason='COLLECTIVE_SILENCE' BEGIN SELECT RAISE(ABORT,'final fault'); END")
    with pytest.raises(sqlite3.IntegrityError, match="final fault"):
        await step(env, 2)
    assert env.scene_repo.get_scene(env.scene_id).status is RunState.RUNNING
    assert [t["status"] for t in env.runtime.list_turns(env.scene_id)] == ["SUCCEEDED"] * 3
    with database.transaction() as conn:
        conn.execute("DROP TRIGGER fail_final")
    runner = SceneRunner(database=database, scenes=SceneRepository(database), runtime=RuntimeRepository(database),
                         model_port=env.port, clock=lambda: CLOCK, id_factory=Counter("recover"))
    assert runner.recover_after_restart() == [env.scene_id]
    assert env.scene_repo.get_scene(env.scene_id).pause_reason is PauseReason.PROCESS_INTERRUPT
    assert env.port.call_count == 3
    env.runner = runner
    replay = await step(env, 2)
    assert replay.deduplicated and replay.pause_reason is PauseReason.PROCESS_INTERRUPT
    assert '结果尚未确认' in replay.detail
    assert env.port.call_count == 3
    await step(env, 3)
    assert env.port.call_count == 4 and env.port.calls[-1].actor_id == env.agent_ids[0]
    assert runner.recover_after_restart() == []


@pytest.mark.parametrize('command', [ControlCommandType.STEP, ControlCommandType.START, ControlCommandType.RESUME])
async def test_first_request_after_restart_includes_accepted_event(database, command):
    env = build_env(database, chat_policy_version=2)
    gate = GatedModelPort(ActionDraft(action='PASS'))
    env.runner._model = gate
    task = asyncio.create_task(step(env, 0))
    await asyncio.wait_for(gate.started.wait(), timeout=5)
    await env.runner.inject_event(env.scene_id, request_id='pending-event', submission=EventSubmission(
        body='RECOVERY_EVENT', visibility='TARGETED', target_agent_id=env.agent_ids[0]))
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    runner = SceneRunner(database=database, scenes=SceneRepository(database), runtime=RuntimeRepository(database),
                         model_port=env.port, clock=lambda: CLOCK, id_factory=Counter('recover-event'))
    runner.recover_after_restart()
    assert env.runtime.list_events(env.scene_id)[0].status.value == 'ACCEPTED'
    await runner.run_command(env.scene_id, request_id='recovery', command=command)
    assert await runner.wait_until_idle(env.scene_id, timeout=5)
    assert 'RECOVERY_EVENT' in env.port.calls[0].prompt
    assert env.runtime.list_events(env.scene_id)[0].status.value == 'EFFECTIVE'
    assert len(env.runtime.list_events(env.scene_id)) == 1
    before = env.port.call_count
    assert (await runner.run_command(env.scene_id, request_id='fc-step-0', command=ControlCommandType.STEP)).deduplicated
    assert env.port.call_count == before


async def test_free_chat_stops_at_budget_and_context_limit_still_blocks_send(database):
    env = build_env(database, chat_policy_version=2, max_role_requests=4, default_draft=speak("持续表达"))
    await env.runner.run_command(env.scene_id, request_id="run", command=ControlCommandType.START)
    assert await env.runner.wait_until_idle(env.scene_id, timeout=5)
    assert env.scene_repo.get_scene(env.scene_id).status is RunState.ENDED
    assert env.port.call_count == 4
    assert not (await step(env, 4)).accepted


async def test_context_limit_blocks_send_without_consuming_budget(database):
    env = build_env(database, chat_policy_version=2, prompt_char_limit=1)
    ack = await step(env, 0)
    assert ack.pause_reason is PauseReason.CONTEXT_LIMIT
    assert env.port.call_count == 0
    assert env.runtime.budget_used(env.scene_id)["role_requests_used"] == 0


async def test_pause_during_final_pass_then_one_step_reopens_opportunity(database):
    env = build_env(database, chat_policy_version=2)
    await step(env, 0)
    await step(env, 1)
    port = GatedModelPort(ActionDraft(action="PASS"))
    env.runner._model = port
    task = asyncio.create_task(step(env, 2))
    await asyncio.wait_for(port.started.wait(), timeout=5)
    await env.runner.run_command(env.scene_id, request_id="manual-pause", command=ControlCommandType.PAUSE)
    port.release.set()
    assert (await asyncio.wait_for(task, timeout=5)).pause_reason is PauseReason.MANUAL
    env.runner._model = env.port
    await step(env, 3)
    assert env.port.call_count == 3  # A, B, then the reopened A; gated C counted separately.
    assert env.port.calls[-1].actor_id == env.agent_ids[0]
    assert sum(c.last_success_action is ActionType.PASS for c in env.runtime.list_cursors(env.scene_id)) == 1


@pytest.mark.parametrize("version,accepted", [(1, False), (2, True)])
async def test_runner_validates_long_mock_result_by_saved_policy(database, version, accepted):
    env = build_env(database, chat_policy_version=version, script=[speak("字" * 1000)])
    ack = await step(env, 0)
    assert (len(env.runtime.list_messages(env.scene_id)) == 1) is accepted
    assert env.port.calls[0].params.max_output_tokens == (1024 if version == 1 else 4096)
    if not accepted:
        assert ack.pause_reason is PauseReason.PROVIDER_ERROR
        assert env.runtime.list_turns(env.scene_id)[0]["failure_kind"] == "SCHEMA_INVALID"
