"""行为分析只读接口（PRD 6.1、6.2、5.3）。

分析是**独立观察**：这些接口不改变剧情、不改变运行状态、不触发调度。
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from ..analysis import AnalysisService
from ..contracts import AnalysisReport
from ..contracts.api_analysis import (
    AnalysisCapabilityView,
    AnalysisCreateRequest,
    AnalysisListView,
    AnalysisRecordView,
)
from ..domain import DomainNotFoundError
from .deps import SceneServiceDep, get_analysis_service

router = APIRouter(prefix="/api/scenes", tags=["m06-analysis"])


def _service(request: Request) -> AnalysisService:
    return get_analysis_service(request)


def _record_view(record: dict) -> AnalysisRecordView:
    return AnalysisRecordView(
        analysis_id=record["analysis_id"],
        scene_id=record["scene_id"],
        agent_id=record["agent_id"],
        status=record["status"].value,
        provider_attempts=record["provider_attempts"],
        degradation_flags=record["degradation_flags"],
        error=record["error"],
        created_at=record["created_at"].isoformat(),
        material_seqs=record["material_seqs"],
        materials=record["materials"],
        behavior_description=record["behavior_description"],
        context=record["context"],
        report=record["report"],
    )


@router.post("/{scene_id}/analyses", response_model=AnalysisRecordView, status_code=201)
async def create_analysis(
    scene_id: str,
    payload: AnalysisCreateRequest,
    request: Request,
    _: SceneServiceDep,
) -> AnalysisRecordView:
    """执行一次分析。

    结果有三种“没有真正调用模型”的可能：`BLOCKED`（本地边界规则，含超长与预算耗尽）、
    `DISABLED`（能力关闭或外部包不可用）；两者 `provider_attempts=0`。
    """

    service = _service(request)
    outcome = await service.analyze(
        scene_id, agent_id=payload.agent_id, material_seqs=tuple(payload.material_seqs)
    )
    record = service.get_record(outcome.analysis_id)
    if record is None:  # pragma: no cover - 刚写入的记录不会消失
        raise DomainNotFoundError(f"分析记录不存在：{outcome.analysis_id}")
    return _record_view(record)


@router.get("/{scene_id}/analyses", response_model=AnalysisListView)
async def list_analyses(
    scene_id: str,
    request: Request,
    _: SceneServiceDep,
    agent_id: str | None = Query(default=None),
) -> AnalysisListView:
    """列出分析记录，并把操作数与实际模型请求数分开呈现（PRD 5.3）。"""

    service = _service(request)
    records = service.list_records(scene_id, agent_id=agent_id)
    runner = request.app.state.scene_runner
    scene = runner._scenes.get_scene(scene_id)  # noqa: SLF001 - 只读
    if scene is None:
        raise DomainNotFoundError(f"场景不存在：{scene_id}")

    used = request.app.state.runtime_repository.budget_used(scene_id)["analysis_requests_used"]
    return AnalysisListView(
        scene_id=scene_id,
        capability=service.capability(),
        operations_total=len(records),
        provider_attempts_total=sum(record["provider_attempts"] for record in records),
        analysis_requests_used=used,
        max_analysis_requests=scene.budget.max_analysis_requests,
        records=[_record_view(record) for record in records],
    )


@router.get("/{scene_id}/analyses/capability", response_model=AnalysisCapabilityView)
async def analysis_capability(
    scene_id: str, request: Request, _: SceneServiceDep
) -> AnalysisCapabilityView:
    """分析能力是否可用，以及不可用的具体原因。"""

    service = _service(request)
    runner = request.app.state.scene_runner
    if runner._scenes.get_scene(scene_id) is None:  # noqa: SLF001
        raise DomainNotFoundError(f"场景不存在：{scene_id}")
    return AnalysisCapabilityView(scene_id=scene_id, capability=service.capability())


__all__ = ["AnalysisReport", "router"]
