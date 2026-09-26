"""行为分析端口契约（PRD 6.1、6.2）。

首版通过 :class:`AnalysisPort` 调用外部仓库；M00 只定义结构，不安装、不导入
外部包，也不发起真实分析调用。强制 ``persist_profile=false``：分析记录由本
项目按 ``scene_id``／``agent_id`` 隔离。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import AnalysisStatus
from .ids import AgentId, MessageId, SceneId
from .limits import (
    MAX_ANALYSIS_BEHAVIOR_DESCRIPTION_CODEPOINTS,
    MAX_ANALYSIS_CONTEXT_CODEPOINTS,
    MAX_ANALYSIS_MATERIAL_ITEMS,
    codepoint_length,
)
from .model import Usage

MIN_ALTERNATIVE_EXPLANATIONS = 2


class AnalysisMaterialRef(BaseModel):
    """选中的公开材料引用：保留原文、来源角色与消息 ID（PRD 6.1）。

    默认不送出任何私有背景或定向事件。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str = Field(pattern="^(message|event)$")
    source_id: str = Field(min_length=1)
    author_agent_id: AgentId | None = None
    text: str


class AnalysisRequest(BaseModel):
    """送交行为分析的材料。

    ``behavior_description`` 与 ``context`` 各自最多 4000 字符；超限时提示
    缩小选择，**不静默截断、不自动总结**（PRD 6.1）。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    scene_id: SceneId
    agent_id: AgentId
    behavior_description: str
    context: str = ""
    materials: list[AnalysisMaterialRef] = Field(default_factory=list)
    persist_profile: bool = False
    provider_attempts: int = Field(default=0, ge=0, le=1)

    @model_validator(mode="after")
    def _check(self) -> AnalysisRequest:
        if self.persist_profile:
            raise ValueError("persist_profile 必须为 false；分析记录由本项目按场景隔离")
        if codepoint_length(self.behavior_description) > MAX_ANALYSIS_BEHAVIOR_DESCRIPTION_CODEPOINTS:
            raise ValueError(
                f"behavior_description 不能超过 {MAX_ANALYSIS_BEHAVIOR_DESCRIPTION_CODEPOINTS} 个 Unicode 码点"
            )
        if codepoint_length(self.context) > MAX_ANALYSIS_CONTEXT_CODEPOINTS:
            raise ValueError(
                f"context 不能超过 {MAX_ANALYSIS_CONTEXT_CODEPOINTS} 个 Unicode 码点"
            )
        if len(self.materials) > MAX_ANALYSIS_MATERIAL_ITEMS:
            raise ValueError(f"选中材料最多 {MAX_ANALYSIS_MATERIAL_ITEMS} 条")
        return self


class AnalysisReport(BaseModel):
    """分析结果。

    必须区分 normal／blocked／degraded／failed／disabled 五种状态；保留
    ``degradation_flags``，不把返回 JSON 当成分析成功（PRD 6.2）。结果不进入
    角色记忆、不改变人设、不触发调度。
    """

    model_config = ConfigDict(extra="forbid")

    status: AnalysisStatus
    scene_id: SceneId | None = None
    agent_id: AgentId | None = None
    behavior_labels: list[str] = Field(default_factory=list)
    mechanisms: list[str] = Field(default_factory=list)
    alternative_explanations: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    disclaimer: str = ""
    degradation_flags: list[str] = Field(default_factory=list)
    provider_attempts: int = Field(default=0, ge=0)
    usage: Usage = Field(default_factory=Usage)
    error: str | None = None

    @model_validator(mode="after")
    def _check(self) -> AnalysisReport:
        if self.status in (AnalysisStatus.BLOCKED, AnalysisStatus.DISABLED):
            if self.provider_attempts != 0:
                raise ValueError(
                    "被本地边界规则拦截或能力关闭时 provider_attempts 必须为 0"
                )
        if self.status in (AnalysisStatus.NORMAL, AnalysisStatus.DEGRADED):
            if len(self.alternative_explanations) < MIN_ALTERNATIVE_EXPLANATIONS:
                raise ValueError(
                    f"结果必须给出至少 {MIN_ALTERNATIVE_EXPLANATIONS} 种替代解释"
                )
            if not self.disclaimer:
                raise ValueError("结果必须包含免责声明")
        if self.status is AnalysisStatus.FAILED and not self.error:
            raise ValueError("FAILED 必须给出 error 说明")
        return self


class AnalysisCapability(BaseModel):
    """分析能力开关状态，用于健康检查与界面提示。"""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    external_package_installed: bool = False
    reason: str | None = None
