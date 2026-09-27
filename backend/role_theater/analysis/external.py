"""外部分析仓库适配层（PRD 6.2）。

**本模块是唯一允许导入外部 `behavior-psychology-v2.0` 代码的位置。**

未验证项（不得据项目名或历史对话臆造后声称为已验证）：

* 上游提交 ``bd1e8fa`` 的模块路径、构造签名和响应字段已离线核对。
* U-M06-3：真实供应商与受控客户端的兼容性及分析质量仍待联调。

外部包不可导入时：返回 ``DISABLED`` 并带上原始错误文本，**不抛异常、不影响聊天**；
禁用分析时**不导入**任何外部包。
"""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

from ..contracts import (
    AnalysisReport,
    AnalysisRequest,
    AnalysisStatus,
    Usage,
)
from ..contracts.analysis import MIN_ALTERNATIVE_EXPLANATIONS
from ..ports.token_limit import (
    SingleCallTokenLimitExceeded,
    actual_usage_exceeds_single_call_limit,
    check_single_call_token_limit,
)
from .controlled_client import AttemptRecord, ControlledAnalysisClient

#: 已按锁定上游提交核对的导入位置。
DEFAULT_ANALYZER_MODULE = "src.analyzer"
DEFAULT_ANALYZER_CLASS = "DefaultBehaviorAnalyzer"
DEFAULT_REQUEST_MODULE = "src.schemas"
DEFAULT_REQUEST_CLASS = "AnalysisRequest"

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
        result = []
        for item in value:
            name = getattr(item, "name", None) or getattr(item, "perspective", None)
            explanation = getattr(item, "explanation", None) or getattr(item, "reasoning", None)
            rendered = f"{name}：{explanation}" if name and explanation else str(item)
            if rendered.strip():
                result.append(rendered)
        return result
    return [str(value)]


class UpstreamCompletionClient:
    """Expose the upstream SDK shape while enforcing our request and usage rules."""

    def __init__(self, *, api_key: str | None, base_url: str, provider: str) -> None:
        self._api_key = api_key or "local-no-credential"
        self._base_url = base_url
        self._sdk: Any = None
        self._provider = provider
        self.chat = SimpleNamespace(completions=self)
        self.attempts: list[AttemptRecord] = []

    def _ensure_sdk(self) -> Any:
        if self._sdk is None:
            from openai import AsyncOpenAI

            self._sdk = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                max_retries=0,
                timeout=90.0,
            )
        return self._sdk

    @property
    def provider_attempts(self) -> int:
        return len(self.attempts)

    @property
    def usage(self) -> Usage:
        if not self.attempts:
            return Usage()
        return self.attempts[-1].usage

    async def create(self, **kwargs: Any) -> Any:
        kwargs["stream"] = False
        kwargs.pop("tools", None)
        check_single_call_token_limit(kwargs.get("messages"), kwargs.get("max_tokens"))
        if self._provider == "deepseek":
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        number = len(self.attempts) + 1
        try:
            response = await self._ensure_sdk().chat.completions.create(**kwargs)
        except Exception as exc:
            self.attempts.append(
                AttemptRecord(provider_attempt=number, model=str(kwargs["model"]), ok=False,
                              error=exc.__class__.__name__)
            )
            raise
        raw_usage = getattr(response, "usage", None)
        input_tokens = getattr(raw_usage, "prompt_tokens", None)
        output_tokens = getattr(raw_usage, "completion_tokens", None)
        self.attempts.append(
            AttemptRecord(
                provider_attempt=number,
                model=str(kwargs["model"]),
                ok=True,
                usage=Usage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cached_tokens=getattr(
                        getattr(raw_usage, "prompt_tokens_details", None), "cached_tokens", None
                    ),
                ),
            )
        )
        if actual_usage_exceeds_single_call_limit(input_tokens, output_tokens):
            raise SingleCallTokenLimitExceeded(
                "供应商报告的单次 token 用量超过 10,000,000"
            )
        return response

    async def close(self) -> None:
        if self._sdk is not None:
            await self._sdk.close()
            self._sdk = None


