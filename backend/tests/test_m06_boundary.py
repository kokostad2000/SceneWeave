"""M06 边界规则（PRD 6.1；tasks/M06.md A1–A3）。

纯函数测试：不涉及数据库、不涉及外部包。**私有内容不可能进入材料**是结构性保证——
`TimelineItem` 根本没有承载私有资料的字段。
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from role_theater.analysis import evaluate_selection
from role_theater.analysis.boundary import (
    REASON_NO_MATERIAL,
    REASON_TARGETED_EVENT,
    REASON_TOO_LONG,
    REASON_UNKNOWN_SEQ,
)
from role_theater.context import TimelineItem, TimelineKind
from role_theater.contracts import (
    MAX_ANALYSIS_BEHAVIOR_DESCRIPTION_CODEPOINTS,
    MAX_ANALYSIS_CONTEXT_CODEPOINTS,
    EventVisibility,
    codepoint_length,
)

NOW = datetime(2026, 9, 26, 20, 0, tzinfo=UTC)


def message(seq: int, agent_id: str, name: str, text: str) -> TimelineItem:
    return TimelineItem(
        kind=TimelineKind.MESSAGE,
        seq=seq,
        body=text,
        author_agent_id=agent_id,
        author_name=name,
    )


def event(seq: int, body: str, visibility: EventVisibility = EventVisibility.ALL) -> TimelineItem:
    return TimelineItem(
        kind=TimelineKind.EVENT,
        seq=seq,
        body=body,
        author_agent_id=None,
        visibility=visibility,
        target_agent_id="agt-xu" if visibility is EventVisibility.TARGETED else None,
    )


def timeline() -> tuple[TimelineItem, ...]:
    return (
        message(1, "agt-an", "安然", "今晚一起吃饭吗？"),
        message(2, "agt-xu", "许川", "我想先休息。"),
        event(3, "客厅的灯突然灭了。"),
        event(4, "只给许川的提示。", EventVisibility.TARGETED),
    )


def test_public_materials_are_split_into_self_and_context() -> None:
    decision = evaluate_selection(
        timeline=timeline(),
        agent_id="agt-an",
        agent_name="安然",
        selected_seqs=(1, 2, 3),
    )

    assert decision.allowed is True
    assert decision.behavior_description.startswith("分析对象：安然。仅分析此角色")
    assert "#1" in decision.behavior_description
    assert "今晚一起吃饭吗？" in decision.behavior_description
    assert "我想先休息。" in decision.context
    assert "灯突然灭了" in decision.context
    # 本人的发言不出现在 context 里，别人的发言不出现在 behavior_description 里。
    assert "我想先休息。" not in decision.behavior_description
    assert "今晚一起吃饭吗？" not in decision.context
    # 材料保留原文与来源角色。
    assert [material.author_agent_id for material in decision.materials] == ["agt-an", "agt-xu", None]


def test_private_profile_never_enters_the_materials() -> None:
    decision = evaluate_selection(
        timeline=timeline(), agent_id="agt-an", agent_name="安然", selected_seqs=(1,)
    )

    # 结构性保证：可选材料只有发言与事件，TimelineItem 没有私有字段。
    fields = set(TimelineItem.__dataclass_fields__)
    assert "private_background" not in fields
    assert "persona" not in fields
    assert "initial_goal" not in fields
    assert "朋友临时取消了聚会" not in decision.behavior_description
    assert "朋友临时取消了聚会" not in decision.context


def test_targeted_event_is_refused_even_though_the_operator_can_see_it() -> None:
    decision = evaluate_selection(
        timeline=timeline(), agent_id="agt-an", agent_name="安然", selected_seqs=(4,)
    )

    assert decision.allowed is False
    assert decision.reason == REASON_TARGETED_EVENT
    assert "定向事件" in decision.detail
    assert decision.materials == ()


def test_empty_selection_is_refused() -> None:
    decision = evaluate_selection(
        timeline=timeline(), agent_id="agt-an", agent_name="安然", selected_seqs=()
    )

    assert decision.allowed is False
    assert decision.reason == REASON_NO_MATERIAL


def test_unknown_seq_is_refused() -> None:
    decision = evaluate_selection(
        timeline=timeline(), agent_id="agt-an", agent_name="安然", selected_seqs=(99,)
    )

    assert decision.allowed is False
    assert decision.reason == REASON_UNKNOWN_SEQ


def test_selection_is_deduplicated_and_sorted() -> None:
    decision = evaluate_selection(
        timeline=timeline(), agent_id="agt-an", agent_name="安然", selected_seqs=(3, 1, 1)
    )

    assert decision.allowed is True
    assert decision.behavior_description.count("#1") == 1
    assert decision.context.count("#3") == 1


def _rendered_prefix_length() -> int:
    """渲染后的固定前缀长度（`[#seq] 名称（发言）：`）。"""

    probe = evaluate_selection(
        timeline=(message(1, "agt-an", "安然", ""),),
        agent_id="agt-an",
        agent_name="安然",
        selected_seqs=(1,),
    )
    return codepoint_length(probe.behavior_description)


@pytest.mark.parametrize("overflow", [0, 1])
def test_behavior_description_limit_is_enforced_on_rendered_text(overflow: int) -> None:
    """上限作用于**实际送出的文本**（含序号与来源），并且不截断。"""

    limit = MAX_ANALYSIS_BEHAVIOR_DESCRIPTION_CODEPOINTS
    body_length = limit - _rendered_prefix_length() + overflow
    long_timeline = (message(1, "agt-an", "安然", "字" * body_length),)

    decision = evaluate_selection(
        timeline=long_timeline, agent_id="agt-an", agent_name="安然", selected_seqs=(1,)
    )

    if overflow == 0:
        assert decision.allowed is True
        assert codepoint_length(decision.behavior_description) == limit
    else:
        assert decision.allowed is False
        assert decision.reason == REASON_TOO_LONG
        assert "缩小选择" in decision.detail
        assert decision.behavior_description == "", "不得截断后照常送出"


@pytest.mark.parametrize("overflow", [0, 1])
def test_context_limit_is_enforced_on_rendered_text(overflow: int) -> None:
    limit = MAX_ANALYSIS_CONTEXT_CODEPOINTS
    prefix = codepoint_length("[#2] 许川（发言）：")
    body_length = limit - prefix + overflow
    long_timeline = (
        message(1, "agt-an", "安然", "我先说一句。"),
        message(2, "agt-xu", "许川", "字" * body_length),
    )

    decision = evaluate_selection(
        timeline=long_timeline, agent_id="agt-an", agent_name="安然", selected_seqs=(1, 2)
    )

    if overflow == 0:
        assert decision.allowed is True
        assert codepoint_length(decision.context) == limit
    else:
        assert decision.allowed is False
        assert decision.reason == REASON_TOO_LONG


def test_selecting_only_others_material_is_allowed_but_flagged() -> None:
    """只选他人材料时可以分析，但必须标注缺少本人发言（不悄悄补全）。"""

    decision = evaluate_selection(
        timeline=timeline(), agent_id="agt-an", agent_name="安然", selected_seqs=(2,)
    )

    assert decision.allowed is True
    assert decision.behavior_description == ""
    assert "no_self_speech_selected" in decision.flags


def test_pending_event_is_not_in_the_timeline_so_it_cannot_be_selected() -> None:
    """尚未生效的事件不会出现在已提交时间线里，因此选不中（PRD 4.3）。"""

    decision = evaluate_selection(
        timeline=(message(1, "agt-an", "安然", "你好。"),),
        agent_id="agt-an",
        agent_name="安然",
        selected_seqs=(2,),
    )

    assert decision.allowed is False
    assert decision.reason == REASON_UNKNOWN_SEQ
