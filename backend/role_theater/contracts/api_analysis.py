"""M06 行为分析请求／响应契约（PRD 6.1、6.2）。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .analysis import AnalysisCapability, AnalysisReport
from .ids import AgentId, AnalysisId, SceneId


class AnalysisCreateRequest(BaseModel):
    """请求分析：选定一名本场角色与若干**已提交公开材料**的序号。"""

    model_config = ConfigDict(extra="forbid")

    agent_id: AgentId
    material_seqs: list[int] = Field(default_factory=list, max_length=200)


class AnalysisRecordView(BaseModel):
    """一条分析记录（含报告与计数，界面据此区分五状态）。"""

    model_config = ConfigDict(extra="forbid")

    analysis_id: AnalysisId
    scene_id: SceneId
    agent_id: AgentId
    status: str
    provider_attempts: int = Field(ge=0)
    degradation_flags: list[str] = Field(default_factory=list)
    error: str | None = None
    created_at: str
    material_seqs: list[int] = Field(default_factory=list)
    #: 送出的材料原文（保留来源），供操作者核对到底送了什么。
    materials: list[dict] = Field(default_factory=list)
    behavior_description: str = ""
    context: str = ""
    report: AnalysisReport


class AnalysisListView(BaseModel):
    """分析记录列表 + **分开呈现**的操作数与实际模型请求数（PRD 5.3）。"""

    model_config = ConfigDict(extra="forbid")

    scene_id: SceneId
    capability: AnalysisCapability
    operations_total: int = Field(ge=0)
    provider_attempts_total: int = Field(ge=0)
    analysis_requests_used: int = Field(ge=0)
    max_analysis_requests: int = Field(ge=0)
    records: list[AnalysisRecordView]


class AnalysisCapabilityView(BaseModel):
    """分析能力状态（供界面决定是否可用与如何解释）。"""

    model_config = ConfigDict(extra="forbid")

    scene_id: SceneId
    capability: AnalysisCapability
