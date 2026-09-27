"""外部端口契约与 Mock 行为（PRD 4.2、5.3、6.2）。

全部测试离线运行，不联网、不需要密钥。
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from role_theater.contracts import (
    ActionDraft,
    ActionType,
    AnalysisRequest,
    AnalysisStatus,
    ModelActionRequest,
    ModelFailure,
    ModelFailureKind,
    ModelParams,
    Usage,
)
from role_theater.ports import (
    DisabledAnalysisPort,
    MockAnalysisPort,
    MockModelPort,
    ModelPort,
    AnalysisPort,
    load_analysis_port,
)


def _request(prompt: str = "公开背景 + 你的私有背景 ……") -> ModelActionRequest:
    return ModelActionRequest(
        scene_id="scene-1",
        actor_id="agent-1",
        prompt_template_id="role_action@m00",
        prompt=prompt,
        cursor_seq=0,
    )


async def test_mock_model_port_returns_scripted_drafts_in_order() -> None:
    port = MockModelPort(
        script=[
            ActionDraft(action=ActionType.SPEAK, text="我先说一句。"),
            ActionDraft(action=ActionType.PASS),
        ]
    )

    first = await port.generate_action(_request())
    second = await port.generate_action(_request())
    third = await port.generate_action(_request())

    assert first.ok and first.draft is not None
    assert first.draft.text == "我先说一句。"
    assert second.ok and second.draft is not None
    assert second.draft.action is ActionType.PASS
    # 脚本用尽后使用默认 PASS，不伪造发言。
    assert third.ok and third.draft is not None
    assert third.draft.action is ActionType.PASS
    assert port.call_count == 3


async def test_mock_model_port_reports_structured_failures() -> None:
    port = MockModelPort(
        script=[
            ModelFailure(kind=ModelFailureKind.EMPTY_CONTENT, detail="空 content"),
            ModelFailure(kind=ModelFailureKind.TRUNCATED, detail="finish_reason=length"),
            ModelFailure(kind=ModelFailureKind.INVALID_JSON, detail="非法 JSON"),
        ]
    )

    for expected in (
        ModelFailureKind.EMPTY_CONTENT,
        ModelFailureKind.TRUNCATED,
        ModelFailureKind.INVALID_JSON,
    ):
        response = await port.generate_action(_request())
        assert response.ok is False
        assert response.draft is None
        assert response.failure is not None
        assert response.failure.kind is expected


async def test_mock_model_port_does_not_fabricate_usage() -> None:
    port = MockModelPort()
    response = await port.generate_action(_request())

    # 缺失用量记为 unknown，不是 0（PRD 5.3）。
    assert response.usage.is_unknown
    assert response.usage.input_tokens is None
    assert response.usage.output_tokens is None


async def test_mock_model_port_records_calls_for_assertions() -> None:
    port = MockModelPort(usage=Usage(input_tokens=120, output_tokens=18))
    request = _request(prompt="具体上下文")
    response = await port.generate_action(request)

    assert port.calls == [request]
    assert response.usage.input_tokens == 120
    assert response.requested_model == "deepseek-flash"


def test_mock_ports_satisfy_protocols() -> None:
    assert isinstance(MockModelPort(), ModelPort)
    assert isinstance(MockAnalysisPort(), AnalysisPort)
    assert isinstance(DisabledAnalysisPort(), AnalysisPort)


async def test_disabled_analysis_port_needs_no_external_package() -> None:
    port = DisabledAnalysisPort()
    report = await port.analyze(
        AnalysisRequest(
            scene_id="scene-1",
            agent_id="agent-1",
            behavior_description="安然主动找人聊天。",
        )
    )

    assert port.enabled is False
    assert report.status is AnalysisStatus.DISABLED
    # 本地边界拦截：记录一次分析操作，但 provider_attempts=0（PRD 5.3）。
    assert report.provider_attempts == 0


async def test_mock_analysis_port_returns_two_alternative_explanations() -> None:
    port = MockAnalysisPort()
    report = await port.analyze(
        AnalysisRequest(
            scene_id="scene-1",
            agent_id="agent-1",
            behavior_description="许川回答得很短。",
            context="公开聊天记录……",
        )
    )

    assert report.status is AnalysisStatus.NORMAL
    assert len(report.alternative_explanations) >= 2
    assert report.disclaimer
    assert report.usage.is_unknown


async def test_mock_analysis_port_keeps_degradation_visible() -> None:
    port = MockAnalysisPort(
        status=AnalysisStatus.DEGRADED,
        degradation_flags=("provider_exception_swallowed",),
    )
    report = await port.analyze(
        AnalysisRequest(
            scene_id="scene-1",
            agent_id="agent-1",
            behavior_description="陈禾多次附和。",
        )
    )

    assert report.status is AnalysisStatus.DEGRADED
    assert "provider_exception_swallowed" in report.degradation_flags


async def test_blocked_analysis_never_claims_provider_attempt() -> None:
    port = MockAnalysisPort(status=AnalysisStatus.BLOCKED)
    report = await port.analyze(
        AnalysisRequest(
            scene_id="scene-1",
            agent_id="agent-1",
            behavior_description="包含私有背景的选择。",
        )
    )

    assert report.status is AnalysisStatus.BLOCKED
    assert report.provider_attempts == 0


def test_analysis_port_factory_never_creates_a_fake_capability() -> None:
    """M00 尚未接入外部仓库：即便配置开启也必须显式关闭，不出现假完成态。"""

    port = load_analysis_port(enabled=True)
    offline = load_analysis_port(enabled=False)

    assert port.enabled is False
    assert offline.enabled is False


def test_analysis_layer_does_not_import_external_src_package() -> None:
    """禁用分析时不得导入外部仓库的顶层 ``src`` 包（PRD 6.2）。"""
    result = subprocess.run(
        [
            sys.executable, "-c",
            "import sys; "
            "from role_theater.ports.analysis import load_analysis_port; "
            "assert not load_analysis_port(enabled=False).enabled; "
            "assert 'src' not in sys.modules",
        ],
        check=False, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("kind", list(ModelFailureKind))
def test_every_failure_kind_round_trips(kind: ModelFailureKind) -> None:
    assert ModelFailure(kind=kind).kind is kind


def test_model_params_disable_implicit_retries() -> None:
    params = ModelParams()

    assert params.model == "deepseek-flash"
    assert params.max_output_tokens == 1024
    assert params.request_timeout_seconds == 90
    assert params.sdk_max_retries == 0
    assert params.thinking_enabled is False
    assert params.stream is False
    assert params.send_tools is False

    with pytest.raises(Exception):
        ModelParams(sdk_max_retries=3)
