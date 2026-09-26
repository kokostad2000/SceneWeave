"""场景与本场角色路由（PRD 3.1、3.2、5.3）。

M01 只提供配置期接口：创建场景、创建预置场景、查看、增删改本场角色。
运行控制（start／step／pause／resume／stop）、事件与 SSE 属于 M04。
"""

from __future__ import annotations

from fastapi import APIRouter, status

from ..contracts import SceneAgent
from ..contracts.api import (
    AgentCreateRequest,
    AgentRenameRequest,
    PresetListView,
    PresetSceneCreateRequest,
    PresetSummaryView,
    SceneCreateRequest,
    SceneDetailView,
    SceneListView,
    SceneSummaryView,
)
from ..domain import AgentSpec, SceneDetail, SceneService
from ..presets import PRESET_SCENES
from .deps import SceneServiceDep

router = APIRouter(prefix="/api/scenes", tags=["m01-scenes"])


def _detail_view(detail: SceneDetail) -> SceneDetailView:
    return SceneDetailView(
        scene=detail.scene,
        agents=list(detail.agents),
        locked=detail.locked,
    )


@router.get("/presets", response_model=PresetListView)
def list_presets() -> PresetListView:
    """列出可用预置场景。属于配置期只读数据，不调用模型。"""

    return PresetListView(
        presets=[
            PresetSummaryView(
                key=preset.key,
                title=preset.title,
                background=preset.background,
                agent_names=[agent.name for agent in preset.agents],
            )
            for preset in PRESET_SCENES.values()
        ]
    )


@router.post("", response_model=SceneDetailView, status_code=status.HTTP_201_CREATED)
def create_scene(payload: SceneCreateRequest, service: SceneServiceDep) -> SceneDetailView:
    detail = service.create(
        title=payload.title,
        background=payload.background,
        agent_specs=[
            AgentSpec(template_id=spec.template_id, name=spec.name) for spec in payload.agents
        ],
        max_role_requests=payload.max_role_requests,
        max_analysis_requests=payload.max_analysis_requests,
    )
    return _detail_view(detail)


@router.post("/preset", response_model=SceneDetailView, status_code=status.HTTP_201_CREATED)
def create_preset_scene(
    payload: PresetSceneCreateRequest,
    service: SceneServiceDep,
) -> SceneDetailView:
    """用预置“三个室友的客厅”创建会话（PRD 3.1）。"""

    return _detail_view(service.create_preset(payload.preset_key))


@router.get("", response_model=SceneListView)
def list_scenes(service: SceneServiceDep) -> SceneListView:
    return SceneListView(
        scenes=[
            SceneSummaryView(
                scene_id=summary.scene.scene_id,
                title=summary.scene.title,
                status=summary.scene.status.value,
                agent_count=summary.agent_count,
                budget_locked=summary.scene.budget.locked_at is not None,
                created_at=summary.scene.created_at.isoformat(),
            )
            for summary in service.list_summaries()
        ]
    )


@router.get("/{scene_id}", response_model=SceneDetailView)
def get_scene(scene_id: str, service: SceneServiceDep) -> SceneDetailView:
    return _detail_view(service.get_detail(scene_id))


@router.post(
    "/{scene_id}/agents",
    response_model=SceneAgent,
    status_code=status.HTTP_201_CREATED,
)
def add_agent(
    scene_id: str,
    payload: AgentCreateRequest,
    service: SceneServiceDep,
) -> SceneAgent:
    return service.add_agent(scene_id, template_id=payload.template_id, name=payload.name)


@router.patch("/{scene_id}/agents/{agent_id}", response_model=SceneAgent)
def rename_agent(
    scene_id: str,
    agent_id: str,
    payload: AgentRenameRequest,
    service: SceneServiceDep,
) -> SceneAgent:
    return service.rename_agent(scene_id, agent_id, payload.name)


@router.delete("/{scene_id}/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_agent(scene_id: str, agent_id: str, service: SceneServiceDep) -> None:
    service.remove_agent(scene_id, agent_id)
