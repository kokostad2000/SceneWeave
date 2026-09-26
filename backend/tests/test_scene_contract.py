"""角色、场景与预算契约（PRD 3.2、3.3、5.3）。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from role_theater.contracts import (
    AgentSnapshot,
    AgentTemplate,
    Budget,
    BudgetUsage,
    PauseReason,
    RunState,
    Scene,
    SceneAgent,
    validate_agent_count,
)


def _now() -> datetime:
    return datetime(2026, 9, 26, 20, 0, tzinfo=UTC)


def test_agent_count_range_is_two_to_eight() -> None:
    assert validate_agent_count(2) == 2
    assert validate_agent_count(3) == 3
    assert validate_agent_count(5) == 5
    assert validate_agent_count(8) == 8

    for bad in (0, 1, 9, 100):
        with pytest.raises(ValueError):
            validate_agent_count(bad)


def test_agent_profile_length_limits_use_codepoints() -> None:
    AgentTemplate(
        template_id="tpl-1",
        name="安" * 30,
        persona="人" * 1000,
        speech_style="语" * 300,
        initial_goal="目" * 500,
        private_background="私" * 1000,
        created_at=_now(),
        updated_at=_now(),
    )

    with pytest.raises(ValidationError):
        AgentTemplate(
            template_id="tpl-2",
            name="安" * 31,
            persona="",
            speech_style="",
            initial_goal="",
            private_background="",
            created_at=_now(),
            updated_at=_now(),
        )
    with pytest.raises(ValidationError):
        AgentTemplate(
            template_id="tpl-3",
            name="",
            persona="",
            speech_style="",
            initial_goal="",
            private_background="",
            created_at=_now(),
            updated_at=_now(),
        )


def test_snapshot_is_a_value_copy_of_template() -> None:
    """模板改动不影响已有会话快照（PRD 3.2）。"""

    template = AgentTemplate(
        template_id="tpl-1",
        name="许川",
        persona="表达直接",
        speech_style="短句",
        initial_goal="想休息",
        private_background="今天工作很累",
        created_at=_now(),
        updated_at=_now(),
    )
    snapshot = AgentSnapshot(
        source_template_id=template.template_id,
        name=template.name,
        persona=template.persona,
        speech_style=template.speech_style,
        initial_goal=template.initial_goal,
        private_background=template.private_background,
        captured_at=_now(),
    )

    template.private_background = "被改写的背景"
    template.name = "改名"

    assert snapshot.private_background == "今天工作很累"
    assert snapshot.name == "许川"
    assert snapshot.source_template_id == "tpl-1"


def test_scene_agent_display_name_is_bounded() -> None:
    snapshot = AgentSnapshot(
        source_template_id="tpl-1",
        name="陈禾",
        persona="刚搬来",
        speech_style="客气",
        initial_goal="想融入",
        private_background="不想打扰别人",
        captured_at=_now(),
    )
    SceneAgent(
        agent_id="agent-1",
        scene_id="scene-1",
        name="陈禾",
        order_index=2,
        snapshot=snapshot,
        created_at=_now(),
    )

    with pytest.raises(ValidationError):
        SceneAgent(
            agent_id="agent-1",
            scene_id="scene-1",
            name="长" * 31,
            order_index=0,
            snapshot=snapshot,
            created_at=_now(),
        )


def test_budget_defaults_and_bounds() -> None:
    budget = Budget()
    # 人工裁决 2026-09-26：角色请求默认上限由 24 上调为 200（分析仍为 4）。
    assert budget.max_role_requests == 200
    assert budget.max_analysis_requests == 4
    assert budget.locked_at is None

    with pytest.raises(ValidationError):
        Budget(max_role_requests=0)
    with pytest.raises(ValidationError):
        Budget(max_role_requests=10_000)

    usage = BudgetUsage()
    assert usage.role_requests_used == 0
    with pytest.raises(ValidationError):
        # 同一时刻每个类别最多一个在途请求（PRD 5.3）。
        BudgetUsage(role_requests_in_flight=2)


def test_paused_scene_must_explain_why() -> None:
    kwargs = {
        "scene_id": "scene-1",
        "title": "三个室友的客厅",
        "background": "晚上，三个室友在客厅相遇，尚未确定今晚做什么。",
        "budget": Budget(),
        "created_at": _now(),
    }

    Scene(**kwargs, status=RunState.READY)

    with pytest.raises(ValidationError):
        Scene(**kwargs, status=RunState.PAUSED)

    paused = Scene(**kwargs, status=RunState.PAUSED, pause_reason=PauseReason.NO_NEW_INFORMATION)
    assert paused.pause_reason is PauseReason.NO_NEW_INFORMATION

    with pytest.raises(ValidationError):
        Scene(**kwargs, status=RunState.RUNNING, pause_reason=PauseReason.MANUAL)

    with pytest.raises(ValidationError):
        Scene(**kwargs, status=RunState.ENDED)


def test_scene_background_limit() -> None:
    kwargs = {
        "scene_id": "scene-1",
        "title": "标题",
        "budget": Budget(),
        "created_at": _now(),
    }
    Scene(**kwargs, background="景" * 2000)
    with pytest.raises(ValidationError):
        Scene(**kwargs, background="景" * 2001)
