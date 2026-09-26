"""M01 请求／响应契约（角色模板与场景）。

新增契约模型必须同时登记到 :mod:`role_theater.contracts.registry`，否则前端
无法生成对应类型（PRD 第 8 节）。

约定：

- 请求模型 ``extra="forbid"``，未知字段直接 422，而不是被静默忽略；
- 长度一律按 Unicode 码点校验，空白先裁剪后校验（PRD 3.3）；
- ``*UpdateRequest`` 中 ``None`` 表示**不修改该字段**；要清空可选文本请传空字符串。
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from .ids import SceneId, TemplateId
from .limits import (
    MAX_AGENTS_PER_SCENE,
    MAX_AGENT_NAME_CODEPOINTS,
    MAX_ANALYSIS_REQUESTS_PER_SCENE,
    MAX_ROLE_REQUESTS_PER_SCENE,
    MAX_SCENE_BACKGROUND_CODEPOINTS,
    MAX_SCENE_REQUEST_LIMIT,
    MIN_AGENTS_PER_SCENE,
    MIN_SCENE_REQUEST_LIMIT,
)
from .scene import AgentProfileFields, AgentTemplate, Scene, SceneAgent

AgentName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_AGENT_NAME_CODEPOINTS,
    ),
]

SceneTitle = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
]

SceneBackground = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=MAX_SCENE_BACKGROUND_CODEPOINTS),
]


class TemplateCreateRequest(AgentProfileFields):
    """创建角色模板。"""

    model_config = ConfigDict(extra="forbid")


class TemplateUpdateRequest(BaseModel):
    """编辑角色模板（部分字段）。``None`` 表示不修改。"""

    model_config = ConfigDict(extra="forbid")

    name: AgentName | None = None
    persona: str | None = None
    speech_style: str | None = None
    initial_goal: str | None = None
    private_background: str | None = None


class TemplateCopyRequest(BaseModel):
    """复制角色模板；省略 ``name`` 时自动取第一个可用的不重复名称。"""

    model_config = ConfigDict(extra="forbid")

    name: AgentName | None = None


class TemplateListView(BaseModel):
    """模板列表。"""

    model_config = ConfigDict(extra="forbid")

    templates: list[AgentTemplate]


class AgentSpecRequest(BaseModel):
    """创建场景时对一名本场角色的要求。"""

    model_config = ConfigDict(extra="forbid")

    template_id: TemplateId
    name: AgentName | None = None


class SceneCreateRequest(BaseModel):
    """创建场景（会话）。

    ``agents`` 的 2～8 人约束在契约层即校验，因此越界请求得到 422 而不是
    进入业务层（PRD 1.2、9）。
    """

    model_config = ConfigDict(extra="forbid")

    title: SceneTitle
    background: SceneBackground = ""
    agents: list[AgentSpecRequest] = Field(
        min_length=MIN_AGENTS_PER_SCENE,
        max_length=MAX_AGENTS_PER_SCENE,
    )
    max_role_requests: int | None = Field(
        default=None, ge=MIN_SCENE_REQUEST_LIMIT, le=MAX_SCENE_REQUEST_LIMIT
    )
    max_analysis_requests: int | None = Field(
        default=None, ge=MIN_SCENE_REQUEST_LIMIT, le=MAX_SCENE_REQUEST_LIMIT
    )


class PresetSceneCreateRequest(BaseModel):
    """用预置场景创建会话。"""

    model_config = ConfigDict(extra="forbid")

    preset_key: str = Field(default="roommates", min_length=1, max_length=64)


class PresetSummaryView(BaseModel):
    """预置场景摘要（供界面展示与测试核对）。"""

    model_config = ConfigDict(extra="forbid")

    key: str
    title: str
    background: str
    agent_names: list[str]


class PresetListView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    presets: list[PresetSummaryView]


class SceneSummaryView(BaseModel):
    """场景列表项。"""

    model_config = ConfigDict(extra="forbid")

    scene_id: SceneId
    title: str
    status: str
    agent_count: int = Field(ge=0)
    budget_locked: bool
    created_at: str


class SceneListView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenes: list[SceneSummaryView]


class SceneDetailView(BaseModel):
    """场景详情：场景 + 本场角色集合（含模板快照）。"""

    model_config = ConfigDict(extra="forbid")

    scene: Scene
    agents: list[SceneAgent]
    locked: bool


class AgentCreateRequest(BaseModel):
    """由模板新增一名本场角色。"""

    model_config = ConfigDict(extra="forbid")

    template_id: TemplateId
    name: AgentName | None = None


class AgentRenameRequest(BaseModel):
    """重命名本场角色（显示名称）。"""

    model_config = ConfigDict(extra="forbid")

    name: AgentName


# 预算默认值再次导出，便于前端展示“默认 200／4”（PRD 5.3；默认值经人工裁决调整）。
DEFAULT_ROLE_REQUEST_LIMIT = MAX_ROLE_REQUESTS_PER_SCENE
DEFAULT_ANALYSIS_REQUEST_LIMIT = MAX_ANALYSIS_REQUESTS_PER_SCENE
