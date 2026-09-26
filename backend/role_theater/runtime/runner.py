"""SceneRunner：状态机、单步／自动运行、预算、事件排序与恢复（PRD 4.3、5.1～5.4）。

关键不变量：

1. **每场同一时刻只有一个在途角色请求**（由 ``_in_flight`` + 每场景锁保证）；
2. **先落盘、再通知**：数据库是事实来源，SSE 只按 ``seq`` 补发已提交数据；
3. **模型网络等待期间不持有写事务**：``PENDING`` 写入与结果写入是各自的短事务；
4. **只有成功行动推进已处理位置**，失败不推进（PRD 5.1）；
5. **发送即占用预算**，失败／超时不退款；未派发的调用不占用（PRD 5.3）；
6. **结束请求后拒绝新事件**，但已接受事件仍在调用边界顺序落盘（PRD 4.3）。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import uuid4

from ..contracts import (
    MAX_PROMPT_CHARS,
    ActionType,
    CommandAck,
    ControlCommandType,
    Event,
    EventStatus,
    EventSubmission,
    Message,
    ModelActionRequest,
    ModelFailureKind,
    ModelParams,
    PauseReason,
    ReferenceScope,
    RoleCursor,
    RunState,
    TurnStatus,
)
from ..context import ContextBuilder, ContextLimitExceeded, SceneSnapshot, agent_profile_views
from ..context.models import TimelineItem
from ..storage import Database, RuntimeRepository, SceneRepository
from ..scheduling import Scheduler, SchedulerState
from .broadcaster import Broadcaster
from .state_machine import assert_transition, can_transition

#: `_ack` 构造响应时的占位 request_id；真正的值由 `_store_command` 填入。
_PENDING_REQUEST_ID = "pending"

#: 未派发（不占用预算）的失败分类（PRD 5.3）。
NOT_DISPATCHED_KINDS = frozenset(
    {
        ModelFailureKind.CONTEXT_LIMIT,
        ModelFailureKind.MISSING_CONFIG,
        ModelFailureKind.NOT_DISPATCHED,
    }
)


@dataclass(frozen=True, slots=True)
class StepResult:
    """一次角色请求的结果摘要（供测试与报告使用）。"""

    actor_id: str | None
    action: str | None
    message_id: str | None
    status: TurnStatus | None
    failure_kind: ModelFailureKind | None
    run_state: RunState
    pause_reason: PauseReason | None
    budget_used: int


def utcnow() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)


class SceneRunner:
    """单进程内所有场景的运行器。"""

    def __init__(
        self,
        *,
        database: Database,
        scenes: SceneRepository,
        runtime: RuntimeRepository,
        model_port,
        scheduler: Scheduler | None = None,
        context_builder: ContextBuilder | None = None,
        broadcaster: Broadcaster | None = None,
        clock: Callable[[], datetime] = utcnow,
        id_factory: Callable[[], str] | None = None,
        loop_timeout_seconds: float = 300.0,
        prompt_char_limit: int = MAX_PROMPT_CHARS,
        model_params: ModelParams | None = None,
    ) -> None:
        self._db = database
        self._scenes = scenes
        self._runtime = runtime
        self._model = model_port
        self._scheduler = scheduler or Scheduler()
        self._builder = context_builder or ContextBuilder()
        self._broadcaster = broadcaster or Broadcaster()
        self._clock = clock
        self._new_id = id_factory or (lambda: uuid4().hex)
        self._loop_timeout_seconds = loop_timeout_seconds
        #: 应用侧保守字符上限（PRD 5.3）：超过则暂停，不截断。可注入以便测试。
        self._prompt_char_limit = prompt_char_limit
        #: 运行参数（含模型名）。由配置注入，因此 SCENEWEAVE_MODEL_NAME 真正生效。
        self._model_params = model_params or ModelParams()

        self._tasks: dict[str, asyncio.Task] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._in_flight: dict[str, bool] = {}
        self._stop_requested: dict[str, bool] = {}
        self._pause_requested: dict[str, bool] = {}
        #: 统计每个场景的实际模型调用次数（测试与报告用；不是业务状态）。
        self._call_counts: dict[str, int] = {}

    # --- 只读辅助 ---

    @property
    def broadcaster(self) -> Broadcaster:
        return self._broadcaster

    def call_count(self, scene_id: str) -> int:
        return self._call_counts.get(scene_id, 0)

    def is_busy(self, scene_id: str) -> bool:
        task = self._tasks.get(scene_id)
        return bool(self._in_flight.get(scene_id)) or (task is not None and not task.done())

    def _lock(self, scene_id: str) -> asyncio.Lock:
        return self._locks.setdefault(scene_id, asyncio.Lock())

    # --- 快照 ---

    def snapshot(self, scene_id: str) -> SceneSnapshot:
        """从数据库构建 M02 的纯数据快照（只用**已生效**事件）。"""

        scene = self._scenes.get_scene(scene_id)
        if scene is None:
            raise KeyError(scene_id)
        agents = self._scenes.list_agents(scene_id)
        names = {agent.agent_id: agent.name for agent in agents}

        timeline: list[TimelineItem] = []
        for message in self._runtime.list_messages(scene_id):
            timeline.append(TimelineItem.from_message(message, author_name=names.get(message.actor_id)))
        for event in self._runtime.list_events(scene_id, status=EventStatus.EFFECTIVE):
            timeline.append(TimelineItem.from_event(event))

        return SceneSnapshot(
            scene_id=scene_id,
            background=scene.background,
            agents=agent_profile_views(agents),
            timeline=tuple(timeline),
        )

    def viewpoint(self, scene_id: str, agent_id: str) -> tuple[SceneSnapshot, object]:
        """角色视角：返回**与调用器完全相同**的构建结果（PRD 7.2）。"""

        snapshot = self.snapshot(scene_id)
        return snapshot, self._builder.build(snapshot, agent_id)

    # --- 命令入口 ---

    async def run_command(
        self, scene_id: str, *, request_id: str, command: ControlCommandType
    ) -> CommandAck:
        """执行控制命令；同一 ``request_id`` 重复提交返回既有结果（PRD 5.4）。"""

        existing = self._runtime.get_command(request_id)
        if existing is not None:
            ack = CommandAck.model_validate_json(existing["response_json"])
            return ack.model_copy(update={"deduplicated": True})

        scene = self._require_scene(scene_id)
        current = scene.status
        now = self._clock()

        if current is RunState.ENDED:
            if command is ControlCommandType.STOP:
                ack = self._ack(scene_id, command, accepted=True, detail="会话已结束")
            else:
                ack = self._ack(
                    scene_id,
                    command,
                    accepted=False,
                    detail="会话已结束，不可恢复运行；重新开始请创建新会话",
                    override_state=RunState.ENDED,
                )
            return self._store_command(scene_id, request_id, command, ack, now)

        if command is ControlCommandType.START:
            ack = await self._handle_start(scene_id, current, now)
        elif command is ControlCommandType.STEP:
            ack = await self._handle_step(scene_id, current)
        elif command is ControlCommandType.PAUSE:
            ack = await self._handle_pause(scene_id, current)
        elif command is ControlCommandType.RESUME:
            ack = await self._handle_resume(scene_id, current, now)
        else:  # STOP
            ack = await self._handle_stop(scene_id, current, now)

        return self._store_command(scene_id, request_id, command, ack, now)

    async def inject_event(
        self, scene_id: str, *, request_id: str, submission: EventSubmission
    ) -> CommandAck:
        """提交人工事件（PRD 4.3）。"""

        existing = self._runtime.get_command(request_id)
        if existing is not None:
            ack = CommandAck.model_validate_json(existing["response_json"])
            return ack.model_copy(update={"deduplicated": True})

        scene = self._require_scene(scene_id)
        now = self._clock()

        if scene.status is RunState.ENDED or self._stop_requested.get(scene_id):
            ack = self._ack(
                scene_id,
                None,
                accepted=False,
                detail="结束请求之后不再接受新事件",
                override_state=scene.status,
            )
            return self._store_command(scene_id, request_id, None, ack, now)

        in_flight = bool(self._in_flight.get(scene_id))
        status = EventStatus.ACCEPTED if in_flight else EventStatus.EFFECTIVE
        event = Event(
            event_id=f"evt_{self._new_id()}",
            scene_id=scene_id,
            # 调用进行中先接受、不占序号；到调用边界生效时再分配（§3.7 I6）。
            seq=None if in_flight else self._runtime.next_seq(scene_id),
            body=submission.body,
            visibility=submission.visibility,
            target_agent_id=submission.target_agent_id,
            status=status,
            accepted_at=now,
            effective_at=None if status is EventStatus.ACCEPTED else now,
        )
        self._runtime.insert_event(event, accepted_order=self._runtime.next_accepted_order(scene_id))
        # 先落盘、再通知（PRD 5.4）。
        self._broadcaster.notify(scene_id)

        ack = self._ack(
            scene_id,
            None,
            accepted=True,
            detail="事件已接受，将在当前调用边界生效" if in_flight else "事件已生效",
            override_state=scene.status,
            event_id=event.event_id,
            event_status=status.value,
        )
        return self._store_command(scene_id, request_id, None, ack, now)

    async def wait_until_idle(self, scene_id: str, timeout: float | None = None) -> bool:
        """等待后台循环停下（测试、关闭与运维使用）。"""

        task = self._tasks.get(scene_id)
        if task is None or task.done():
            return True
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=timeout or self._loop_timeout_seconds)
        except (TimeoutError, asyncio.TimeoutError):
            return False
        return True

    async def shutdown(self) -> None:
        """取消所有后台循环（进程退出用；不改变数据库状态）。"""

        for scene_id, task in list(self._tasks.items()):
            self._stop_requested[scene_id] = True
            task.cancel()
        for task in list(self._tasks.values()):
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - 关闭时忽略
                pass
        self._tasks.clear()

    def recover_after_restart(self) -> list[str]:
        """进程重启恢复（PRD 5.4）：残留 `PENDING` → `UNKNOWN`，场景暂停。"""

        scene_ids = self._runtime.mark_pending_turns_unknown()
        for scene_id in scene_ids:
            if self._scenes.get_scene(scene_id) is None:  # pragma: no cover - 级联删除后不会出现
                continue
            self._runtime.set_scene_state(
                scene_id, status=RunState.PAUSED, pause_reason=PauseReason.PROCESS_INTERRUPT
            )
        return scene_ids

    # --- 命令实现 ---

    async def _handle_start(self, scene_id: str, current: RunState, now: datetime) -> CommandAck:
        if current in (RunState.RUNNING, RunState.PAUSING):
            return self._ack(scene_id, ControlCommandType.START, accepted=True, detail="已在运行")
        if not can_transition(current, RunState.RUNNING):
            return self._ack(
                scene_id,
                ControlCommandType.START,
                accepted=False,
                detail=f"当前状态 {current.value} 不能开始",
                override_state=current,
            )

        # 首次实际角色请求开始后锁定本场背景与人物设定（PRD 3.2）。
        self._scenes.lock_scene(scene_id, now)
        assert_transition(current, RunState.RUNNING)
        self._runtime.set_scene_state(scene_id, status=RunState.RUNNING, started_at=now)
        self._stop_requested[scene_id] = False
        self._pause_requested[scene_id] = False
        self._spawn_loop(scene_id)
        return self._ack(scene_id, ControlCommandType.START, accepted=True, override_state=RunState.RUNNING)

    async def _handle_step(self, scene_id: str, current: RunState) -> CommandAck:
        if current is RunState.RUNNING or self.is_busy(scene_id):
            return self._ack(
                scene_id,
                ControlCommandType.STEP,
                accepted=False,
                detail="已有调用在执行；单步需在暂停状态下进行",
                override_state=current,
            )
        if not can_transition(current, RunState.RUNNING):
            return self._ack(
                scene_id,
                ControlCommandType.STEP,
                accepted=False,
                detail=f"当前状态 {current.value} 不能单步",
                override_state=current,
            )

        now = self._clock()
        self._scenes.lock_scene(scene_id, now)
        self._runtime.set_scene_state(scene_id, status=RunState.RUNNING, started_at=now)
        result = await self._execute_one(scene_id, allow_pause=True)

        # 单步只执行一次角色请求，**完成后暂停**（PRD 5.2）；不保证产生发言。
        if result.run_state is RunState.RUNNING:
            self._pause(scene_id, PauseReason.MANUAL)
            result = replace(result, run_state=RunState.PAUSED, pause_reason=PauseReason.MANUAL)

        return self._ack(
            scene_id,
            ControlCommandType.STEP,
            accepted=True,
            detail=None if result.actor_id is not None else "没有候选角色",
            override_state=result.run_state,
            pause_reason=result.pause_reason,
        )

    async def _handle_pause(self, scene_id: str, current: RunState) -> CommandAck:
        if current is RunState.PAUSED:
            return self._ack(scene_id, ControlCommandType.PAUSE, accepted=True, detail="已暂停")
        if current is RunState.READY:
            self._runtime.set_scene_state(
                scene_id, status=RunState.PAUSED, pause_reason=PauseReason.MANUAL
            )
            return self._ack(
                scene_id,
                ControlCommandType.PAUSE,
                accepted=True,
                override_state=RunState.PAUSED,
                pause_reason=PauseReason.MANUAL,
            )
        if not can_transition(current, RunState.PAUSING):
            return self._ack(
                scene_id,
                ControlCommandType.PAUSE,
                accepted=False,
                detail=f"当前状态 {current.value} 不能暂停",
                override_state=current,
            )

        self._pause_requested[scene_id] = True
        if self._in_flight.get(scene_id):
            # 在途调用后由循环在调用边界转入 PAUSED。
            self._runtime.set_scene_state(scene_id, status=RunState.PAUSING)
            return self._ack(
                scene_id,
                ControlCommandType.PAUSE,
                accepted=True,
                detail="将在当前调用结束时暂停",
                override_state=RunState.PAUSING,
            )

        self._runtime.set_scene_state(
            scene_id, status=RunState.PAUSED, pause_reason=PauseReason.MANUAL
        )
        return self._ack(
            scene_id,
            ControlCommandType.PAUSE,
            accepted=True,
            override_state=RunState.PAUSED,
            pause_reason=PauseReason.MANUAL,
        )

    async def _handle_resume(
        self, scene_id: str, current: RunState, now: datetime
    ) -> CommandAck:
        if current is RunState.RUNNING:
            return self._ack(scene_id, ControlCommandType.RESUME, accepted=True, detail="已在运行")
        if not can_transition(current, RunState.RUNNING):
            return self._ack(
                scene_id,
                ControlCommandType.RESUME,
                accepted=False,
                detail=f"当前状态 {current.value} 不能继续",
                override_state=current,
            )

        # 恢复边界：先处理尚未生效的已接受事件，再允许新的角色请求（PRD 5.4）。
        self._activate_pending_events(scene_id)

        self._pause_requested[scene_id] = False
        self._stop_requested[scene_id] = False
        self._runtime.set_scene_state(scene_id, status=RunState.RUNNING, started_at=now)
        self._spawn_loop(scene_id)
        return self._ack(
            scene_id, ControlCommandType.RESUME, accepted=True, override_state=RunState.RUNNING
        )

    async def _handle_stop(self, scene_id: str, current: RunState, now: datetime) -> CommandAck:
        if current is RunState.ENDED:
            return self._ack(scene_id, ControlCommandType.STOP, accepted=True, detail="已结束")

        self._stop_requested[scene_id] = True
        self._pause_requested[scene_id] = False

        if self._in_flight.get(scene_id):
            self._runtime.set_scene_state(scene_id, status=RunState.STOPPING)
            return self._ack(
                scene_id,
                ControlCommandType.STOP,
                accepted=True,
                detail="将在当前调用结束时结束",
                override_state=RunState.STOPPING,
            )

        self._finalize_stop(scene_id, now)
        return self._ack(
            scene_id, ControlCommandType.STOP, accepted=True, override_state=RunState.ENDED
        )

    def _finalize_stop(self, scene_id: str, now: datetime) -> None:
        """在调用边界结束：先把已接受事件顺序落盘，再进入 ENDED（PRD 4.3）。"""

        self._activate_pending_events(scene_id)
        self._runtime.set_scene_state(
            scene_id, status=RunState.ENDED, pause_reason=None, ended_at=now
        )
        self._broadcaster.notify(scene_id)

    # --- 循环 ---

    def _spawn_loop(self, scene_id: str) -> None:
        task = self._tasks.get(scene_id)
        if task is not None and not task.done():
            return
        self._tasks[scene_id] = asyncio.create_task(self._run_loop(scene_id))

    async def _run_loop(self, scene_id: str) -> None:
        """自动运行：每轮在调用边界检查停止标志（PRD 5.2）。"""

        try:
            while True:
                scene = self._scenes.get_scene(scene_id)
                if scene is None or scene.status is RunState.ENDED:
                    return

                if self._stop_requested.get(scene_id):
                    self._finalize_stop(scene_id, self._clock())
                    return

                if self._pause_requested.get(scene_id):
                    self._runtime.set_scene_state(
                        scene_id, status=RunState.PAUSED, pause_reason=PauseReason.MANUAL
                    )
                    self._broadcaster.notify(scene_id)
                    return

                result = await self._execute_one(scene_id, allow_pause=True)
                if result.run_state in (RunState.PAUSED, RunState.ENDED):
                    return
        except asyncio.CancelledError:  # pragma: no cover - 关闭时
            raise
        except Exception as exc:  # noqa: BLE001 - 意外错误必须暂停而不是静默崩溃
            self._runtime.set_scene_state(
                scene_id, status=RunState.PAUSED, pause_reason=PauseReason.PROVIDER_ERROR
            )
            self._broadcaster.notify(scene_id)
            self._last_error = exc  # 便于测试定位

    # --- 单次调用 ---

    async def _execute_one(self, scene_id: str, *, allow_pause: bool) -> StepResult:
        """执行一次角色请求（调用者保证当前没有在途调用）。"""

        async with self._lock(scene_id):
            self._in_flight[scene_id] = True
            try:
                result = await self._execute_locked(scene_id, allow_pause=allow_pause)
            finally:
                self._in_flight[scene_id] = False

            # 调用边界：结束请求优先收尾（PRD 5.2／4.3）。
            if self._stop_requested.get(scene_id):
                self._finalize_stop(scene_id, self._clock())
                result = replace(result, run_state=RunState.ENDED, pause_reason=None)
            return result

    async def _execute_locked(self, scene_id: str, *, allow_pause: bool) -> StepResult:
        scene = self._scenes.get_scene(scene_id)
        if scene is None:  # pragma: no cover - 调用前已校验
            raise KeyError(scene_id)

        used = self._runtime.budget_used(scene_id)["role_requests_used"]
        limit = scene.budget.max_role_requests
        if used >= limit:
            self._runtime.set_scene_state(scene_id, status=RunState.ENDED, ended_at=self._clock())
            self._broadcaster.notify(scene_id)
            return self._result(scene_id, RunState.ENDED, None, used)

        snapshot = self.snapshot(scene_id)
        cursors = tuple(self._runtime.list_cursors(scene_id))
        priority_used = max(
            (cursor.consecutive_requested_priority for cursor in cursors), default=0
        )
        state = SchedulerState(
            scene=snapshot, cursors=cursors, consecutive_requested_priority=priority_used
        )
        outcome = self._scheduler.select(state)

        if outcome.actor_id is None:
            # 候选为空 → 暂停，原因“无新信息”，**不是**会话结束（PRD 5.1）。
            self._pause(scene_id, PauseReason.NO_NEW_INFORMATION if allow_pause else PauseReason.MANUAL)
            return self._result(
                scene_id, RunState.PAUSED, PauseReason.NO_NEW_INFORMATION, used, actor_id=None
            )

        actor_id = outcome.actor_id
        context = self._builder.build(snapshot, actor_id)
        try:
            self._builder.assert_within_limits(context, limit=self._prompt_char_limit)
        except ContextLimitExceeded as exc:
            # 上下文超限：暂停而不是截断，且**不占用预算**（PRD 5.3）。
            self._pause(scene_id, PauseReason.CONTEXT_LIMIT)
            return self._result(
                scene_id,
                RunState.PAUSED,
                PauseReason.CONTEXT_LIMIT,
                used,
                actor_id=actor_id,
                failure_kind=ModelFailureKind.CONTEXT_LIMIT,
                detail=str(exc),
            )

        now = self._clock()
        attempt_id = f"att_{self._new_id()}"
        turn_id = f"turn_{self._new_id()}"
        action_id = f"act_{self._new_id()}"

        # 派发前先写 PENDING：占用预算 + 标记在途 + 崩溃恢复依据（tasks/M04.md §3.7 I2）。
        self._runtime.insert_turn(
            action_id=action_id,
            turn_id=turn_id,
            attempt_id=attempt_id,
            scene_id=scene_id,
            actor_id=actor_id,
            input_cursor_seq=outcome.based_on_seq,
            prompt_template_id=context.prompt_template_id,
            created_at=now,
        )
        self._runtime.bump_budget(scene_id, role_requests=1)
        self._call_counts[scene_id] = self._call_counts.get(scene_id, 0) + 1

        # 引用范围：本场已提交且该角色可见的公开发言 + 本场其他有效角色（PRD 4.2）。
        references = ReferenceScope(
            actor_id=actor_id,
            allowed_message_ids=[
                message.message_id
                for message in self._runtime.list_messages(scene_id)
                if message.seq <= outcome.based_on_seq
            ],
            allowed_speaker_ids=[
                agent.agent_id for agent in snapshot.ordered_agents if agent.agent_id != actor_id
            ],
        )
        request = ModelActionRequest(
            scene_id=scene_id,
            actor_id=actor_id,
            prompt_template_id=context.prompt_template_id,
            prompt=context.prompt,
            cursor_seq=outcome.based_on_seq,
            params=self._model_params,
            references=references,
        )

        response = await self._model.generate_action(request)

        if response.ok and response.draft is not None:
            return self._commit_success(
                scene_id=scene_id,
                actor_id=actor_id,
                attempt_id=attempt_id,
                response=response,
                outcome=outcome,
                now=now,
            )

        failure = response.failure
        kind = failure.kind if failure is not None else ModelFailureKind.PROVIDER_ERROR
        not_dispatched = (not response.sent) and kind in NOT_DISPATCHED_KINDS
        if not_dispatched:
            # 没有产生模型请求 → 不占用预算（PRD 5.3）。
            self._runtime.refund_budget(attempt_id, scene_id)

        status = TurnStatus.UNKNOWN if kind is ModelFailureKind.UNKNOWN_REQUEST else TurnStatus.FAILED
        self._runtime.finish_turn(
            attempt_id,
            status=status,
            finished_at=self._clock(),
            failure_kind=kind.value,
            failure_detail=failure.detail if failure else "",
            sent=response.sent,
            budget_consumed=not not_dispatched,
            requested_model=response.requested_model,
            returned_model=response.returned_model,
            provider_request_id=response.provider_request_id,
            usage=response.usage,
            latency_ms=response.latency_ms,
        )

        pause_reason = (
            PauseReason.CONTEXT_LIMIT
            if kind is ModelFailureKind.CONTEXT_LIMIT
            else PauseReason.PROVIDER_ERROR
        )
        self._pause(scene_id, pause_reason)
        self._activate_pending_events(scene_id)
        used_after = self._runtime.budget_used(scene_id)["role_requests_used"]
        return self._result(
            scene_id,
            RunState.PAUSED,
            pause_reason,
            used_after,
            actor_id=actor_id,
            status=status,
            failure_kind=kind,
            detail=failure.detail if failure else None,
        )

    def _commit_success(
        self,
        *,
        scene_id: str,
        actor_id: str,
        attempt_id: str,
        response,
        outcome,
        now: datetime,
    ) -> StepResult:
        draft = response.draft
        message_id: str | None = None

        if draft.action is ActionType.SPEAK:
            # 先分配 seq 并落盘消息，再更新行动行（一次短事务一次）。
            seq = self._runtime.next_seq(scene_id)
            message = Message(
                message_id=f"msg_{self._new_id()}",
                scene_id=scene_id,
                seq=seq,
                actor_id=actor_id,
                text=draft.text,
                reply_to_message_id=draft.reply_to_message_id,
                requested_speaker_id=draft.requested_speaker_id,
                created_at=now,
            )
            self._runtime.insert_message(message)
            message_id = message.message_id

        self._runtime.finish_turn(
            attempt_id,
            status=TurnStatus.SUCCEEDED,
            finished_at=self._clock(),
            action=draft.action.value,
            text=draft.text,
            reply_to_message_id=draft.reply_to_message_id,
            requested_speaker_id=draft.requested_speaker_id,
            message_id=message_id,
            requested_model=response.requested_model,
            returned_model=response.returned_model,
            provider_request_id=response.provider_request_id,
            usage=response.usage,
            sent=response.sent,
            latency_ms=response.latency_ms,
        )

        # 只有成功的 SPEAK／PASS 才推进已处理位置，且**只推进到输入快照**，
        # 避免把提交之后出现的新事件误标为已处理（PRD 5.1）。
        previous = self._runtime.get_cursor(scene_id, actor_id)
        priority = previous.consecutive_requested_priority if previous else 0
        from ..contracts import SchedulerReason

        if outcome.reason is SchedulerReason.REQUESTED_SPEAKER_PRIORITY:
            priority = min(priority + 1, 2)
        else:
            priority = 0

        self._runtime.upsert_cursor(
            RoleCursor(
                scene_id=scene_id,
                agent_id=actor_id,
                processed_seq=outcome.based_on_seq,
                startup_opportunity_consumed=True,
                last_action_at=now,
                last_action_status=TurnStatus.SUCCEEDED,
                consecutive_requested_priority=priority,
            )
        )

        # 提交后再处理待生效事件并通知订阅者（先记录、后推送）。
        self._activate_pending_events(scene_id)
        self._broadcaster.notify(scene_id)

        used = self._runtime.budget_used(scene_id)["role_requests_used"]
        scene = self._scenes.get_scene(scene_id)
        state = scene.status if scene is not None else RunState.RUNNING
        return StepResult(
            actor_id=actor_id,
            action=draft.action.value,
            message_id=message_id,
            status=TurnStatus.SUCCEEDED,
            failure_kind=None,
            run_state=state,
            pause_reason=None,
            budget_used=used,
        )

    # --- 事件与状态辅助 ---

    def _activate_pending_events(self, scene_id: str) -> list[str]:
        """按接受顺序把待生效事件转为已生效（PRD 4.3）。"""

        activated: list[str] = []
        now = self._clock()
        for event in self._runtime.list_pending_events(scene_id):
            # 按接受顺序分配序号 → 时间线顺序 = 生效顺序（PRD 4.3）。
            self._runtime.mark_event_effective(
                event.event_id, now, self._runtime.next_seq(scene_id)
            )
            activated.append(event.event_id)
        if activated:
            self._broadcaster.notify(scene_id)
        return activated

    def _pause(self, scene_id: str, reason: PauseReason) -> None:
        self._runtime.set_scene_state(scene_id, status=RunState.PAUSED, pause_reason=reason)
        self._broadcaster.notify(scene_id)

    def _result(
        self,
        scene_id: str,
        state: RunState,
        pause_reason: PauseReason | None,
        budget_used: int,
        *,
        actor_id: str | None = None,
        status: TurnStatus | None = None,
        failure_kind: ModelFailureKind | None = None,
        detail: str | None = None,
        message_id: str | None = None,
        action: str | None = None,
    ) -> StepResult:
        del detail  # 细节已写入 scene_turns
        return StepResult(
            actor_id=actor_id,
            action=action,
            message_id=message_id,
            status=status,
            failure_kind=failure_kind,
            run_state=state,
            pause_reason=pause_reason,
            budget_used=budget_used,
        )

    def _require_scene(self, scene_id: str):
        from ..domain import DomainNotFoundError

        scene = self._scenes.get_scene(scene_id)
        if scene is None:
            raise DomainNotFoundError(f"场景不存在：{scene_id}")
        return scene

    def _ack(
        self,
        scene_id: str,
        command: ControlCommandType | None,
        *,
        accepted: bool,
        detail: str | None = None,
        override_state: RunState | None = None,
        pause_reason: PauseReason | None = None,
        event_id: str | None = None,
        event_status: str | None = None,
    ) -> CommandAck:
        scene = self._scenes.get_scene(scene_id)
        state = override_state or (scene.status if scene is not None else RunState.READY)
        if pause_reason is None and scene is not None and state is RunState.PAUSED:
            pause_reason = scene.pause_reason
        # request_id 由 _store_command 统一填充（_ack 的所有返回值都会经过它）。
        return CommandAck(
            request_id=_PENDING_REQUEST_ID,
            command=command,
            accepted=accepted,
            deduplicated=False,
            run_state=state,
            pause_reason=pause_reason,
            event_id=event_id,
            event_status=event_status,
            detail=detail,
        )

    def _store_command(
        self,
        scene_id: str,
        request_id: str,
        command: ControlCommandType | None,
        ack: CommandAck,
        now: datetime,
    ) -> CommandAck:
        stored = ack.model_copy(update={"request_id": request_id})
        self._runtime.store_command(
            request_id=request_id,
            scene_id=scene_id,
            command=command.value if command else "INJECT_EVENT",
            response_json=stored.model_dump_json(),
            created_at=now,
        )
        return stored


__all__ = ["NOT_DISPATCHED_KINDS", "SceneRunner", "StepResult", "utcnow"]
