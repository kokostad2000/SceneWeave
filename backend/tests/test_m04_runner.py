"""M04 运行器（PRD 4.3、5.1～5.4；tasks/M04.md A1–A13）。

用确定性 Mock 端口驱动真实仓储与状态机，覆盖单步、自动运行、暂停排序、
预算、幂等、崩溃恢复与「不重放请求」。
"""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from role_theater.contracts import (
    ActionDraft,
    ActionType,
    ControlCommandType,
    EventStatus,
    EventSubmission,
    EventVisibility,
    Message,
    ModelFailure,
    ModelFailureKind,
    ModelParams,
    PauseReason,
    RoleCursor,
    RunState,
    SchedulerReason,
    TurnStatus,
)
from role_theater.domain import AgentSpec, SceneService, TemplateService
from role_theater.ports import DeepSeekModelClient, MockModelPort
from role_theater.runtime import SceneRunner
from role_theater.scheduling import Scheduler
from role_theater.storage import Database, RuntimeRepository, SceneRepository, TemplateRepository
from role_theater.storage.runtime_repo import PENDING_TURN_STATUS
from role_theater.storage import migrator

CLOCK = datetime(2026, 9, 26, 20, 0, tzinfo=UTC)


class Counter:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.n = 0

    def __call__(self) -> str:
        self.n += 1
        return f"{self.prefix}-{self.n}"


@dataclass
class Env:
    database: Database
    scenes: SceneService
    templates: TemplateService
    scene_repo: SceneRepository
    runtime: RuntimeRepository
    runner: SceneRunner
    port: object
    scene_id: str
    agent_ids: list[str]


def build_env(
    database: Database,
    *,
    port=None,
    script=None,
    agent_count: int = 3,
    max_role_requests: int | None = None,
    prompt_char_limit: int | None = None,
    default_draft: ActionDraft | None = None,
    mode="simulation",
    chat_policy_version=1,
) -> Env:
    ids = Counter("id")
    template_service = TemplateService(
        TemplateRepository(database), clock=lambda: CLOCK, id_factory=Counter("tpl")
    )
    scene_repository = SceneRepository(database)
    scene_service = SceneService(
        scene_repository,
        template_service,
        clock=lambda: CLOCK,
        scene_id_factory=Counter("scn"),
        agent_id_factory=Counter("agt"),
    )
    runtime = RuntimeRepository(database)

    resolved_port = port or MockModelPort(
        script=script or [],
        default_draft=default_draft or ActionDraft(action=ActionType.PASS),
    )

    runner_kwargs = {}
    if prompt_char_limit is not None:
        runner_kwargs["prompt_char_limit"] = prompt_char_limit

    runner = SceneRunner(
        database=database,
        scenes=scene_repository,
        runtime=runtime,
        model_port=resolved_port,
        clock=lambda: CLOCK,
        id_factory=Counter("run"),
        **runner_kwargs,
    )

    specs = []
    for index in range(agent_count):
        template = template_service.create(
            __import__("role_theater.contracts", fromlist=["AgentProfileFields"]).AgentProfileFields(
                name=f"角色{index}",
                persona=f"人物设定{index}",
                speech_style=f"表达习惯{index}",
                initial_goal=f"初始目标{index}",
                private_background=f"私有背景{index}",
            )
        )
        specs.append(AgentSpec(template_id=template.template_id))

    detail = scene_service.create(
        title="测试场景",
        mode=mode,
        mode_config=__import__("role_theater.contracts", fromlist=["DiscussionConfig"]).DiscussionConfig(topic="晚上，三个室友在客厅相遇。") if mode == "discussion" else None,
        background="晚上，三个室友在客厅相遇。",
        agent_specs=specs,
        max_role_requests=max_role_requests,
        chat_policy_version=chat_policy_version,
    )
    return Env(
        database=database,
        scenes=scene_service,
        templates=template_service,
        scene_repo=scene_repository,
        runtime=runtime,
        runner=runner,
        port=resolved_port,
        scene_id=detail.scene.scene_id,
        agent_ids=[agent.agent_id for agent in detail.agents],
    )


def speak(text: str, **overrides) -> ActionDraft:
    return ActionDraft(action=ActionType.SPEAK, text=text, **overrides)


# --- A1 假模型端到端 -----------------------------------------------------------


async def test_end_to_end_with_fake_model_commits_messages_in_seq_order(database: Database) -> None:
    env = build_env(
        database,
        script=[speak("我先说一句。"), speak("我也说一句。"), speak("那我跟一句。")],
    )

    for index in range(3):
        ack = await env.runner.run_command(
            env.scene_id, request_id=f"step-{index}", command=ControlCommandType.STEP
        )
        assert ack.accepted is True

    messages = env.runtime.list_messages(env.scene_id)
    assert [message.text for message in messages] == ["我先说一句。", "我也说一句。", "那我跟一句。"]
    assert [message.seq for message in messages] == [1, 2, 3]
    assert [message.actor_id for message in messages] == env.agent_ids

    # 角色集合与快照都没有被运行影响。
    assert len(env.scene_repo.list_agents(env.scene_id)) == 3
    assert env.runner.call_count(env.scene_id) == 3


