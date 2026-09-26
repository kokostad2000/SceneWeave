"""外部分析仓库适配层（PRD 6.2）。

**本模块是唯一允许导入外部 `behavior-psychology-v2.0` 代码的位置。**

未验证项（不得据项目名或历史对话臆造后声称为已验证）：

* U-M06-1：外部仓库的模块路径与类名。PRD 只给出
  ``BehaviorAnalyzer.analyze(AnalysisRequest)`` 这一异步接口与结构化响应，
  因此这里把模块路径、类名与字段名集中成常量，**默认值待真实联调核对**。
* U-M06-2：结构化响应的具体字段名（行为标签／机制／替代解释／局限／降级标记）。
  这里用 ``getattr`` 容错读取，**缺字段一律降级**，绝不猜成成功。
* U-M06-3：受控客户端与外部分析器的兼容性（供应商接口差异）。

外部包不可导入时：返回 ``DISABLED`` 并带上原始错误文本，**不抛异常、不影响聊天**；
禁用分析时**不导入**任何外部包。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..contracts import (
    AnalysisReport,
    AnalysisRequest,
    AnalysisStatus,
    Usage,
)
from ..contracts.analysis import MIN_ALTERNATIVE_EXPLANATIONS
from .controlled_client import ControlledAnalysisClient

#: 外部仓库导入位置（**待真实联调核对**，见 U-M06-1）。
DEFAULT_ANALYZER_MODULE = "src.behavior_psychology.analyzer"
DEFAULT_ANALYZER_CLASS = "BehaviorAnalyzer"
DEFAULT_REQUEST_CLASS = "AnalysisRequest"
DEFAULT_ANALYSIS_REQUEST_CLASS = "AnalysisRequest"

DISCLAIMER = (
    "本结果仅用于解释虚构角色的文本行为，不构成对真实人物的心理测量或预测；"
    "不得当作经过校准的事实概率使用。"
)

#: 外部结果中被视为“降级标记”的字段（任一非空即判降级，见 U-M06-2）。
DEGRADATION_FIELDS = (
    "degradation_flags",
    "degradation",
    "warnings",
    "degraded",
    "fallback",
    "is_fallback",
)
LABEL_FIELDS = ("behavior_labels", "behavior_tags", "labels", "behaviors")
MECHANISM_FIELDS = ("mechanisms", "possible_mechanisms", "mechanism")
ALTERNATIVE_FIELDS = (
    "alternative_explanations",
    "alternatives",
    "alternative_interpretations",
)
LIMITATION_FIELDS = ("limitations", "limits", "caveats")


class ExternalAnalysisUnavailable(RuntimeError):
    """外部分析仓库不可用（未安装或导入失败）。"""


def _first_attr(source: Any, names: tuple[str, ...]) -> Any:
    for name in names:
        if isinstance(source, dict) and name in source:
            return source[name]
        value = getattr(source, name, None)
        if value:
            return value
    return None


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, dict):
        return [f"{key}：{item}" for key, item in value.items()]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


class ExternalAnalysisPort:
    """通过外部仓库执行分析。

    ``analyzer_factory`` 由 :func:`load_external_analyzer` 提供；测试可注入假实现，
    因此本类的状态映射逻辑可以在**没有外部包**的环境下被完整测试。
    """

    def __init__(
        self,
        *,
        analyzer: Any,
        client: ControlledAnalysisClient | None = None,
    ) -> None:
        self._analyzer = analyzer
        self._client = client or ControlledAnalysisClient()

    @property
    def enabled(self) -> bool:
        return True

    @property
    def client(self) -> ControlledAnalysisClient:
        return self._client

    async def analyze(self, request: AnalysisRequest) -> AnalysisReport:
        if request.persist_profile:  # pragma: no cover - 契约层已强制
            raise ValueError("persist_profile 必须为 false（PRD 6.2）")

        # 强制关闭画像写入：即使外部默认开启也不允许。
        payload = request.model_copy(update={"persist_profile": False})

        try:
            raw = await self._invoke(payload)
        except Exception as exc:  # noqa: BLE001 - 任何外部异常都必须变成 FAILED
            return AnalysisReport(
                status=AnalysisStatus.FAILED,
                scene_id=request.scene_id,
                agent_id=request.agent_id,
                provider_attempts=max(self._client.provider_attempts, 1),
                usage=self._client.usage,
                error=f"外部分析调用失败：{exc.__class__.__name__}: {exc}",
                degradation_flags=["provider_exception"],
            )

        return self._to_report(raw, request)

    async def _invoke(self, request: AnalysisRequest) -> Any:
        result = self._analyzer.analyze(request)
        if hasattr(result, "__await__"):
            return await result
        return result

    def _to_report(self, raw: Any, request: AnalysisRequest) -> AnalysisReport:
        """把外部结构化响应映射为契约报告；缺项与降级标记一律判 ``DEGRADED``。"""

        flags: list[str] = []
        for name in DEGRADATION_FIELDS:
            value = raw.get(name) if isinstance(raw, dict) else getattr(raw, name, None)
            if isinstance(value, bool):
                if value:
                    flags.append(name)
            elif value:
                flags.extend(_as_str_list(value))

        labels = _as_str_list(_first_attr(raw, LABEL_FIELDS))
        mechanisms = _as_str_list(_first_attr(raw, MECHANISM_FIELDS))
        alternatives = _as_str_list(_first_attr(raw, ALTERNATIVE_FIELDS))
        limitations = _as_str_list(_first_attr(raw, LIMITATION_FIELDS))

        if not labels:
            flags.append("missing_behavior_labels")
        if len(alternatives) < 2:
            flags.append("insufficient_alternative_explanations")
            # 契约要求结果至少给出两种替代解释；外部结果不足时补**明确标注的占位**，
            # 既满足展示要求，也不假装外部真的提供了这些解释（PRD 6.1、6.2）。
            while len(alternatives) < MIN_ALTERNATIVE_EXPLANATIONS:
                alternatives.append(
                    f"（外部结果未提供第 {len(alternatives) + 1} 种替代解释，已按降级处理）"
                )

        status = AnalysisStatus.DEGRADED if flags else AnalysisStatus.NORMAL
        disclaimer = _first_attr(raw, ("disclaimer", "notice")) or DISCLAIMER

        return AnalysisReport(
            status=status,
            scene_id=request.scene_id,
            agent_id=request.agent_id,
            behavior_labels=labels,
            mechanisms=mechanisms,
            alternative_explanations=alternatives,
            limitations=limitations or (["外部结果未声明局限"] if status is AnalysisStatus.DEGRADED else []),
            disclaimer=str(disclaimer),
            degradation_flags=sorted(set(flags)),
            provider_attempts=max(self._client.provider_attempts, 1),
            usage=self._client.usage or Usage(),
        )


def load_external_analyzer(
    *,
    module_name: str = DEFAULT_ANALYZER_MODULE,
    class_name: str = DEFAULT_ANALYZER_CLASS,
    client: ControlledAnalysisClient | None = None,
    importer: Callable[[str], Any] | None = None,
) -> Any:
    """导入并实例化外部分析器。

    失败时抛出 :class:`ExternalAnalysisUnavailable`，消息中保留原始错误文本，
    便于界面／运维看清“为什么不可用”，而不是静默变成可用。
    """

    import importlib

    load = importer or importlib.import_module
    try:
        module = load(module_name)
    except Exception as exc:  # noqa: BLE001 - ImportError 及其它导入期错误
        raise ExternalAnalysisUnavailable(
            f"无法导入外部分析仓库模块 {module_name}：{exc.__class__.__name__}: {exc}"
        ) from exc

    analyzer_class = getattr(module, class_name, None)
    if analyzer_class is None:
        raise ExternalAnalysisUnavailable(
            f"模块 {module_name} 中不存在 {class_name}（字段名待联调核对，见 U-M06-1）"
        )

    try:
        return analyzer_class(client=client) if client is not None else analyzer_class()
    except TypeError:
        # 外部构造签名可能不接受 client：退回无参构造，并保留受控客户端供本项目记录。
        return analyzer_class()


__all__ = [
    "DEFAULT_ANALYZER_CLASS",
    "DEFAULT_ANALYZER_MODULE",
    "DISCLAIMER",
    "ExternalAnalysisPort",
    "ExternalAnalysisUnavailable",
    "load_external_analyzer",
]
