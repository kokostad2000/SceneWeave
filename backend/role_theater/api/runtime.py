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
    ActionHistoryView,
    ConversationListView,
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
    FactStatisticsView,
    RoleActionCountView,
    ReplyRelationView,
)
from ..contracts import ActionDraft
from ..contracts.enums import MessageVisibility
from ..context import TimelineItem, is_visible_to
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


def _check_viewer(runner, scene_id, viewer_id):
    if runner._scenes.get_scene(scene_id) is None:
        raise DomainNotFoundError("场景不存在")
    if viewer_id is not None and runner._scenes.get_agent(scene_id, viewer_id) is None:
        raise DomainNotFoundError("本场角色不存在")


def _visible_entries(runtime, scene_id, viewer_id=None):
    names = runtime.scene_agent_names(scene_id)
    entries = []
    for seq, kind, payload in runtime.timeline(scene_id):
        item = TimelineItem.from_message(payload) if kind == "message" else TimelineItem.from_event(payload)
        if viewer_id is not None and not is_visible_to(item, viewer_id):
            continue
        display_seq = len(entries) + 1 if viewer_id is not None else seq
        shown = payload.model_copy(update={"seq": display_seq})
        entries.append(TimelineEntryView(kind=kind, seq=display_seq,
            message=shown if kind == "message" else None, event=shown if kind == "event" else None,
            author_name=names.get(payload.actor_id) if kind == "message" else None))
    return entries


def _conversations(runtime, scene_id, viewer_id=None):
    conversations = runtime.conversations(scene_id, viewer_id=viewer_id)
    if viewer_id is not None:
        entries = _visible_entries(runtime, scene_id, viewer_id)
        latest = {e.message.conversation_id: e.seq for e in entries if e.message and e.message.conversation_id}
        conversations = [c.model_copy(update={"last_seq": latest[c.conversation_id]}) for c in conversations]
    return conversations


def _actions(runtime, scene_id, viewer_id=None):
    return [ActionHistoryView(action_id=t["action_id"], actor_id=t["actor_id"], status=t["status"],
        draft=ActionDraft(action=t["action"], text=t["text"] or "", reply_to_message_id=t["reply_to_message_id"],
            requested_speaker_id=t["requested_speaker_id"], recipient_id=t["recipient_id"]) if t["action"] else None,
        failure_kind=t["failure_kind"], created_at=t["created_at"])
        for t in runtime.list_turns(scene_id) if viewer_id is None or t["actor_id"] == viewer_id]


@router.get("/{scene_id}/statistics", response_model=FactStatisticsView)
async def fact_statistics(scene_id: str, request: Request, _: SceneServiceDep, viewer_id: str | None = None):
    runner = _runner(request)
    _check_viewer(runner, scene_id, viewer_id)
    runtime = request.app.state.runtime_repository
    messages = [e.message for e in _visible_entries(runtime, scene_id, viewer_id) if e.message]
    message_ids = {m.message_id for m in messages}
    actions = _actions(runtime, scene_id, viewer_id)
    counts = []
    for agent in runner._scenes.list_agents(scene_id):
        if viewer_id is not None and agent.agent_id != viewer_id:
            continue
        own = [a for a in actions if a.actor_id == agent.agent_id]
        drafts = [a.draft for a in own if a.status == "SUCCEEDED" and a.draft]
        counts.append(RoleActionCountView(agent_id=agent.agent_id, name=agent.name,
            succeeded=len(drafts), public_speaks=sum(d.action == "SPEAK" for d in drafts),
            private_initiations=sum(d.action == "PRIVATE" and d.reply_to_message_id is None for d in drafts),
            private_replies=sum(d.action == "PRIVATE" and d.reply_to_message_id is not None for d in drafts),
            passes=sum(d.action == "PASS" for d in drafts),
            failed=sum(a.status == "FAILED" for a in own), unknown=sum(a.status == "UNKNOWN" for a in own)))
    participants = {m.actor_id for m in messages} | {m.recipient_id for m in messages if m.recipient_id}
    return FactStatisticsView(scene_id=scene_id, viewer_id=viewer_id,
        public_messages=sum(m.visibility is MessageVisibility.PUBLIC for m in messages),
        private_messages=sum(m.visibility is MessageVisibility.PRIVATE for m in messages),
        participant_ids=sorted(participants),
        reply_relations=[ReplyRelationView(message_id=m.message_id, reply_to_message_id=m.reply_to_message_id)
            for m in messages if m.reply_to_message_id in message_ids], role_actions=counts)