async def test_pass_produces_no_message_but_still_advances_cursor(database: Database) -> None:
    env = build_env(database, script=[ActionDraft(action=ActionType.PASS)])

    await env.runner.run_command(env.scene_id, request_id="s1", command=ControlCommandType.STEP)

    assert env.runtime.list_messages(env.scene_id) == []
    turns = env.runtime.list_turns(env.scene_id)
    assert turns[0]["status"] == TurnStatus.SUCCEEDED.value
    assert turns[0]["action"] == ActionType.PASS.value
    cursor = env.runtime.get_cursor(env.scene_id, env.agent_ids[0])
    assert cursor is not None
    assert cursor.startup_opportunity_consumed is True


# --- A2 单步只执行一次调用 -----------------------------------------------------


async def test_single_step_makes_exactly_one_call_and_pauses(database: Database) -> None:
    env = build_env(database, script=[speak("一句话。"), speak("第二句。")])

    ack = await env.runner.run_command(env.scene_id, request_id="s1", command=ControlCommandType.STEP)

    assert env.runner.call_count(env.scene_id) == 1
    assert ack.run_state is RunState.PAUSED
    assert ack.pause_reason is PauseReason.MANUAL


async def test_step_on_ended_scene_is_rejected(database: Database) -> None:
    env = build_env(database)
    await env.runner.run_command(env.scene_id, request_id="stop", command=ControlCommandType.STOP)

    ack = await env.runner.run_command(
        env.scene_id, request_id="step-after-end", command=ControlCommandType.STEP
    )

    assert ack.accepted is False
    assert ack.run_state is RunState.ENDED
    assert env.runner.call_count(env.scene_id) == 0


# --- 自动运行 -----------------------------------------------------------------


async def test_start_runs_until_no_new_information(database: Database) -> None:
    """全员 PASS → 无新外部信息 → 自动暂停（PRD 5.1）。"""

    env = build_env(database, default_draft=ActionDraft(action=ActionType.PASS))

    await env.runner.run_command(env.scene_id, request_id="run", command=ControlCommandType.START)
    assert await env.runner.wait_until_idle(env.scene_id, timeout=10)

    scene = env.scene_repo.get_scene(env.scene_id)
    assert scene is not None
    assert scene.status is RunState.PAUSED
    assert scene.pause_reason is PauseReason.NO_NEW_INFORMATION
    assert env.runner.call_count(env.scene_id) == 3, "每个角色各有一次启动机会"


async def test_start_runs_until_budget_exhausted_then_ends(database: Database) -> None:
    env = build_env(
        database,
        script=[speak(f"第{i}句。") for i in range(10)],
        max_role_requests=2,
    )

    await env.runner.run_command(env.scene_id, request_id="run", command=ControlCommandType.START)
    assert await env.runner.wait_until_idle(env.scene_id, timeout=10)

    scene = env.scene_repo.get_scene(env.scene_id)
    assert scene is not None
    assert scene.status is RunState.ENDED
    assert env.runner.call_count(env.scene_id) == 2
    assert env.runtime.budget_used(env.scene_id)["role_requests_used"] == 2


async def test_pause_stops_the_loop_at_the_call_boundary(database: Database) -> None:
    """暂停在**当前调用边界**生效：当前调用收尾，但不新建下一次调用（PRD 5.2）。"""

    port = GatedModelPort(speak("正在说话。"))
    env = build_env(database, port=port)

    await env.runner.run_command(env.scene_id, request_id="run", command=ControlCommandType.START)
    await asyncio.wait_for(port.started.wait(), timeout=5)
    assert env.runner.call_count(env.scene_id) == 1

    pause_ack = await env.runner.run_command(
        env.scene_id, request_id="pause", command=ControlCommandType.PAUSE
    )
    # 在途调用期间请求暂停 → PAUSING，等当前调用收尾。
    assert pause_ack.run_state is RunState.PAUSING

    port.release.set()
    assert await env.runner.wait_until_idle(env.scene_id, timeout=10)

    scene = env.scene_repo.get_scene(env.scene_id)
    assert scene is not None
    assert scene.status is RunState.PAUSED
    assert scene.pause_reason is PauseReason.MANUAL
    assert env.runner.call_count(env.scene_id) == 1, "不得新建下一次调用"


# --- A3／A4 暂停排序 ----------------------------------------------------------


class GatedModelPort:
    """可控端口：把一次调用挂在门口，便于在「调用进行中」注入事件。"""

    def __init__(self, draft: ActionDraft) -> None:
        self._draft = draft
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def generate_action(self, request):
        from role_theater.contracts import ModelActionResponse

        self.calls += 1
        self.started.set()
        await self.release.wait()
        return ModelActionResponse(
            ok=True,
            draft=self._draft,
            prompt_template_id=request.prompt_template_id,
            requested_model=request.params.model,
            returned_model=request.params.model,
        )


