"""分析边界规则（PRD 6.1）——**纯函数**。

只有“已经提交的公开发言”和“已生效的公开事件”可以送交分析。私有背景、定向事件
与尚未生效的事件一律拒绝；`behavior_description` 与 `context` 各自超过 4000 字符
即拦截并提示缩小选择，**不截断、不自动总结**。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts import (
    MAX_ANALYSIS_BEHAVIOR_DESCRIPTION_CODEPOINTS,
    MAX_ANALYSIS_CONTEXT_CODEPOINTS,
    AnalysisMaterialRef,
    codepoint_length,
)
from ..contracts.enums import MessageVisibility
from ..context.models import TimelineItem, TimelineKind

#: 拦截原因（写入 `error` 与 `degradation_flags`，便于界面解释为何没有送出材料）。
REASON_NO_MATERIAL = "no_material_selected"
REASON_UNKNOWN_SEQ = "unknown_material_seq"
REASON_TARGETED_EVENT = "targeted_event_not_allowed"
REASON_PENDING_EVENT = "pending_event_not_allowed"
REASON_PRIVATE_CONTENT = "private_content_not_allowed"
REASON_TOO_LONG = "material_too_long"


@dataclass(frozen=True, slots=True)
class BoundaryDecision:
    """边界判定结果。``allowed=False`` 时不得发起任何分析调用。"""

    allowed: bool
    reason: str | None
    detail: str
    behavior_description: str
    context: str
    materials: tuple[AnalysisMaterialRef, ...]
    flags: tuple[str, ...] = ()


def _render_message(item: TimelineItem) -> str:
    return f"[#{item.seq}] {item.author_name or item.author_agent_id or '角色'}（发言）：{item.body}"


def _render_event(item: TimelineItem) -> str:
    return f"[#{item.seq}] 事件（公开）：{item.body}"


def evaluate_selection(
    *,
    timeline: tuple[TimelineItem, ...],
    agent_id: str,
    agent_name: str,
    selected_seqs: tuple[int, ...],
) -> BoundaryDecision:
    """校验选择并构建送入分析的两个字段。

    ``timeline`` 应为该场景**已提交**的条目（消息 + 已生效事件）。
    """

    if not selected_seqs:
        return _blocked(REASON_NO_MATERIAL, "尚未选择任何公开材料")

    by_seq = {item.seq: item for item in timeline}
    selected: list[TimelineItem] = []
    for seq in dict.fromkeys(selected_seqs):  # 去重但保持传入顺序
        item = by_seq.get(seq)
        if item is None:
            return _blocked(REASON_UNKNOWN_SEQ, f"选择的材料 #{seq} 不存在或尚未提交")
        if item.kind is TimelineKind.MESSAGE and item.message_visibility is MessageVisibility.PRIVATE:
            return _blocked(REASON_PRIVATE_CONTENT, f"#{seq} 是私聊，不送出分析")
        if item.kind is TimelineKind.EVENT:
            if item.visibility is not None and item.visibility.value == "TARGETED":
                return _blocked(
                    REASON_TARGETED_EVENT,
                    f"#{seq} 是定向事件，默认不送出分析（即使操作者可以看到）",
                )
            if item.visibility is None:  # pragma: no cover - 事件必有可见范围
                return _blocked(REASON_PENDING_EVENT, f"#{seq} 事件缺少可见范围")
        selected.append(item)

    selected.sort(key=lambda item: item.seq)

    own_speech = [item for item in selected if item.author_agent_id == agent_id]
    others = [item for item in selected if item.author_agent_id != agent_id]

    behavior_description = "\n".join(_render_message(item) for item in own_speech)
    if behavior_description:
        behavior_description = (
            f"分析对象：{agent_name}。仅分析此角色的公开发言行为；"
            "其他角色的发言和事件只用于理解情境，不要将其行为归给分析对象。\n"
            f"{behavior_description}"
        )
    context = "\n".join(
        _render_event(item) if item.kind is TimelineKind.EVENT else _render_message(item)
        for item in others
    )

    if codepoint_length(behavior_description) > MAX_ANALYSIS_BEHAVIOR_DESCRIPTION_CODEPOINTS:
        return _blocked(
            REASON_TOO_LONG,
            f"选中的「{agent_name}」本人发言共 {codepoint_length(behavior_description)} 个码点，"
            f"超过 {MAX_ANALYSIS_BEHAVIOR_DESCRIPTION_CODEPOINTS} 上限；请缩小选择（不会截断或自动总结）",
        )
    if codepoint_length(context) > MAX_ANALYSIS_CONTEXT_CODEPOINTS:
        return _blocked(
            REASON_TOO_LONG,
            f"选中的上下文共 {codepoint_length(context)} 个码点，"
            f"超过 {MAX_ANALYSIS_CONTEXT_CODEPOINTS} 上限；请缩小选择（不会截断或自动总结）",
        )
    if behavior_description == "" and context == "":
        return _blocked(REASON_NO_MATERIAL, "选中的材料为空")

    if behavior_description == "":
        # 只选了别人的发言/公开事件：可以分析，但明确标注缺少本人发言。
        flags = ("no_self_speech_selected",)
    else:
        flags = ()

    materials = tuple(
        AnalysisMaterialRef(
            kind=item.kind.value,
            source_id=_source_id(item),
            author_agent_id=item.author_agent_id,
            text=item.body,
        )
        for item in selected
    )
    return BoundaryDecision(
        allowed=True,
        reason=None,
        detail="材料通过本地边界规则",
        behavior_description=behavior_description,
        context=context,
        materials=materials,
        flags=flags,
    )


def _source_id(item: TimelineItem) -> str:
    """材料来源 ID：消息用消息 ID 语义（此处以 seq 与作者稳定标识），事件同理。"""

    author = item.author_agent_id or "operator"
    return f"{item.kind.value}:{item.seq}:{author}"


def _blocked(reason: str, detail: str) -> BoundaryDecision:
    return BoundaryDecision(
        allowed=False,
        reason=reason,
        detail=detail,
        behavior_description="",
        context="",
        materials=(),
        flags=(reason,),
    )


__all__ = [
    "REASON_NO_MATERIAL",
    "REASON_PENDING_EVENT",
    "REASON_PRIVATE_CONTENT",
    "REASON_TARGETED_EVENT",
    "REASON_TOO_LONG",
    "REASON_UNKNOWN_SEQ",
    "BoundaryDecision",
    "evaluate_selection",
]
