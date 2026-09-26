"""运行控制、事件、时间线、角色视角与 SSE（PRD 4.3、5.2、5.4、7.2、8）。

SSE 从**已提交**数据按 ``seq`` 补发；数据库是事实来源，订阅者被通知后重新读取，
因此断线重连只靠 `since_seq` 即可追赶，不需要重放模型请求。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from ..contracts import CommandAck, RunStatus
from ..contracts.api_runtime import (
    AgentStatusListView,
    AgentStatusView,
    ControlCommandRequest,
    EventView,
    InjectEventRequest,
    RunStateView,
    ScenarioSummaryView,
    TimelineEntryView,
    TimelineView,
    ViewpointView,
)
from ..domain import DomainNotFoundError
from ..runtime import SceneRunner
from .deps import SceneServiceDep, get_runner

router = APIRouter(prefix="/api/scenes", tags=["m04-runtime"])

#: SSE 心跳间隔（秒）。心跳是**传输层**内容，不进入剧情、不产生 `seq`。
HEARTBEAT_SECONDS = 15.0


def _runner(request: Request) -> SceneRunner:
    return get_runner(request)


def _run_status(runner: SceneRunner, runtime, scene_id: str) -> RunStatus:
    last_seq = runtime.last_seq(scene_id)
    from ..contracts import RunState

    scene = runner._scenes.get_scene(scene_id)  # noqa: SLF001 - 只读快照
    pending = runtime.pending_event_count(scene_id)
    return RunStatus(
        scene_id=scene_id,
        run_state=scene.status if scene else RunState.READY,
        pause_reason=scene.pause_reason if scene else None,
        last_committed_seq=last_seq,
        pending_event_count=pending,
    )


@router.post("/{scene_id}/commands", response_model=CommandAck)
async def run_command(
    scene_id: str,
    payload: ControlCommandRequest,
    request: Request,
    _: SceneServiceDep,
) -> CommandAck:
    """控制命令：`START`／`STEP`／`PAUSE`／`RESUME`／`STOP`（幂等）。"""

    return await _runner(request).run_command(
        scene_id, request_id=payload.request_id, command=payload.command
    )


@router.post("/{scene_id}/events", response_model=CommandAck)
async def inject_event(
    scene_id: str,
    payload: InjectEventRequest,
    request: Request,
    _: SceneServiceDep,
) -> CommandAck:
    """提交人工事件；暂停时立即生效但不自动继续（PRD 4.3）。"""

    return await _runner(request).inject_event(
        scene_id, request_id=payload.request_id, submission=payload.to_submission()
    )


@router.get("/{scene_id}/events", response_model=list[EventView])
async def list_events(scene_id: str, request: Request, _: SceneServiceDep) -> list[EventView]:
    """列出全部事件及其状态（界面区分已接受／已生效）。"""

    runner = _runner(request)
    runtime = request.app.state.runtime_repository
    if runner._scenes.get_scene(scene_id) is None:  # noqa: SLF001
        raise DomainNotFoundError(f"场景不存在：{scene_id}")
    return [EventView(event=event, status=event.status) for event in runtime.list_events(scene_id)]


@router.get("/{scene_id}/timeline", response_model=TimelineView)
async def timeline(
    scene_id: str,
    request: Request,
    _: SceneServiceDep,
    since_seq: int = Query(default=0, ge=0),
) -> TimelineView:
    """历史/时间线：**只读**已保存数据，不调用模型（PRD 5.4）。"""

    runner = _runner(request)
    runtime = request.app.state.runtime_repository
    scene = runner._scenes.get_scene(scene_id)  # noqa: SLF001
    if scene is None:
        raise DomainNotFoundError(f"场景不存在：{scene_id}")

    names = runtime.scene_agent_names(scene_id)
    entries = [
        TimelineEntryView(
            kind=kind,
            seq=seq,
            message=payload if kind == "message" else None,
            event=payload if kind == "event" else None,
            author_name=(names.get(payload.actor_id) if kind == "message" else None),
        )
        for seq, kind, payload in runtime.timeline(scene_id, since_seq=since_seq)
    ]
    used = runtime.budget_used(scene_id)
    return TimelineView(
        scene_id=scene_id,
        status=_run_status(runner, runtime, scene_id),
        last_seq=runtime.last_seq(scene_id),
        role_requests_used=used["role_requests_used"],
        max_role_requests=scene.budget.max_role_requests,
        analysis_requests_used=used["analysis_requests_used"],
        max_analysis_requests=scene.budget.max_analysis_requests,
        entries=entries,
    )


@router.get("/{scene_id}/state", response_model=RunStateView)
async def run_state(scene_id: str, request: Request, _: SceneServiceDep) -> RunStateView:
    """运行状态与预算（含是否有在途调用）。"""

    runner = _runner(request)
    runtime = request.app.state.runtime_repository
    scene = runner._scenes.get_scene(scene_id)  # noqa: SLF001
    if scene is None:
        raise DomainNotFoundError(f"场景不存在：{scene_id}")
    used = runtime.budget_used(scene_id)
    return RunStateView(
        scene_id=scene_id,
        status=scene.status,
        pause_reason=scene.pause_reason,
        role_requests_used=used["role_requests_used"],
        max_role_requests=scene.budget.max_role_requests,
        analysis_requests_used=used["analysis_requests_used"],
        max_analysis_requests=scene.budget.max_analysis_requests,
        in_flight=runner.is_busy(scene_id),
        last_committed_seq=runtime.last_seq(scene_id),
    )


@router.get("/{scene_id}/agents/{agent_id}/viewpoint", response_model=ViewpointView)
async def viewpoint(
    scene_id: str, agent_id: str, request: Request, _: SceneServiceDep
) -> ViewpointView:
    """角色视角：与调用器**同一** ContextBuilder 的输出（PRD 7.2）。"""

    runner = _runner(request)
    scene = runner._scenes.get_scene(scene_id)  # noqa: SLF001
    if scene is None:
        raise DomainNotFoundError(f"场景不存在：{scene_id}")
    if runner._scenes.get_agent(scene_id, agent_id) is None:  # noqa: SLF001
        raise DomainNotFoundError(f"本场角色不存在：{agent_id}")

    _, context = runner.viewpoint(scene_id, agent_id)
    return ViewpointView(
        scene_id=scene_id,
        agent_id=agent_id,
        agent_name=context.actor_name,
        prompt_template_id=context.prompt_template_id,
        cutoff_seq=context.cutoff_seq,
        public_roster=list(context.public_roster),
        visible_seq=[item.seq for item in context.visible_items],
        visible_kinds=[item.kind.value for item in context.visible_items],
        prompt=context.prompt,
    )


@router.get("/{scene_id}/agents/status", response_model=AgentStatusListView)
async def agent_status(
    scene_id: str, request: Request, _: SceneServiceDep
) -> AgentStatusListView:
    """每个本场角色的执行状态（PRD 7.1：角色卡只显示名称与执行状态）。

    只读观察：不调用模型，不产生任何剧情事实。
    """

    runner = _runner(request)
    runtime = request.app.state.runtime_repository
    scene = runner._scenes.get_scene(scene_id)  # noqa: SLF001
    if scene is None:
        raise DomainNotFoundError(f"场景不存在：{scene_id}")

    agents = runner._scenes.list_agents(scene_id)  # noqa: SLF001
    cursors = {cursor.agent_id: cursor for cursor in runtime.list_cursors(scene_id)}
    messages = runtime.list_messages(scene_id)
    speak_counts: dict[str, int] = {}
    for message in messages:
        speak_counts[message.actor_id] = speak_counts.get(message.actor_id, 0) + 1

    # “当前待回应对象”：时间线上最新一条发言的点名（与调度窗口一致）。
    requested: str | None = None
    if messages:
        latest = max(messages, key=lambda item: item.seq)
        requested = latest.requested_speaker_id

    return AgentStatusListView(
        scene_id=scene_id,
        in_flight=runner.is_busy(scene_id),
        agents=[
            AgentStatusView(
                agent_id=agent.agent_id,
                name=agent.name,
                order_index=agent.order_index,
                has_acted=cursors.get(agent.agent_id) is not None,
                startup_opportunity_consumed=(
                    cursors[agent.agent_id].startup_opportunity_consumed
                    if agent.agent_id in cursors
                    else False
                ),
                processed_seq=(
                    cursors[agent.agent_id].processed_seq if agent.agent_id in cursors else 0
                ),
                last_action_at=(
                    cursors[agent.agent_id].last_action_at.isoformat()
                    if agent.agent_id in cursors and cursors[agent.agent_id].last_action_at
                    else None
                ),
                last_action_status=(
                    cursors[agent.agent_id].last_action_status.value
                    if agent.agent_id in cursors and cursors[agent.agent_id].last_action_status
                    else None
                ),
                is_requested=requested == agent.agent_id,
                speak_count=speak_counts.get(agent.agent_id, 0),
            )
            for agent in agents
        ],
    )


@router.get("/{scene_id}/summary", response_model=ScenarioSummaryView)
async def scenario_summary(
    scene_id: str, request: Request, _: SceneServiceDep
) -> ScenarioSummaryView:
    """实际调用计数与失败统计（PRD 1.2 的「实际调用计数」）。"""

    runner = _runner(request)
    runtime = request.app.state.runtime_repository
    scene = runner._scenes.get_scene(scene_id)  # noqa: SLF001
    if scene is None:
        raise DomainNotFoundError(f"场景不存在：{scene_id}")

    turns = runtime.list_turns(scene_id)
    last_failure = next(
        (turn["failure_kind"] for turn in reversed(turns) if turn["failure_kind"]), None
    )
    return ScenarioSummaryView(
        scene_id=scene_id,
        role_requests_used=runtime.budget_used(scene_id)["role_requests_used"],
        max_role_requests=scene.budget.max_role_requests,
        succeeded=sum(1 for turn in turns if turn["status"] == "SUCCEEDED"),
        failed=sum(1 for turn in turns if turn["status"] == "FAILED"),
        unknown=sum(1 for turn in turns if turn["status"] == "UNKNOWN"),
        last_failure_kind=last_failure,
    )


@router.get("/{scene_id}/stream")
async def stream(
    scene_id: str,
    request: Request,
    _: SceneServiceDep,
    since_seq: int = Query(default=0, ge=0),
    replay_limit: int | None = Query(default=None, ge=1, le=1000),
) -> StreamingResponse:
    """SSE：按 ``seq`` 补发已提交时间线，支持断线追赶与去重（PRD 第 8 节）。

    - 每条：``id: <seq>`` + ``event: timeline`` + JSON 数据；
    - 心跳为注释行，**不进入剧情**；
    - ``replay_limit`` 用于有界追赶（补发满 N 条后关闭，客户端可再连）。
    """

    runner = _runner(request)
    runtime = request.app.state.runtime_repository
    scene = runner._scenes.get_scene(scene_id)  # noqa: SLF001
    if scene is None:
        raise DomainNotFoundError(f"场景不存在：{scene_id}")

    async def event_stream() -> AsyncIterator[bytes]:
        cursor = since_seq
        sent = 0
        while True:
            if await request.is_disconnected():  # 页面刷新/断开只影响这条流
                return

            names = runtime.scene_agent_names(scene_id)
            batch = runtime.timeline(scene_id, since_seq=cursor, limit=100)
            for seq, kind, payload in batch:
                data = {
                    "kind": kind,
                    "seq": seq,
                    "payload": payload.model_dump(mode="json"),
                    "author_name": names.get(payload.actor_id) if kind == "message" else None,
                }
                cursor = seq
                sent += 1
                yield (
                    f"id: {seq}\nevent: timeline\n"
                    f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                ).encode("utf-8")
                if replay_limit is not None and sent >= replay_limit:
                    return

            if replay_limit is not None:
                # 有界追赶模式：补发现有条目后立即关闭，不等待后续提交。
                # 客户端（或界面）可带上新的 since_seq 再连。
                return

            current = runner._scenes.get_scene(scene_id)  # noqa: SLF001
            if current is None:
                return
            if current.status.value == "ENDED" and not batch:
                # 会话已结束且已追平：流自然关闭。
                yield b"event: closed\ndata: {}\n\n"
                return

            if not batch:
                # 没有新数据：等待通知或发心跳（心跳不产生 seq）。
                notified = await runner.broadcaster.wait(scene_id, timeout=HEARTBEAT_SECONDS)
                if not notified:
                    yield b": heartbeat\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


__all__ = ["HEARTBEAT_SECONDS", "router"]