async def test_events_injected_during_a_call_activate_after_it_in_order(
    database: Database,
) -> None:
    port = GatedModelPort(speak("我正在说话。"))
    env = build_env(database, port=port)

    step = asyncio.create_task(
        env.runner.run_command(env.scene_id, request_id="s1", command=ControlCommandType.STEP)
    )
    await asyncio.wait_for(port.started.wait(), timeout=5)

    first = await env.runner.inject_event(
        env.scene_id,
        request_id="e1",
        submission=EventSubmission(body="第一件事。", visibility=EventVisibility.ALL),
    )
    second = await env.runner.inject_event(
        env.scene_id,
        request_id="e2",
        submission=EventSubmission(
            body="第二件事。", visibility=EventVisibility.TARGETED, target_agent_id=env.agent_ids[0]
        ),
    )

    # 调用进行中：先保存为待生效，界面显示「已接受」。
    assert first.event_status == EventStatus.ACCEPTED.value
    assert second.event_status == EventStatus.ACCEPTED.value
    assert all(
        event.status is EventStatus.ACCEPTED for event in env.runtime.list_events(env.scene_id)
    )

    port.release.set()
    ack = await asyncio.wait_for(step, timeout=5)
    assert ack.accepted is True

    events = env.runtime.list_events(env.scene_id)
    assert [event.status for event in events] == [EventStatus.EFFECTIVE, EventStatus.EFFECTIVE]
    assert [event.body for event in events] == ["第一件事。", "第二件事。"]
    # 按接受顺序生效。
    assert [event.seq for event in events] == [2, 3], "seq 1 是本次发言"


async def test_event_injected_while_paused_takes_effect_without_auto_resume(
    database: Database,
) -> None:
    env = build_env(database, script=[speak("一句话。")])
    await env.runner.run_command(env.scene_id, request_id="s1", command=ControlCommandType.STEP)
    calls_before = env.runner.call_count(env.scene_id)

    ack = await env.runner.inject_event(
        env.scene_id,
        request_id="e1",
        submission=EventSubmission(body="停电了。", visibility=EventVisibility.ALL),
    )

    assert ack.event_status == EventStatus.EFFECTIVE.value
    scene = env.scene_repo.get_scene(env.scene_id)
    assert scene is not None and scene.status is RunState.PAUSED, "不自动继续"
    assert env.runner.call_count(env.scene_id) == calls_before


# --- A5 结束请求 --------------------------------------------------------------


async def test_events_are_rejected_after_a_stop_request(database: Database) -> None:
    env = build_env(database)
    await env.runner.run_command(env.scene_id, request_id="stop", command=ControlCommandType.STOP)

    ack = await env.runner.inject_event(
        env.scene_id,
        request_id="e-late",
        submission=EventSubmission(body="太晚了。", visibility=EventVisibility.ALL),
    )

    assert ack.accepted is False
    assert "不再接受新事件" in (ack.detail or "")
    assert env.runtime.list_events(env.scene_id) == []


async def test_accepted_events_are_committed_at_the_stop_boundary(database: Database) -> None:
    port = GatedModelPort(speak("最后一句。"))
    env = build_env(database, port=port)

    step = asyncio.create_task(
        env.runner.run_command(env.scene_id, request_id="s1", command=ControlCommandType.STEP)
    )
    await asyncio.wait_for(port.started.wait(), timeout=5)

    await env.runner.inject_event(
        env.scene_id,
        request_id="e1",
        submission=EventSubmission(body="结束前的事件。", visibility=EventVisibility.ALL),
    )
    stop = asyncio.create_task(
        env.runner.run_command(env.scene_id, request_id="stop", command=ControlCommandType.STOP)
    )

    port.release.set()
    stop_ack = await asyncio.wait_for(stop, timeout=5)
    await asyncio.wait_for(step, timeout=5)

    events = env.runtime.list_events(env.scene_id)
    assert [event.status for event in events] == [EventStatus.EFFECTIVE]
    assert stop_ack.run_state in (RunState.ENDED, RunState.STOPPING)

    # 结束之后不再触发新行动。
    assert await env.runner.wait_until_idle(env.scene_id, timeout=5)
    assert env.runner.call_count(env.scene_id) == 1
    scene = env.scene_repo.get_scene(env.scene_id)
    assert scene is not None and scene.status is RunState.ENDED


# --- A6 幂等 ------------------------------------------------------------------


async def test_repeated_command_returns_existing_result_without_new_call(
    database: Database,
) -> None:
    env = build_env(database, script=[speak("只调用一次。")])

    first = await env.runner.run_command(
        env.scene_id, request_id="same", command=ControlCommandType.STEP
    )
    second = await env.runner.run_command(
        env.scene_id, request_id="same", command=ControlCommandType.STEP
    )

    assert first.deduplicated is False
    assert second.deduplicated is True
    assert second.run_state is first.run_state
    assert env.runner.call_count(env.scene_id) == 1
    assert len(env.runtime.list_messages(env.scene_id)) == 1


async def test_repeated_event_command_is_idempotent(database: Database) -> None:
    env = build_env(database)

    first = await env.runner.inject_event(
        env.scene_id,
        request_id="ev",
        submission=EventSubmission(body="只生效一次。", visibility=EventVisibility.ALL),
    )
    second = await env.runner.inject_event(
        env.scene_id,
        request_id="ev",
        submission=EventSubmission(body="只生效一次。", visibility=EventVisibility.ALL),
    )

    assert second.deduplicated is True
    assert second.event_id == first.event_id
    assert len(env.runtime.list_events(env.scene_id)) == 1


# --- A7／A8／A9 预算 ----------------------------------------------------------


async def test_failed_call_consumes_budget_and_pauses(database: Database) -> None:
    env = build_env(
        database,
        script=[ModelFailure(kind=ModelFailureKind.PROVIDER_ERROR, detail="boom")],
    )

    ack = await env.runner.run_command(env.scene_id, request_id="s1", command=ControlCommandType.STEP)

    assert ack.run_state is RunState.PAUSED
    assert ack.pause_reason is PauseReason.PROVIDER_ERROR
    assert env.runtime.budget_used(env.scene_id)["role_requests_used"] == 1, "失败不退款"
    turns = env.runtime.list_turns(env.scene_id)
    assert turns[0]["status"] == TurnStatus.FAILED.value
    assert turns[0]["budget_consumed"] == 1


