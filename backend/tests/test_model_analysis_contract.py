"""模型调用结果与分析结果契约（PRD 4.2、5.3、6.1、6.2）。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from role_theater.contracts import (
    ActionDraft,
    ActionType,
    AnalysisReport,
    AnalysisRequest,
    AnalysisStatus,
    MAX_PROMPT_CHARS,
    ModelActionRequest,
    ModelActionResponse,
    ModelFailure,
    ModelFailureKind,
    ModelParams,
    Usage,
)


def _ok_response(**overrides: object) -> ModelActionResponse:
    base: dict[str, object] = {
        "ok": True,
        "draft": ActionDraft(action=ActionType.SPEAK, text="好。"),
        "prompt_template_id": "role_action@m00",
    }
    base.update(overrides)
    return ModelActionResponse(**base)


def test_response_ok_requires_draft_and_forbids_failure() -> None:
    _ok_response()

    with pytest.raises(ValidationError):
        ModelActionResponse(ok=True, prompt_template_id="t")
    with pytest.raises(ValidationError):
        _ok_response(failure=ModelFailure(kind=ModelFailureKind.PROVIDER_ERROR))


def test_response_failure_requires_classification() -> None:
    ModelActionResponse(
        ok=False,
        failure=ModelFailure(kind=ModelFailureKind.EMPTY_CONTENT),
        prompt_template_id="t",
    )

    with pytest.raises(ValidationError):
        ModelActionResponse(ok=False, prompt_template_id="t")


def test_unsent_request_must_be_marked_unknown_and_not_retried() -> None:
    """发送结果不明：保守占用预算并标记 UNKNOWN（PRD 5.3）。"""

    response = ModelActionResponse(
        ok=False,
        sent=False,
        failure=ModelFailure(kind=ModelFailureKind.UNKNOWN_REQUEST),
        prompt_template_id="t",
    )
    assert response.sent is False

    # UNKNOWN_REQUEST 必须与 sent=False 绑定（不能声称未发送却标记为不明）。
    with pytest.raises(ValidationError):
        ModelActionResponse(
            ok=False,
            sent=True,
            failure=ModelFailure(kind=ModelFailureKind.UNKNOWN_REQUEST),
            prompt_template_id="t",
        )
    with pytest.raises(ValidationError):
        ModelActionResponse(
            ok=True,
            sent=False,
            draft=ActionDraft(action=ActionType.PASS),
            failure=ModelFailure(kind=ModelFailureKind.UNKNOWN_REQUEST),
            prompt_template_id="t",
        )


@pytest.mark.parametrize(
    "kind",
    [
        ModelFailureKind.CONTEXT_LIMIT,
        ModelFailureKind.MISSING_CONFIG,
        ModelFailureKind.BUDGET_EXHAUSTED,
        ModelFailureKind.NOT_DISPATCHED,
    ],
)
def test_local_refusal_before_dispatch_is_allowed_without_unknown_marking(
    kind: ModelFailureKind,
) -> None:
    """本地拒绝发送（未新增模型请求）不占用预算，因此不必标记 UNKNOWN（PRD 5.3）。"""

    response = ModelActionResponse(
        ok=False,
        sent=False,
        failure=ModelFailure(kind=kind),
        prompt_template_id="t",
    )

    assert response.sent is False
    assert response.failure is not None
    assert response.failure.kind is kind
    # 未发送仍然不得携带 draft。
    with pytest.raises(ValidationError):
        ModelActionResponse(
            ok=True,
            sent=False,
            draft=ActionDraft(action=ActionType.PASS),
            prompt_template_id="t",
        )


def test_prompt_longer_than_limit_must_pause_not_truncate() -> None:
    ModelActionRequest(
        scene_id="scene-1",
        actor_id="agent-1",
        prompt_template_id="role_action@m00",
        prompt="x" * MAX_PROMPT_CHARS,
        cursor_seq=0,
    )

    with pytest.raises(ValidationError):
        ModelActionRequest(
            scene_id="scene-1",
            actor_id="agent-1",
            prompt_template_id="role_action@m00",
            prompt="x" * (MAX_PROMPT_CHARS + 1),
            cursor_seq=0,
        )


def test_response_records_both_requested_and_returned_model() -> None:
    response = _ok_response(requested_model="deepseek-flash", returned_model="deepseek-flash-2026-09-10")

    assert response.requested_model == "deepseek-flash"
    # 别名可能变化，因此两个模型名都要记录（PRD 2.2）。
    assert response.returned_model == "deepseek-flash-2026-09-10"
    assert response.usage.is_unknown


def test_analysis_request_forces_persist_profile_false() -> None:
    AnalysisRequest(
        scene_id="scene-1",
        agent_id="agent-1",
        behavior_description="安然主动邀请室友。",
    )

    with pytest.raises(ValidationError):
        AnalysisRequest(
            scene_id="scene-1",
            agent_id="agent-1",
            behavior_description="安然主动邀请室友。",
            persist_profile=True,
        )


def test_analysis_material_limits() -> None:
    AnalysisRequest(
        scene_id="scene-1",
        agent_id="agent-1",
        behavior_description="描述",
        context="字" * 4000,
    )
    with pytest.raises(ValidationError):
        AnalysisRequest(
            scene_id="scene-1",
            agent_id="agent-1",
            behavior_description="字" * 4001,
        )
    with pytest.raises(ValidationError):
        AnalysisRequest(
            scene_id="scene-1",
            agent_id="agent-1",
            behavior_description="描述",
            context="字" * 4001,
        )


def test_analysis_report_requires_alternatives_and_disclaimer() -> None:
    AnalysisReport(
        status=AnalysisStatus.NORMAL,
        alternative_explanations=["可能是礼貌", "可能是疲惫"],
        disclaimer="仅供解释虚构行为。",
    )

    with pytest.raises(ValidationError):
        AnalysisReport(
            status=AnalysisStatus.NORMAL,
            alternative_explanations=["只有一个解释"],
            disclaimer="仅供解释虚构行为。",
        )
    with pytest.raises(ValidationError):
        AnalysisReport(
            status=AnalysisStatus.NORMAL,
            alternative_explanations=["a", "b"],
        )


def test_blocked_and_disabled_reports_have_zero_provider_attempts() -> None:
    AnalysisReport(status=AnalysisStatus.BLOCKED, provider_attempts=0)
    AnalysisReport(status=AnalysisStatus.DISABLED, provider_attempts=0)

    with pytest.raises(ValidationError):
        AnalysisReport(status=AnalysisStatus.BLOCKED, provider_attempts=1)


def test_failed_report_must_explain_error() -> None:
    AnalysisReport(status=AnalysisStatus.FAILED, error="provider timeout")

    with pytest.raises(ValidationError):
        AnalysisReport(status=AnalysisStatus.FAILED)


def test_five_analysis_statuses_are_distinct() -> None:
    assert {status.value for status in AnalysisStatus} == {
        "NORMAL",
        "BLOCKED",
        "DEGRADED",
        "FAILED",
        "DISABLED",
    }


def test_model_params_defaults_are_not_mutated_across_requests() -> None:
    first = ModelActionRequest(
        scene_id="s",
        actor_id="a",
        prompt_template_id="t",
        prompt="p",
        cursor_seq=0,
    )
    second = ModelActionRequest(
        scene_id="s",
        actor_id="a",
        prompt_template_id="t",
        prompt="p",
        cursor_seq=0,
    )

    assert first.params == second.params == ModelParams()
    assert Usage().is_unknown