@router.get("/{scene_id}/conversations", response_model=ConversationListView)
async def conversations(scene_id: str, request: Request, _: SceneServiceDep,
    viewer_id: str | None = None, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100)):
    _check_viewer(_runner(request), scene_id, viewer_id)
    values = _conversations(request.app.state.runtime_repository, scene_id, viewer_id)
    return ConversationListView(scene_id=scene_id, conversations=values[offset:offset+limit], total=len(values))


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
async def list_events(scene_id: str, request: Request, _: SceneServiceDep, viewer_id: str | None = None) -> list[EventView]:
    """列出全部事件及其状态（界面区分已接受／已生效）。"""

    runner = _runner(request)
    runtime = request.app.state.runtime_repository
    if runner._scenes.get_scene(scene_id) is None:  # noqa: SLF001
        raise DomainNotFoundError(f"场景不存在：{scene_id}")
    _check_viewer(runner, scene_id, viewer_id)
    aliases = {entry.event.event_id: entry.seq for entry in _visible_entries(runtime, scene_id, viewer_id)
        if entry.event} if viewer_id is not None else {}
    return [EventView(event=event.model_copy(update={"seq": aliases.get(event.event_id)})
        if viewer_id is not None else event, status=event.status) for event in runtime.list_events(scene_id)
        if viewer_id is None or is_visible_to(TimelineItem.from_event(event), viewer_id)]


@router.get("/{scene_id}/timeline", response_model=TimelineView)
async def timeline(
    scene_id: str,
    request: Request,
    _: SceneServiceDep,
    since_seq: int = Query(default=0, ge=0),
    viewer_id: str | None = None,
    conversation_id: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int | None = Query(None, ge=1, le=1000),
) -> TimelineView:
    """历史/时间线：**只读**已保存数据，不调用模型（PRD 5.4）。"""

    runner = _runner(request)
    runtime = request.app.state.runtime_repository
    scene = runner._scenes.get_scene(scene_id)  # noqa: SLF001
    if scene is None:
        raise DomainNotFoundError(f"场景不存在：{scene_id}")

    _check_viewer(runner, scene_id, viewer_id)
    all_entries = _visible_entries(runtime, scene_id, viewer_id)
    convs = _conversations(runtime, scene_id, viewer_id)
    if conversation_id is not None and conversation_id not in {c.conversation_id for c in convs}:
        raise DomainNotFoundError("会话不存在")
    entries = [e for e in all_entries if e.seq > since_seq and
        (conversation_id is None or (e.message and e.message.conversation_id == conversation_id))]
    entries = entries[offset:] if limit is None else entries[offset:offset+limit]
    status = _run_status(runner, runtime, scene_id)
    if viewer_id is not None:
        status = status.model_copy(update={"last_committed_seq": len(all_entries), "pending_event_count": 0})
    used = runtime.budget_used(scene_id)
    return TimelineView(
        scene_id=scene_id,
        status=status,
        last_seq=len(all_entries) if viewer_id is not None else runtime.last_seq(scene_id),
        role_requests_used=used["role_requests_used"],
        max_role_requests=scene.budget.max_role_requests,
        analysis_requests_used=used["analysis_requests_used"],
        max_analysis_requests=scene.budget.max_analysis_requests,
        entries=entries,
        conversations=convs,
        actions=_actions(runtime, scene_id, viewer_id),
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
        cutoff_seq=len(context.visible_items),
        public_roster=list(context.public_roster),
        visible_seq=list(range(1, len(context.visible_items)+1)),
        visible_kinds=[item.kind.value for item in context.visible_items],
        prompt=context.prompt,
        prompt_codepoints=len(context.prompt),
        max_prompt_codepoints=runner._prompt_char_limit,
        entries=_visible_entries(request.app.state.runtime_repository, scene_id, agent_id),
        conversations=_conversations(request.app.state.runtime_repository, scene_id, agent_id),
        actions=_actions(request.app.state.runtime_repository, scene_id, agent_id),
    )