async def test_unknown_send_result_consumes_budget_and_is_marked_unknown(
    database: Database,
) -> None:
    env = build_env(
        database,
        script=[ModelFailure(kind=ModelFailureKind.UNKNOWN_REQUEST, detail="网络异常")],
    )

    await env.runner.run_command(env.scene_id, request_id="s1", command=ControlCommandType.STEP)

    turns = env.runtime.list_turns(env.scene_id)
    assert turns[0]["status"] == TurnStatus.UNKNOWN.value
    assert env.runtime.budget_used(env.scene_id)["role_requests_used"] == 1


async def test_context_limit_pauses_without_consuming_budget(database: Database) -> None:
    env = build_env(database, prompt_char_limit=10)

    ack = await env.runner.run_command(env.scene_id, request_id="s1", command=ControlCommandType.STEP)

    assert ack.run_state is RunState.PAUSED
    assert ack.pause_reason is PauseReason.CONTEXT_LIMIT
    assert env.runtime.budget_used(env.scene_id)["role_requests_used"] == 0, "未发送不占用"
    assert env.runner.call_count(env.scene_id) == 0
    assert env.runtime.list_turns(env.scene_id) == []


async def test_missing_config_pauses_without_consuming_budget(database: Database) -> None:
    env = build_env(database, port=DeepSeekModelClient(api_key=None))

    ack = await env.runner.run_command(env.scene_id, request_id="s1", command=ControlCommandType.STEP)

    assert ack.run_state is RunState.PAUSED
    assert ack.pause_reason is PauseReason.PROVIDER_ERROR
    assert env.runtime.budget_used(env.scene_id)["role_requests_used"] == 0
    turns = env.runtime.list_turns(env.scene_id)
    assert turns[0]["failure_kind"] == ModelFailureKind.MISSING_CONFIG.value
    assert turns[0]["budget_consumed"] == 0
    assert turns[0]["sent"] == 0


async def test_resume_after_failure_retries_with_a_new_attempt(database: Database) -> None:
    """人工重试是新的显式请求，不冒充精确重放（PRD 5.4）。"""

    env = build_env(
        database,
        script=[
            ModelFailure(kind=ModelFailureKind.TIMEOUT, detail="超时"),
            speak("这次成功了。"),
        ],
    )

    await env.runner.run_command(env.scene_id, request_id="s1", command=ControlCommandType.STEP)
    await env.runner.run_command(env.scene_id, request_id="s2", command=ControlCommandType.STEP)

    turns = env.runtime.list_turns(env.scene_id)
    assert [turn["status"] for turn in turns] == [TurnStatus.FAILED.value, TurnStatus.SUCCEEDED.value]
    assert len({turn["attempt_id"] for turn in turns}) == 2
    assert env.runtime.budget_used(env.scene_id)["role_requests_used"] == 2


# --- A11 重启恢复 -------------------------------------------------------------


async def test_restart_marks_pending_unknown_and_pauses_without_replay(
    database: Database,
) -> None:
    env = build_env(database, script=[speak("在途请求。")])

    # 模拟进程在派发后崩溃：留下一条 PENDING 行动。
    env.runtime.insert_turn(
        action_id="act-x",
        turn_id="turn-x",
        attempt_id="att-x",
        scene_id=env.scene_id,
        actor_id=env.agent_ids[0],
        input_cursor_seq=0,
        prompt_template_id="role_action@m02",
        created_at=CLOCK,
    )
    env.runtime.set_scene_state(env.scene_id, status=RunState.RUNNING, started_at=CLOCK)

    recovered = env.runner.recover_after_restart()

    assert recovered == [env.scene_id]
    turns = env.runtime.list_turns(env.scene_id)
    assert turns[0]["status"] == TurnStatus.UNKNOWN.value
    assert turns[0]["failure_kind"] == ModelFailureKind.UNKNOWN_REQUEST.value
    scene = env.scene_repo.get_scene(env.scene_id)
    assert scene is not None
    assert scene.status is RunState.PAUSED
    assert scene.pause_reason is PauseReason.PROCESS_INTERRUPT
    # 不自动恢复付费请求。
    assert env.runner.call_count(env.scene_id) == 0
    assert env.runtime.budget_used(env.scene_id)["role_requests_used"] == 1


def test_recover_is_a_noop_when_nothing_is_pending(database: Database) -> None:
    env = build_env(database)

    assert env.runner.recover_after_restart() == []


# --- A12 视角一致 -------------------------------------------------------------


async def test_viewpoint_matches_the_context_used_by_the_caller(database: Database) -> None:
    env = build_env(database, script=[speak("可见的一句话。")])
    await env.runner.run_command(env.scene_id, request_id="s1", command=ControlCommandType.STEP)

    _, context = env.runner.viewpoint(env.scene_id, env.agent_ids[1])

    assert "可见的一句话。" in context.prompt
    assert context.actor_id == env.agent_ids[1]
    # 本人私有资料在内，他人私有资料不在内。
    assert "私有背景1" in context.prompt
    assert "私有背景0" not in context.prompt


# --- A13 历史只读 -------------------------------------------------------------