class ExternalAnalysisPort:
    """通过外部仓库执行分析。

    ``analyzer_factory`` 由 :func:`load_external_analyzer` 提供；测试可注入假实现，
    因此本类的状态映射逻辑可以在**没有外部包**的环境下被完整测试。
    """

    def __init__(
        self,
        *,
        analyzer: Any,
        client: Any = None,
        request_class: type | None = None,
        boundary_check: Callable[[str, str | None], Any] | None = None,
    ) -> None:
        self._analyzer = analyzer
        self._client = client or ControlledAnalysisClient()
        self._request_class = request_class
        self._boundary_check = boundary_check

    @property
    def enabled(self) -> bool:
        return True

    @property
    def client(self) -> Any:
        return self._client

    def precheck(self, request: AnalysisRequest) -> str | None:
        if not request.behavior_description.strip():
            return "所选材料不含该角色的公开发言，无法分析其行为"
        if self._boundary_check is not None:
            decision = self._boundary_check(request.behavior_description, request.context)
            if decision is not None:
                return str(decision.message)
        return None

    async def close(self) -> None:
        if isinstance(self._client, UpstreamCompletionClient):
            await self._client.close()

    async def analyze(self, request: AnalysisRequest) -> AnalysisReport:
        if request.persist_profile:  # pragma: no cover - 契约层已强制
            raise ValueError("persist_profile 必须为 false（PRD 6.2）")

        try:
            # 强制关闭画像写入：即使外部默认开启也不允许。
            payload = request.model_copy(update={"persist_profile": False})
            if self._request_class is not None:
                payload = self._request_class(
                    behavior_description=payload.behavior_description,
                    context=payload.context or None,
                    persist_profile=False,
                )
            raw = await self._invoke(payload)
        except Exception as exc:  # noqa: BLE001 - 任何外部异常都必须变成 FAILED
            attempts = self._client.provider_attempts
            upstream = isinstance(self._client, UpstreamCompletionClient)
            if not upstream:
                attempts = max(attempts, 1)
            detail = "" if upstream else f": {exc}"
            return AnalysisReport(
                status=AnalysisStatus.FAILED,
                scene_id=request.scene_id,
                agent_id=request.agent_id,
                provider_attempts=attempts,
                usage=self._client.usage,
                error=f"外部分析调用失败：{exc.__class__.__name__}{detail}",
                degradation_flags=["provider_exception"],
            )

        return self._to_report(raw, request)

    async def _invoke(self, request: AnalysisRequest) -> Any:
        try:
            result = self._analyzer.analyze(request)
            if hasattr(result, "__await__"):
                return await result
            return result
        finally:
            await self.close()

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

        if getattr(raw, "blocked", False):
            return AnalysisReport(
                status=AnalysisStatus.BLOCKED,
                scene_id=request.scene_id,
                agent_id=request.agent_id,
                provider_attempts=0,
                degradation_flags=[str(getattr(raw, "safety_category", "upstream_boundary"))],
                error="上游安全边界已拦截分析",
            )
        labels = _as_str_list(_first_attr(raw, ("tags", *LABEL_FIELDS)))
        mechanisms = _as_str_list(_first_attr(raw, ("psychological_mechanisms", *MECHANISM_FIELDS)))
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

        if getattr(raw, "profile_persisted", False):
            return AnalysisReport(
                status=AnalysisStatus.FAILED,
                scene_id=request.scene_id,
                agent_id=request.agent_id,
                provider_attempts=max(self._client.provider_attempts, 1),
                error="上游意外写入画像；违反 persist_profile=false 约束",
                degradation_flags=["profile_persisted_unexpectedly"],
            )
        if isinstance(self._client, UpstreamCompletionClient) and self._client.provider_attempts == 0:
            return AnalysisReport(
                status=AnalysisStatus.FAILED,
                scene_id=request.scene_id,
                agent_id=request.agent_id,
                provider_attempts=0,
                error="上游未发起模型请求，不能把结果记为真实分析",
                degradation_flags=["no_provider_attempt"],
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
    client: Any = None,
    runtime_config: Any = None,
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
        kwargs = {}
        if client is not None:
            kwargs["client"] = client
        if runtime_config is not None:
            kwargs["config"] = runtime_config
        return analyzer_class(**kwargs)
    except Exception as exc:
        raise ExternalAnalysisUnavailable(
            f"无法构造外部分析器 {class_name}：{exc.__class__.__name__}: {exc}"
        ) from exc


def build_upstream_port(*, provider: str, api_key: str | None, base_url: str,
                        model: str) -> ExternalAnalysisPort:
    """Build the pinned upstream implementation with explicit local configuration."""
    import importlib

    try:
        schemas = importlib.import_module(DEFAULT_REQUEST_MODULE)
        config_module = importlib.import_module("src.config")
        safety_module = importlib.import_module("src.safety")
    except Exception as exc:
        raise ExternalAnalysisUnavailable(
            f"无法导入外部分析契约：{exc.__class__.__name__}: {exc}"
        ) from exc
    client = UpstreamCompletionClient(api_key=api_key, base_url=base_url, provider=provider)
    config = config_module.RuntimeConfig(
        provider=provider,
        api_key=api_key or "local-no-credential",
        model=model,
        base_url=base_url,
        timeout_seconds=90.0,
        max_retries=0,
    )
    analyzer = load_external_analyzer(client=client, runtime_config=config)
    return ExternalAnalysisPort(analyzer=analyzer, client=client,
                                request_class=schemas.AnalysisRequest,
                                boundary_check=safety_module.check_boundary)

__all__ = [
    "DEFAULT_ANALYZER_CLASS",
    "DEFAULT_ANALYZER_MODULE",
    "DISCLAIMER",
    "ExternalAnalysisPort",
    "ExternalAnalysisUnavailable",
    "load_external_analyzer",
]
