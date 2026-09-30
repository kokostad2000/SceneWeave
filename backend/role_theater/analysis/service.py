"""分析服务（PRD 6.1、6.2、5.3）。

职责：边界规则 → 能力判定 → 预算 → 调用 → 五状态报告 → 记录（按场景／角色隔离）。

硬性不变量：

1. 被本地边界规则拦截时**不发起任何调用**，且 `provider_attempts=0`（PRD 5.3）；
2. 分析结果**不进入角色上下文、不改变人设、不触发调度**（PRD 6.1）；
3. 分析的任何失败都不影响聊天：调用方拿到的永远是一个 `AnalysisReport`；
4. `persist_profile` 强制 `false`（PRD 6.2）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from ..contracts import (
    AnalysisCapability,
    AnalysisReport,
    AnalysisRequest,
    AnalysisStatus,
    PauseReason,
    RunState,
    Usage,
)
from ..context import SceneSnapshot, TimelineItem
from ..ports import AnalysisPort, DisabledAnalysisPort
from ..storage import AnalysisRepository, RuntimeRepository, SceneRepository
from .boundary import BoundaryDecision, evaluate_selection


@dataclass(frozen=True, slots=True)
class AnalysisOutcome:
    """一次分析操作的结果（记录 + 报告）。"""

    analysis_id: str
    status: AnalysisStatus
    report: AnalysisReport
    provider_attempts: int
    operations_total: int
    error: str | None = None


class AnalysisService:
    """只读分析：不改剧情、不改状态、不改人设。"""

    def __init__(
        self,
        *,
        scenes: SceneRepository,
        runtime: RuntimeRepository,
        repository: AnalysisRepository,
        port_factory: Callable[[], AnalysisPort],
        snapshot_provider: Callable[[str], SceneSnapshot],
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._scenes = scenes
        self._runtime = runtime
        self._repository = repository
        self._port_factory = port_factory
        self._snapshot = snapshot_provider
        self._clock = clock or (lambda: datetime.now(UTC))
        self._new_id = id_factory or (lambda: uuid4().hex)

    # --- 能力 ---

    def capability(self) -> AnalysisCapability:
        port = self._port_factory()
        enabled = getattr(port, "enabled", False)
        reason = None
        capability = getattr(port, "capability", None)
        if capability is not None:
            reason = capability.reason
        elif not enabled:
            reason = getattr(port, "reason", None)
        return AnalysisCapability(
            enabled=bool(enabled),
            external_package_installed=(
                capability.external_package_installed if capability is not None else bool(enabled)
            ),
            reason=reason,
        )

    # --- 分析 ---

    async def analyze(
        self, scene_id: str, *, agent_id: str, material_seqs: tuple[int, ...]
    ) -> AnalysisOutcome:
        from ..domain import DomainNotFoundError

        scene = self._scenes.get_scene(scene_id)
        if scene is None:
            raise DomainNotFoundError(f"场景不存在：{scene_id}")
        agent = self._scenes.get_agent(scene_id, agent_id)
        if agent is None:
            raise DomainNotFoundError(f"本场角色不存在：{agent_id}")

        snapshot = self._snapshot(scene_id)
        decision = evaluate_selection(
            timeline=snapshot.timeline,
            agent_id=agent_id,
            agent_name=agent.name,
            selected_seqs=material_seqs,
        )

        if not decision.allowed:
            return self._record_blocked(scene_id, agent_id, decision, material_seqs)

        # 分析预算：与实际发送挂钩（本地拦截不占预算，PRD 5.3）。
        used = self._runtime.budget_used(scene_id)["analysis_requests_used"]
        if used >= scene.budget.max_analysis_requests:
            return self._record_blocked(
                scene_id,
                agent_id,
                BoundaryDecision(
                    allowed=False,
                    reason="analysis_budget_exhausted",
                    detail=(
                        f"本场分析请求已用尽（{used}／{scene.budget.max_analysis_requests}）；"
                        "新增分析不会发起模型请求"
                    ),
                    behavior_description=decision.behavior_description,
                    context=decision.context,
                    materials=decision.materials,
                    flags=("analysis_budget_exhausted",),
                ),
                material_seqs,
            )

        port = self._port_factory()
        if not getattr(port, "enabled", False):
            return self._record_disabled(scene_id, agent_id, decision, port, material_seqs)

        request = AnalysisRequest(
            scene_id=scene_id,
            agent_id=agent_id,
            behavior_description=decision.behavior_description,
            context=decision.context,
            materials=list(decision.materials),
            persist_profile=False,
            provider_attempts=1,
        )

        precheck = getattr(port, "precheck", None)
        if precheck is not None:
            try:
                reason = precheck(request)
            except Exception as exc:  # noqa: BLE001 - 边界检查异常不能影响聊天
                report = AnalysisReport(
                    status=AnalysisStatus.FAILED,
                    scene_id=scene_id,
                    agent_id=agent_id,
                    provider_attempts=0,
                    error=f"分析边界检查失败：{exc.__class__.__name__}",
                    degradation_flags=["boundary_exception"],
                )
                return self._record(scene_id, agent_id, decision, report, material_seqs)
            if reason is not None:
                return self._record_blocked(
                    scene_id, agent_id,
                    BoundaryDecision(
                        allowed=False, reason="external_boundary",
                        detail=reason,
                        behavior_description=decision.behavior_description,
                        context=decision.context,
                        materials=decision.materials,
                        flags=("external_boundary",),
                    ),
                    material_seqs,
                )

        # 一旦真正发送就占用一次分析预算，失败不退款。
        self._runtime.bump_budget(scene_id, analysis_requests=1)

        report = await self._safe_analyze(port, request)
        if decision.flags and not report.degradation_flags:
            report = report.model_copy(update={"degradation_flags": list(decision.flags)})
        elif decision.flags:
            report = report.model_copy(
                update={"degradation_flags": sorted(set(report.degradation_flags) | set(decision.flags))}
            )

        return self._record(scene_id, agent_id, decision, report, material_seqs)

    async def _safe_analyze(self, port: AnalysisPort, request: AnalysisRequest) -> AnalysisReport:
        """分析的任何失败都变成报告，绝不向调用方抛异常（PRD 6.1）。"""

        try:
            return await port.analyze(request)
        except Exception as exc:  # noqa: BLE001 - 兜底：分析失败不得影响聊天
            return AnalysisReport(
                status=AnalysisStatus.FAILED,
                scene_id=request.scene_id,
                agent_id=request.agent_id,
                provider_attempts=request.provider_attempts,
                usage=Usage(),
                error=f"分析调用异常：{exc.__class__.__name__}: {exc}",
                degradation_flags=["provider_exception"],
            )

    # --- 记录 ---

    def _record_blocked(
        self,
        scene_id: str,
        agent_id: str,
        decision: BoundaryDecision,
        material_seqs: tuple[int, ...],
    ) -> AnalysisOutcome:
        report = AnalysisReport(
            status=AnalysisStatus.BLOCKED,
            scene_id=scene_id,
            agent_id=agent_id,
            provider_attempts=0,
            degradation_flags=list(decision.flags) or ["local_boundary_rule"],
            error=decision.detail,
        )
        return self._record(scene_id, agent_id, decision, report, material_seqs, error=decision.detail)

    def _record_disabled(
        self,
        scene_id: str,
        agent_id: str,
        decision: BoundaryDecision,
        port: AnalysisPort,
        material_seqs: tuple[int, ...],
    ) -> AnalysisOutcome:
        capability = getattr(port, "capability", None)
        reason = getattr(capability, "reason", None) or "分析能力未开启"
        report = AnalysisReport(
            status=AnalysisStatus.DISABLED,
            scene_id=scene_id,
            agent_id=agent_id,
            provider_attempts=0,
            degradation_flags=["analysis_disabled"],
            error=reason,
        )
        return self._record(scene_id, agent_id, decision, report, material_seqs, error=reason)

    def _record(
        self,
        scene_id: str,
        agent_id: str,
        decision: BoundaryDecision,
        report: AnalysisReport,
        material_seqs: tuple[int, ...],
        *,
        error: str | None = None,
    ) -> AnalysisOutcome:
        analysis_id = f"ana_{self._new_id()}"
        self._repository.insert(
            analysis_id=analysis_id,
            scene_id=scene_id,
            agent_id=agent_id,
            report=report,
            materials=[material.model_dump(mode="json") for material in decision.materials],
            material_seqs=list(material_seqs),
            behavior_description=decision.behavior_description,
            context=decision.context,
            created_at=self._clock(),
            error=error,
        )
        return AnalysisOutcome(
            analysis_id=analysis_id,
            status=report.status,
            report=report,
            provider_attempts=report.provider_attempts,
            operations_total=self._repository.count_operations(scene_id),
            error=error or report.error,
        )

    # --- 只读 ---

    def list_records(self, scene_id: str, *, agent_id: str | None = None) -> list[dict]:
        from ..domain import DomainNotFoundError

        if self._scenes.get_scene(scene_id) is None:
            raise DomainNotFoundError(f"场景不存在：{scene_id}")
        return self._repository.list_for_scene(scene_id, agent_id=agent_id)

    def get_record(self, analysis_id: str) -> dict | None:
        return self._repository.get(analysis_id)

    def operations_total(self, scene_id: str) -> int:
        return self._repository.count_operations(scene_id)

    def scene_state_unchanged(self, scene_id: str) -> bool:
        """自检辅助：分析不应改变运行状态（PRD 6.1）。"""

        scene = self._scenes.get_scene(scene_id)
        return scene is not None and scene.status in set(RunState) and scene.pause_reason in (
            None,
            PauseReason.MANUAL,
            PauseReason.NO_NEW_INFORMATION,
            PauseReason.COLLECTIVE_SILENCE,
            PauseReason.PROVIDER_ERROR,
            PauseReason.CONTEXT_LIMIT,
            PauseReason.PROCESS_INTERRUPT,
        )


def build_disabled_port(reason: str) -> DisabledAnalysisPort:
    return DisabledAnalysisPort(reason=reason)


__all__ = ["AnalysisOutcome", "AnalysisService", "TimelineItem", "build_disabled_port"]