async def test_reading_timeline_does_not_call_the_model(database: Database) -> None:
    env = build_env(database, script=[speak("一句话。")])
    await env.runner.run_command(env.scene_id, request_id="s1", command=ControlCommandType.STEP)
    calls = env.runner.call_count(env.scene_id)

    env.runtime.timeline(env.scene_id)
    env.runtime.list_turns(env.scene_id)
    env.runtime.budget_used(env.scene_id)

    assert env.runner.call_count(env.scene_id) == calls


# --- 其他不变量 ---------------------------------------------------------------


async def test_lock_is_applied_when_the_first_request_starts(database: Database) -> None:
    """首次实际角色请求开始后锁定背景与人物设定（PRD 3.2）。"""

    env = build_env(database, script=[speak("一句话。")])

    await env.runner.run_command(env.scene_id, request_id="s1", command=ControlCommandType.STEP)

    scene = env.scene_repo.get_scene(env.scene_id)
    assert scene is not None
    assert scene.budget.locked_at is not None


async def test_cursor_only_advances_on_success(database: Database) -> None:
    env = build_env(
        database,
        script=[
            ModelFailure(kind=ModelFailureKind.SCHEMA_INVALID, detail="字段非法"),
            speak("成功的一次。"),
        ],
    )

    await env.runner.run_command(env.scene_id, request_id="s1", command=ControlCommandType.STEP)
    assert env.runtime.get_cursor(env.scene_id, env.agent_ids[0]) is None

    await env.runner.run_command(env.scene_id, request_id="s2", command=ControlCommandType.STEP)
    cursor = env.runtime.get_cursor(env.scene_id, env.agent_ids[0])
    assert cursor is not None
    assert cursor.startup_opportunity_consumed is True


async def test_pending_turn_is_written_before_the_model_call(database: Database) -> None:
    """派发前先落盘 PENDING（崩溃可恢复的依据）。"""

    port = GatedModelPort(speak("在途。"))
    env = build_env(database, port=port)

    step = asyncio.create_task(
        env.runner.run_command(env.scene_id, request_id="s1", command=ControlCommandType.STEP)
    )
    await asyncio.wait_for(port.started.wait(), timeout=5)

    turns = env.runtime.list_turns(env.scene_id)
    assert len(turns) == 1
    assert turns[0]["status"] == PENDING_TURN_STATUS

    port.release.set()
    await asyncio.wait_for(step, timeout=5)
    assert env.runtime.list_turns(env.scene_id)[0]["status"] == TurnStatus.SUCCEEDED.value


async def test_model_params_and_template_id_are_recorded(database: Database) -> None:
    env = build_env(database, script=[speak("记录一次。")])

    await env.runner.run_command(env.scene_id, request_id="s1", command=ControlCommandType.STEP)

    turn = env.runtime.list_turns(env.scene_id)[0]
    assert turn["prompt_template_id"] == "role_action@simulation.p1.1"
    assert turn["requested_model"] == ModelParams().model
    assert turn["returned_model"] == ModelParams().model


# --- A14 引用闭环（2026-09-26 真实联调 SCHEMA_INVALID 的回归） -------------------


class _ReplyingTransport(httpx.AsyncBaseTransport):
    """像真实模型那样读提示词：第一条发言不作引用，之后引用最近一条发言。

    ``alias`` 决定回写形式——``"id"`` 是逐字复制的消息 ID，``"seq"`` 是真实联调
    里模型实际回的 ``#序号`` 整数，其余按模板生成 ``#序号`` 的文本写法。
    """

    def __init__(self, alias: str = "id") -> None:
        self.alias = alias
        self.prompts: list[str] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        prompt = payload["messages"][-1]["content"]
        self.prompts.append(prompt)

        visible = re.findall(r"\[#(\d+) \| ([^\]]+)\]", prompt)
        if not visible:
            content = json.dumps(
                {"action": "SPEAK", "text": "我先说一句。", "reply_to_message_id": None}
            )
        else:
            seq, message_id = visible[-1]
            if self.alias == "id":
                reference: object = message_id
            elif self.alias == "seq":
                reference = int(seq)
            else:
                reference = self.alias.format(seq=seq)
            content = json.dumps(
                {"action": "SPEAK", "text": "回应一下。", "reply_to_message_id": reference}
            )

        return httpx.Response(
            200,
            json={
                "id": "req-reply",
                "model": "deepseek-flash-2026-09-10",
                "choices": [
                    {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}
                ],
                "usage": {"prompt_tokens": 120, "completion_tokens": 18},
            },
        )


@pytest.mark.parametrize("alias", ["id", "seq", "#{seq}", "[#{seq}]"])
async def test_reply_reference_taken_from_the_prompt_is_committed(
    database: Database, alias: str
) -> None:
    """提示词给出的引用标识必须真的可用：模型回 ID 或回序号都要成功落盘。"""

    transport = _ReplyingTransport(alias)
    env = build_env(
        database, port=DeepSeekModelClient(api_key="placeholder-key", transport=transport)
    )

    await env.runner.run_command(env.scene_id, request_id="s1", command=ControlCommandType.STEP)
    await env.runner.run_command(env.scene_id, request_id="s2", command=ControlCommandType.STEP)

    turns = env.runtime.list_turns(env.scene_id)
    assert [turn["status"] for turn in turns] == [
        TurnStatus.SUCCEEDED.value,
        TurnStatus.SUCCEEDED.value,
    ], [turn["failure_detail"] for turn in turns]

    messages = env.runtime.list_messages(env.scene_id)
    assert len(messages) == 2
    # 前提：第二次调用的提示词确实把第一条发言的 ID 摆在了模型眼前。
    assert messages[0].message_id in transport.prompts[1]
    # 结论：模型照提示词写出的引用真的落盘了。
    assert messages[1].reply_to_message_id == messages[0].message_id


