"""行为分析端口（PRD 6.2）。

本模块是**唯一**允许导入外部分析仓库（``behavior-psychology-v2.0`` 的 ``src``
包）的位置。M00 不导入任何外部包：默认实现 :class:`DisabledAnalysisPort` 在
关闭分析能力时**不要求外部包已安装**（PRD 6.2 / 6.2 依赖可选性）。

真实受控客户端与外部仓库适配属于 M06。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..contracts import (
    AnalysisCapability,
    AnalysisReport,
    AnalysisRequest,
    AnalysisStatus,
    Usage,
)

DISCLAIMER = (
    "本结果仅用于解释虚构角色的文本行为，不构成对真实人物的心理测量或预测；"
    "不得当作经过校准的事实概率使用。"
)


@runtime_checkable
class AnalysisPort(Protocol):
    """行为分析外部端口。分析失败或受限**不得**影响聊天。"""

    @property
    def enabled(self) -> bool:
        """能力是否开启。关闭时不得导入或要求外部包。"""
        ...

    async def analyze(self, request: AnalysisRequest) -> AnalysisReport:
        """返回带状态的分析结果；不得把降级结果当成成功。"""
        ...


class DisabledAnalysisPort:
    """默认实现：分析能力关闭。

    不导入任何外部包，不需要外部依赖已安装；被调用时返回 ``DISABLED`` 且
    ``provider_attempts=0``（本地边界拦截不计模型请求，PRD 5.3）。
    """

    def __init__(self, reason: str = "分析能力未开启") -> None:
        self._reason = reason

    @property
    def enabled(self) -> bool:
        return False

    @property
    def capability(self) -> AnalysisCapability:
        return AnalysisCapability(enabled=False, external_package_installed=False, reason=self._reason)

    async def analyze(self, request: AnalysisRequest) -> AnalysisReport:
        return AnalysisReport(
            status=AnalysisStatus.DISABLED,
            scene_id=request.scene_id,
            agent_id=request.agent_id,
            provider_attempts=0,
            degradation_flags=["analysis_disabled"],
            error=None,
        )


class MockAnalysisPort:
    """确定性假分析实现：不联网、不需要密钥、不导入外部包。

    返回 ``NORMAL`` 且包含至少两种替代解释与免责声明；如需测试降级路径，用
    ``status``／``degradation_flags`` 显式构造，不伪装成成功。
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        status: AnalysisStatus = AnalysisStatus.NORMAL,
        degradation_flags: tuple[str, ...] = (),
        usage: Usage | None = None,
        error: str | None = None,
    ) -> None:
        self._enabled = enabled
        self._status = status
        self._degradation_flags = list(degradation_flags)
        self._usage = usage
        self._error = error
        self.calls: list[AnalysisRequest] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def call_count(self) -> int:
        return len(self.calls)

    async def analyze(self, request: AnalysisRequest) -> AnalysisReport:
        self.calls.append(request)
        if not self._enabled:
            return AnalysisReport(
                status=AnalysisStatus.DISABLED,
                scene_id=request.scene_id,
                agent_id=request.agent_id,
                provider_attempts=0,
                degradation_flags=["analysis_disabled"],
            )

        if self._status is AnalysisStatus.DISABLED:
            raise ValueError("MockAnalysisPort 在 enabled=True 时不能返回 DISABLED")

        if self._status is AnalysisStatus.BLOCKED:
            return AnalysisReport(
                status=AnalysisStatus.BLOCKED,
                scene_id=request.scene_id,
                agent_id=request.agent_id,
                provider_attempts=0,
                degradation_flags=["local_boundary_rule"],
            )

        if self._status is AnalysisStatus.FAILED:
            return AnalysisReport(
                status=AnalysisStatus.FAILED,
                scene_id=request.scene_id,
                agent_id=request.agent_id,
                provider_attempts=max(request.provider_attempts, 1),
                degradation_flags=list(self._degradation_flags) or ["provider_error"],
                error=self._error or "mock failure",
            )

        return AnalysisReport(
            status=self._status,
            scene_id=request.scene_id,
            agent_id=request.agent_id,
            behavior_labels=["示例行为标签（Mock）"],
            mechanisms=["示例机制（Mock）"],
            alternative_explanations=["替代解释一（Mock）", "替代解释二（Mock）"],
            limitations=["Mock 结果不代表真实模型输出"],
            disclaimer=DISCLAIMER,
            degradation_flags=list(self._degradation_flags),
            provider_attempts=max(request.provider_attempts, 1),
            usage=self._usage if self._usage is not None else Usage(),
        )


def load_analysis_port(*, enabled: bool, reason: str | None = None) -> AnalysisPort:
    """按配置返回分析端口（M06 起接入外部仓库）。

    - ``enabled=False``：返回 :class:`DisabledAnalysisPort`，**不导入**任何外部包
      （PRD 6.2：禁用分析时不得要求外部包已安装）；
    - ``enabled=True``：尝试加载外部分析器；导入失败时仍返回
      :class:`DisabledAnalysisPort`，但带上**具体失败原因**（含原始错误文本），
      绝不伪装成可用，也绝不让聊天因此中断。
    """

    if not enabled:
        return DisabledAnalysisPort(reason=reason or "分析能力未开启")

    try:
        from ..analysis.external import ExternalAnalysisPort, load_external_analyzer
        from ..analysis.controlled_client import ControlledAnalysisClient

        client = ControlledAnalysisClient()
        analyzer = load_external_analyzer(client=client)
        return ExternalAnalysisPort(analyzer=analyzer, client=client)
    except Exception as exc:  # noqa: BLE001 - 外部包缺失是预期情形
        return DisabledAnalysisPort(
            reason=reason
            or f"已开启分析能力，但外部分析仓库不可用：{exc.__class__.__name__}: {exc}"
        )
