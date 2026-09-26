"""契约模型登记表（PRD 第 8 节：后端是接口唯一来源）。

M01～M06 的路由尚未建立时，行动、事件、端口等模型不会自动出现在 OpenAPI 文档
中。为了让前端可以一次性生成**完整**契约类型，这里把契约模型集中登记，并由
``role_theater.main`` 在生成 OpenAPI 时把这些模型的 JSON Schema 合并进
``components.schemas``。

新增契约模型必须登记在此，否则前端无法生成对应类型。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .action import ActionDraft, ActionRecord
from .analysis import (
    AnalysisCapability,
    AnalysisMaterialRef,
    AnalysisReport,
    AnalysisRequest,
)
from .api_analysis import (
    AnalysisCapabilityView,
    AnalysisCreateRequest,
    AnalysisListView,
    AnalysisRecordView,
)
from .api_runtime import (
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
from .api import (
    AgentCreateRequest,
    AgentRenameRequest,
    AgentSpecRequest,
    PresetListView,
    PresetSceneCreateRequest,
    PresetSummaryView,
    SceneCreateRequest,
    SceneDetailView,
    SceneListView,
    SceneSummaryView,
    TemplateCopyRequest,
    TemplateCreateRequest,
    TemplateListView,
    TemplateUpdateRequest,
)
from .common import (
    CONTRACT_ENUMS,
    ApiError,
    ContractSummary,
    EnumSummary,
    HealthResponse,
)
from .event import Event, EventSubmission
from .model import (
    ModelActionRequest,
    ModelActionResponse,
    ModelFailure,
    ModelParams,
    ReferenceScope,
    Usage,
)
from .runtime import (
    CommandAck,
    ControlCommand,
    InjectEventCommand,
    RoleCursor,
    RunStatus as RunStatusSnapshot,
    SchedulerDirective,
    TimelineEntry,
)
from .scene import (
    AgentProfileFields,
    AgentSnapshot,
    AgentTemplate,
    Budget,
    BudgetUsage,
    Message,
    Scene,
    SceneAgent,
)

#: 全部契约模型（含请求／响应与端口结构）。
CONTRACT_MODELS: dict[str, type[BaseModel]] = {
    # 角色 / 场景 / 消息
    "AgentProfileFields": AgentProfileFields,
    "AgentTemplate": AgentTemplate,
    "AgentSnapshot": AgentSnapshot,
    "SceneAgent": SceneAgent,
    "Scene": Scene,
    "Message": Message,
    "Budget": Budget,
    "BudgetUsage": BudgetUsage,
    # 行动与事件
    "ActionDraft": ActionDraft,
    "ActionRecord": ActionRecord,
    "EventSubmission": EventSubmission,
    "Event": Event,
    # 运行控制
    "ControlCommand": ControlCommand,
    "InjectEventCommand": InjectEventCommand,
    "CommandAck": CommandAck,
    "RoleCursor": RoleCursor,
    "SchedulerDirective": SchedulerDirective,
    "RunStatus": RunStatusSnapshot,
    "TimelineEntry": TimelineEntry,
    # 模型端口
    "Usage": Usage,
    "ModelParams": ModelParams,
    "ModelActionRequest": ModelActionRequest,
    "ModelFailure": ModelFailure,
    "ModelActionResponse": ModelActionResponse,
    "ReferenceScope": ReferenceScope,
    # 分析端口
    "AnalysisMaterialRef": AnalysisMaterialRef,
    "AnalysisRequest": AnalysisRequest,
    "AnalysisReport": AnalysisReport,
    "AnalysisCapability": AnalysisCapability,
    # 通用
    "ApiError": ApiError,
    "EnumSummary": EnumSummary,
    "ContractSummary": ContractSummary,
    "HealthResponse": HealthResponse,
    # M01 角色模板与场景配置请求／响应
    "TemplateCreateRequest": TemplateCreateRequest,
    "TemplateUpdateRequest": TemplateUpdateRequest,
    "TemplateCopyRequest": TemplateCopyRequest,
    "TemplateListView": TemplateListView,
    "AgentSpecRequest": AgentSpecRequest,
    "SceneCreateRequest": SceneCreateRequest,
    "PresetSceneCreateRequest": PresetSceneCreateRequest,
    "PresetSummaryView": PresetSummaryView,
    "PresetListView": PresetListView,
    "SceneSummaryView": SceneSummaryView,
    "SceneListView": SceneListView,
    "SceneDetailView": SceneDetailView,
    "AgentCreateRequest": AgentCreateRequest,
    "AgentRenameRequest": AgentRenameRequest,
    # M04 运行与观察
    "ControlCommandRequest": ControlCommandRequest,
    "InjectEventRequest": InjectEventRequest,
    "TimelineEntryView": TimelineEntryView,
    "TimelineView": TimelineView,
    "ViewpointView": ViewpointView,
    "RunStateView": RunStateView,
    "EventView": EventView,
    "ScenarioSummaryView": ScenarioSummaryView,
    "AgentStatusView": AgentStatusView,
    "AgentStatusListView": AgentStatusListView,
    # M06 行为分析
    "AnalysisCreateRequest": AnalysisCreateRequest,
    "AnalysisRecordView": AnalysisRecordView,
    "AnalysisListView": AnalysisListView,
    "AnalysisCapabilityView": AnalysisCapabilityView,
}


def contract_json_schemas() -> dict[str, dict[str, Any]]:
    """返回全部契约模型的 JSON Schema（键为组件名）。

    嵌套模型与枚举会被提升到同一层，保证引用（``#/components/schemas/...``）可解析。
    """

    schemas: dict[str, dict[str, Any]] = {}
    for name in sorted(CONTRACT_MODELS):
        schema = CONTRACT_MODELS[name].model_json_schema(
            ref_template="#/components/schemas/{model}"
        )
        definitions = schema.pop("$defs", {})
        for definition_name in sorted(definitions):
            schemas.setdefault(definition_name, definitions[definition_name])
        schemas.setdefault(name, schema)
    # 枚举通过被模型引用出现在 $defs 中，无需单独生成。
    return schemas