# --- 运行一致性修复：跨模块回归（2026-09-28） ---------------------------------


@pytest.mark.parametrize("draft", [speak("暂停前的一句话。"), ActionDraft(action=ActionType.PASS)])
async def test_step_pause_during_model_wait_finishes_paused(
    database: Database, draft: ActionDraft
) -> None:
    port = GatedModelPort(draft)
    env = build_env(database, port=port)
    step = asyncio.create_task(
        env.runner.run_command(env.scene_id, request_id="step", command=ControlCommandType.STEP)
    )
    await asyncio.wait_for(port.started.wait(), timeout=5)
    pause = await env.runner.run_command(
        env.scene_id, request_id="pause", command=ControlCommandType.PAUSE
    )
    assert pause.run_state is RunState.PAUSING
    port.release.set()
    ack = await asyncio.wait_for(step, timeout=5)
    assert ack.run_state is RunState.PAUSED
    scene = env.scene_repo.get_scene(env.scene_id)
    assert scene.status is RunState.PAUSED
    assert scene.pause_reason is PauseReason.MANUAL
    assert not env.runner.is_busy(env.scene_id)
    assert env.runner.call_count(env.scene_id) == 1
    assert env.runtime.list_turns(env.scene_id)[0]["status"] == TurnStatus.SUCCEEDED.value


class TracingScheduler(Scheduler):
    def __init__(self) -> None:
        super().__init__()
        self.decisions = []

    def select(self, state):
        outcome = super().select(state)
        self.decisions.append(outcome)
        return outcome


@pytest.mark.parametrize("third_actor,normal_actor", [(0, 2), (2, 0)])
async def test_runner_caps_requested_priority_across_roles_and_resets_after_rotation(
    database: Database, third_actor: int, normal_actor: int
) -> None:
    env = build_env(database)
    a, b, _ = env.agent_ids
    env.runner._model = MockModelPort(script=[
        speak("第一句。", requested_speaker_id=b),
        speak("第二句。", requested_speaker_id=env.agent_ids[third_actor]),
        speak("第三句。", requested_speaker_id=b),
        speak("轮转后重新点名。", requested_speaker_id=b),
        speak("重新获得点名机会。"),
    ])
    scheduler = TracingScheduler()
    env.runner._scheduler = scheduler
    for index in range(5):
        await env.runner.run_command(
            env.scene_id, request_id=f"step-{index}", command=ControlCommandType.STEP
        )
    decisions = scheduler.decisions
    assert [x.actor_id for x in decisions] == [a, b, env.agent_ids[third_actor], env.agent_ids[normal_actor], b]
    assert [x.reason for x in decisions[1:3]] == [SchedulerReason.REQUESTED_SPEAKER_PRIORITY] * 2
    assert decisions[3].reason is not SchedulerReason.REQUESTED_SPEAKER_PRIORITY
    assert decisions[4].reason is SchedulerReason.REQUESTED_SPEAKER_PRIORITY


async def test_pending_and_budget_reservation_roll_back_together(database: Database) -> None:
    env = build_env(database, script=[speak("不得派发。")])
    with database.transaction() as conn:
        conn.execute("CREATE TRIGGER fail_budget BEFORE INSERT ON scene_budget_usage "
                     "BEGIN SELECT RAISE(ABORT, 'budget fault'); END")
    with pytest.raises(sqlite3.IntegrityError, match="budget fault"):
        await env.runner.run_command(env.scene_id, request_id="step", command=ControlCommandType.STEP)
    assert env.runtime.list_turns(env.scene_id) == []
    assert env.runtime.budget_used(env.scene_id)["role_requests_used"] == 0
    assert env.runner.call_count(env.scene_id) == 0
    assert not env.runner.is_busy(env.scene_id)


@pytest.mark.parametrize("stage", ["turn", "cursor", "scheduler"])
async def test_success_commit_failure_exposes_no_partial_action(
    database: Database, stage: str
) -> None:
    env = build_env(database, script=[speak("必须整体提交。")])
    target = {
        "turn": "BEFORE UPDATE ON scene_turns WHEN NEW.status = 'SUCCEEDED'",
        "cursor": "BEFORE INSERT ON role_cursors",
        "scheduler": "BEFORE INSERT ON scene_scheduler_state",
    }[stage]
    with database.transaction() as conn:
        conn.execute(f"CREATE TRIGGER fail_success {target} "
                     "BEGIN SELECT RAISE(ABORT, 'success fault'); END")
    with pytest.raises(sqlite3.IntegrityError, match="success fault"):
        await env.runner.run_command(env.scene_id, request_id="step", command=ControlCommandType.STEP)
    assert env.runtime.list_messages(env.scene_id) == []
    assert env.runtime.last_seq(env.scene_id) == 0
    assert env.runtime.get_cursor(env.scene_id, env.agent_ids[0]) is None
    assert env.runtime.list_turns(env.scene_id)[0]["status"] == PENDING_TURN_STATUS
    assert env.runtime.budget_used(env.scene_id)["role_requests_used"] == 1
    assert env.runtime.requested_priority_streak(env.scene_id) == 0
    assert env.runner.recover_after_restart() == [env.scene_id]
    assert env.runtime.list_turns(env.scene_id)[0]["status"] == TurnStatus.UNKNOWN.value
    assert env.runtime.list_messages(env.scene_id) == []