@router.get("/{scene_id}/agents/status", response_model=AgentStatusListView)
async def agent_status(
    scene_id: str, request: Request, _: SceneServiceDep, viewer_id: str | None = None
) -> AgentStatusListView:
    """每个本场角色的执行状态（PRD 7.1：角色卡只显示名称与执行状态）。

    只读观察：不调用模型，不产生任何剧情事实。
    """

    runner = _runner(request)
    runtime = request.app.state.runtime_repository
    scene = runner._scenes.get_scene(scene_id)  # noqa: SLF001
    if scene is None:
        raise DomainNotFoundError(f"场景不存在：{scene_id}")

    _check_viewer(runner, scene_id, viewer_id)
    agents = runner._scenes.list_agents(scene_id)  # noqa: SLF001
    cursors = {cursor.agent_id: cursor for cursor in runtime.list_cursors(scene_id)}
    messages = runtime.list_messages(scene_id)
    speak_counts: dict[str, int] = {}
    for message in messages:
        if message.visibility is not MessageVisibility.PUBLIC:
            continue
        speak_counts[message.actor_id] = speak_counts.get(message.actor_id, 0) + 1

    # “当前待回应对象”：时间线上最新一条发言的点名（与调度窗口一致）。
    requested: str | None = None
    if messages:
        latest = max(messages, key=lambda item: item.seq)
        requested = latest.recipient_id or latest.requested_speaker_id
        if requested:
            from ..scheduling import SchedulerState
            scheduling_state = SchedulerState(scene=runner.snapshot(scene_id), cursors=tuple(cursors.values()),
                consecutive_requested_priority=runtime.requested_priority_streak(scene_id))
            if (scheduling_state.consecutive_requested_priority >= 2
                or not runner._scheduler.is_candidate(scheduling_state, requested)
                or (scene.chat_policy_version == 2 and cursors.get(requested)
                    and cursors[requested].processed_seq >= latest.seq)):
                requested = None

    actions = _actions(runtime, scene_id, viewer_id)
    def latest_for(actor, success=False):
        return next((a for a in reversed(actions) if a.actor_id == actor and (not success or a.status == "SUCCEEDED")), None)
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
                    (sum(i.seq <= cursors[agent.agent_id].processed_seq for i in runner.viewpoint(scene_id, agent.agent_id)[1].visible_items) if viewer_id is not None else cursors[agent.agent_id].processed_seq) if agent.agent_id in cursors else 0
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
                is_requested=requested == agent.agent_id if viewer_id is None else False,
                generating=bool(latest_for(agent.agent_id) and latest_for(agent.agent_id).status == "PENDING"),
                last_failure_kind=latest_for(agent.agent_id).failure_kind if latest_for(agent.agent_id) else None,
                last_successful_draft=latest_for(agent.agent_id, True).draft if latest_for(agent.agent_id, True) else None,
                speak_count=speak_counts.get(agent.agent_id, 0),
                prompt_codepoints=len(runner.viewpoint(scene_id, agent.agent_id)[1].prompt),
                max_prompt_codepoints=runner._prompt_char_limit,
            )
            for agent in agents if viewer_id is None or agent.agent_id == viewer_id
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