async def test_scheduler_update_failure_rolls_back_pass_and_preserves_prior_action(
    database: Database,
) -> None:
    env = build_env(database)
    env.runner._model = MockModelPort(script=[
        speak("请第二位回应。", requested_speaker_id=env.agent_ids[1]),
        ActionDraft(action=ActionType.PASS),
    ])
    await env.runner.run_command(env.scene_id, request_id="first", command=ControlCommandType.STEP)
    original = env.runtime.list_messages(env.scene_id)
    with database.transaction() as conn:
        conn.execute("CREATE TRIGGER fail_scheduler BEFORE UPDATE ON scene_scheduler_state "
                     "BEGIN SELECT RAISE(ABORT, 'scheduler fault'); END")
    with pytest.raises(sqlite3.IntegrityError, match="scheduler fault"):
        await env.runner.run_command(env.scene_id, request_id="second", command=ControlCommandType.STEP)
    assert env.runtime.list_messages(env.scene_id) == original
    assert sorted(x["status"] for x in env.runtime.list_turns(env.scene_id)) == ["PENDING", "SUCCEEDED"]
    assert env.runtime.get_cursor(env.scene_id, env.agent_ids[1]) is None
    assert env.runtime.requested_priority_streak(env.scene_id) == 0
    assert env.runtime.budget_used(env.scene_id)["role_requests_used"] == 2


async def test_requested_priority_streak_survives_runner_restart(database: Database) -> None:
    env = build_env(database)
    a, b, c = env.agent_ids
    port = MockModelPort(script=[
        speak("A 点 B。", requested_speaker_id=b),
        speak("B 点 A。", requested_speaker_id=a),
        speak("A 再点 B。", requested_speaker_id=b),
        speak("C 轮转后点 B。", requested_speaker_id=b),
        speak("B 回应。"),
    ])
    env.runner._model = port
    for i in range(3):
        await env.runner.run_command(env.scene_id, request_id=f"first-{i}", command=ControlCommandType.STEP)
    assert env.runtime.requested_priority_streak(env.scene_id) == 2
    reopened = Database(database.path)
    runtime = RuntimeRepository(reopened)
    trace = TracingScheduler()
    restarted = SceneRunner(
        database=reopened, scenes=SceneRepository(reopened), runtime=runtime,
        model_port=port, scheduler=trace, clock=lambda: CLOCK, id_factory=Counter("restart"),
    )
    assert restarted.recover_after_restart() == []
    assert runtime.requested_priority_streak(env.scene_id) == 2
    await restarted.run_command(env.scene_id, request_id="after-restart", command=ControlCommandType.STEP)
    assert trace.decisions[0].actor_id == c
    assert trace.decisions[0].reason is not SchedulerReason.REQUESTED_SPEAKER_PRIORITY
    assert runtime.requested_priority_streak(env.scene_id) == 0
    await restarted.run_command(env.scene_id, request_id="after-rotation", command=ControlCommandType.STEP)
    assert trace.decisions[1].actor_id == b
    assert trace.decisions[1].reason is SchedulerReason.REQUESTED_SPEAKER_PRIORITY
    assert runtime.requested_priority_streak(env.scene_id) == 1


async def test_pass_counts_priority_and_normal_pass_resets_streak(database: Database) -> None:
    env = build_env(database)
    env.runner._model = MockModelPort(script=[
        speak("点名。", requested_speaker_id=env.agent_ids[1]),
        ActionDraft(action=ActionType.PASS), ActionDraft(action=ActionType.PASS),
    ])
    for index, expected in enumerate([0, 1, 0]):
        await env.runner.run_command(env.scene_id, request_id=f"step-{index}", command=ControlCommandType.STEP)
        assert env.runtime.requested_priority_streak(env.scene_id) == expected
    assert len(env.runtime.list_messages(env.scene_id)) == 1


class GatedFailureModelPort(GatedModelPort):
    async def generate_action(self, request):
        response = await super().generate_action(request)
        return response.model_copy(update={
            "ok": False, "draft": None,
            "failure": ModelFailure(kind=ModelFailureKind.TIMEOUT, detail="可控超时"),
        })


@pytest.mark.parametrize("failure,stop", [(True, False), (False, True), (True, True)])
async def test_step_pause_preserves_failure_reason_and_stop_wins(
    database: Database, failure: bool, stop: bool
) -> None:
    port_type = GatedFailureModelPort if failure else GatedModelPort
    port = port_type(speak("当前调用。"))
    env = build_env(database, port=port)
    step = asyncio.create_task(
        env.runner.run_command(env.scene_id, request_id="step", command=ControlCommandType.STEP)
    )
    await asyncio.wait_for(port.started.wait(), timeout=5)
    await env.runner.run_command(env.scene_id, request_id="pause", command=ControlCommandType.PAUSE)
    if stop:
        await env.runner.run_command(env.scene_id, request_id="stop", command=ControlCommandType.STOP)
    port.release.set()
    ack = await asyncio.wait_for(step, timeout=5)
    expected = RunState.ENDED if stop else RunState.PAUSED
    assert ack.run_state is expected
    scene = env.scene_repo.get_scene(env.scene_id)
    assert scene.status is expected
    assert scene.pause_reason is (None if stop else PauseReason.PROVIDER_ERROR)
    assert env.runner.call_count(env.scene_id) == 1
    assert not env.runner.is_busy(env.scene_id)


async def test_model_wait_does_not_hold_sqlite_write_transaction(database: Database) -> None:
    port = GatedModelPort(speak("等待期间。"))
    env = build_env(database, port=port)
    step = asyncio.create_task(
        env.runner.run_command(env.scene_id, request_id="step", command=ControlCommandType.STEP)
    )
    await asyncio.wait_for(port.started.wait(), timeout=5)
    try:
        with database.connection() as conn:
            conn.execute("PRAGMA busy_timeout = 0")
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE scenes SET title = title WHERE scene_id = ?", (env.scene_id,))
            conn.execute("COMMIT")
        assert env.runtime.budget_used(env.scene_id)["role_requests_used"] == 1
        assert env.runtime.list_turns(env.scene_id)[0]["status"] == PENDING_TURN_STATUS
    finally:
        port.release.set()
        await asyncio.wait_for(step, timeout=5)


def test_old_database_upgrade_preserves_records_and_resets_unreliable_role_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = Database(tmp_path / "old.db")
    all_migrations = migrator.discover_migrations()
    with monkeypatch.context() as patch:
        patch.setattr(migrator, "discover_migrations", lambda: all_migrations[:3])
        assert old.migrate() == [1, 2, 3]
    seed = Database(tmp_path / "seed-current.db")
    seed.migrate()
    env = build_env(seed)
    with seed.connection() as source, old.transaction() as target:
        for table in ["agent_templates", "scenes", "scene_agents"]:
            columns = [row["name"] for row in target.execute(f"PRAGMA table_info({table})")]
            names = ",".join(columns)
            for row in source.execute(f"SELECT {names} FROM {table}"):
                target.execute(f"INSERT INTO {table} ({names}) VALUES ({','.join('?' for _ in columns)})", tuple(row))
    env.runtime = RuntimeRepository(old)
    env.runtime.insert_turn(
        action_id="old-action", turn_id="old-turn", attempt_id="old-attempt",
        scene_id=env.scene_id, actor_id=env.agent_ids[0], input_cursor_seq=0,
        prompt_template_id="role_action@m02.1", created_at=CLOCK,
    )
    seq = env.runtime.next_seq(env.scene_id)
    with old.transaction() as conn:
        conn.execute("INSERT INTO messages (message_id, scene_id, seq, actor_id, text, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("old-message", env.scene_id, seq, env.agent_ids[0], "升级前的消息。", CLOCK.isoformat()))
    env.runtime.finish_turn(
        "old-attempt", status=TurnStatus.SUCCEEDED, finished_at=CLOCK,
        action=ActionType.SPEAK.value, text="升级前的消息。", message_id="old-message",
    )
    # Seed the historical 003 schema with its original columns.
    with old.transaction() as conn:
        conn.execute("INSERT INTO role_cursors (scene_id,agent_id,processed_seq,startup_opportunity_consumed,consecutive_requested_priority) VALUES (?,?,1,1,2)",
                     (env.scene_id, env.agent_ids[0]))
    with old.connection() as conn:
        messages = [dict(r) for r in conn.execute("SELECT * FROM messages")]
        turns = [dict(r) for r in conn.execute("SELECT * FROM scene_turns")]
    budget = env.runtime.budget_used(env.scene_id)
    assert old.migrate() == [4, 5, 6, 7, 8, 9]
    assert old.migrate() == []
    with old.connection() as conn:
        for table, expected in [("messages", messages), ("scene_turns", turns)]:
            actual = [dict(r) for r in conn.execute(f"SELECT * FROM {table}")]
            assert [{k: r[k] for k in expected[0]} for r in actual] == expected
    assert env.runtime.list_messages(env.scene_id)[0].visibility == "PUBLIC"
    assert env.runtime.action_records(env.scene_id)[0].draft.recipient_id is None
    assert env.runtime.list_turns(env.scene_id)[0]["prompt_template_id"] == "role_action@m02.1"
    assert env.runtime.budget_used(env.scene_id) == budget
    assert env.runtime.requested_priority_streak(env.scene_id) == 0
    cursor = env.runtime.get_cursor(env.scene_id, env.agent_ids[0])
    assert cursor.processed_seq == 1
    assert cursor.startup_opportunity_consumed
    assert cursor.consecutive_requested_priority == 0


async def test_unsent_failure_and_budget_refund_roll_back_together(database: Database) -> None:
    env = build_env(database, script=[ModelFailure(kind=ModelFailureKind.MISSING_CONFIG, detail="未派发")])
    with database.transaction() as conn:
        conn.execute("CREATE TRIGGER fail_finish BEFORE UPDATE ON scene_turns WHEN NEW.status = 'FAILED' "
                     "BEGIN SELECT RAISE(ABORT, 'finish fault'); END")
    with pytest.raises(sqlite3.IntegrityError, match="finish fault"):
        await env.runner.run_command(env.scene_id, request_id="step", command=ControlCommandType.STEP)
    turn = env.runtime.list_turns(env.scene_id)[0]
    assert turn["status"] == PENDING_TURN_STATUS
    assert turn["budget_consumed"] == 1
    assert env.runtime.budget_used(env.scene_id)["role_requests_used"] == 1
