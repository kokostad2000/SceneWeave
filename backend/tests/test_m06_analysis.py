"""M06 分析服务与外部适配（PRD 6.1、6.2、5.3；tasks/M06.md A4–A12）。

用**假外部分析器**驱动服务层：不需要外部仓库、不联网，同时可完整验证五状态、
预算、降级识别、受控客户端与隔离性。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from role_theater.analysis import (
    AnalysisService,
    ControlledAnalysisClient,
    ExternalAnalysisPort,
    ExternalAnalysisUnavailable,
    load_external_analyzer,
)
from role_theater.analysis.external import DISCLAIMER
from role_theater.contracts import (
    AnalysisReport,
    AnalysisRequest,
    AnalysisStatus,
    AgentProfileFields,
    RunState,
    Usage,
)
from role_theater.domain import AgentSpec, SceneService, TemplateService
from role_theater.ports import DisabledAnalysisPort
from role_theater.runtime import SceneRunner
from role_theater.storage import (
    AnalysisRepository,
    Database,
    RuntimeRepository,
    SceneRepository,
    TemplateRepository,
)
from role_theater.ports import MockModelPort
from role_theater.contracts import ActionDraft, ActionType, ControlCommandType

CLOCK = datetime(2026, 9, 26, 20, 0, tzinfo=UTC)


class Counter:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.n = 0

    def __call__(self) -> str:
        self.n += 1
        return f"{self.prefix}-{self.n}"


@dataclass
class FakeAnalyzer:
    """假外部分析器：记录收到的请求，返回预设的“结构化响应”。"""

    response: object
    raise_error: Exception | None = None
    delay: float = 0.0

    def __post_init__(self) -> None:
        self.requests: list[AnalysisRequest] = []

    async def analyze(self, request):
        self.requests.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.raise_error is not None:
            raise self.raise_error
        return self.response


@dataclass
class Env:
    scene_id: str
    agent_ids: list[str]
    service: AnalysisService
    repository: AnalysisRepository
    runtime: RuntimeRepository
    scene_repo: SceneRepository
    runner: SceneRunner
    port_holder: dict


def build_env(
    database: Database,
    *,
    port=None,
    analyzer=None,
    analysis_enabled: bool = True,
    max_analysis_requests: int | None = None,
) -> Env:
    template_service = TemplateService(
        TemplateRepository(database), clock=lambda: CLOCK, id_factory=Counter("tpl")
    )
    scene_repository = SceneRepository(database)
    scene_service = SceneService(
        scene_repository,
        template_service,
        clock=lambda: CLOCK,
        scene_id_factory=Counter("scn"),
        agent_id_factory=Counter("agt"),
    )
    runtime = RuntimeRepository(database)
    runner = SceneRunner(
        database=database,
        scenes=scene_repository,
        runtime=runtime,
        model_port=MockModelPort(
            script=[
                ActionDraft(action=ActionType.SPEAK, text="今晚一起吃饭吗？"),
                ActionDraft(action=ActionType.SPEAK, text="我想先休息。"),
            ],
            default_draft=ActionDraft(action=ActionType.PASS),
        ),
        clock=lambda: CLOCK,
        id_factory=Counter("run"),
    )

    if port is None:
        if analyzer is not None:
            port = ExternalAnalysisPort(analyzer=analyzer, client=ControlledAnalysisClient())
        else:
            port = DisabledAnalysisPort(reason="测试中未开启")

    service = AnalysisService(
        scenes=scene_repository,
        runtime=runtime,
        repository=AnalysisRepository(database),
        port_factory=lambda: port,
        snapshot_provider=runner.snapshot,
        clock=lambda: CLOCK,
        id_factory=Counter("ana"),
    )

    specs = []
    for index, name in enumerate(("安然", "许川")):
        template = template_service.create(
            AgentProfileFields(
                name=name,
                persona=f"{name}的人物设定",
                speech_style="简短",
                initial_goal=f"{name}的目标",
                private_background=f"{name}的私有背景",
            )
        )
        specs.append(AgentSpec(template_id=template.template_id))

    detail = scene_service.create(
        title="分析测试场景",
        background="晚上，室友们在客厅。",
        agent_specs=specs,
        max_analysis_requests=max_analysis_requests,
    )
    return Env(
        scene_id=detail.scene.scene_id,
        agent_ids=[agent.agent_id for agent in detail.agents],
        service=service,
        repository=AnalysisRepository(database),
        runtime=runtime,
        scene_repo=scene_repository,
        runner=runner,
        port_holder={"port": port, "analyzer": analyzer},
    )


def good_response(**overrides) -> dict:
    payload = {
        "behavior_labels": ["主动邀请"],
        "mechanisms": ["寻求社会连接"],
        "alternative_explanations": ["只是礼貌寒暄", "想确认今晚的安排"],
        "limitations": ["仅基于公开文本", "无法排除样本偏差"],
        "disclaimer": DISCLAIMER,
        "degradation_flags": [],
    }
    payload.update(overrides)
    return payload


async def prepare_material(env: Env) -> tuple[int, ...]:
    """跑两次单步，得到两条公开发言（seq 1、2）。"""

    await env.runner.run_command(env.scene_id, request_id="s1", command=ControlCommandType.STEP)
    await env.runner.run_command(env.scene_id, request_id="s2", command=ControlCommandType.STEP)
    return (1, 2)


# --- A4 五状态 ----------------------------------------------------------------


async def test_normal_analysis_returns_a_full_report(database: Database) -> None:
    analyzer = FakeAnalyzer(response=good_response())
    env = build_env(database, analyzer=analyzer)
    seqs = await prepare_material(env)

    outcome = await env.service.analyze(env.scene_id, agent_id=env.agent_ids[0], material_seqs=seqs)

    assert outcome.status is AnalysisStatus.NORMAL
    report = outcome.report
    assert report.behavior_labels == ["主动邀请"]
    assert report.mechanisms == ["寻求连接"] or report.mechanisms == ["寻求社会连接"]
    assert len(report.alternative_explanations) >= 2
    assert report.limitations
    assert report.disclaimer
    assert report.degradation_flags == []
    assert report.provider_attempts == 1


async def test_blocked_analysis_records_an_operation_without_provider_attempt(
    database: Database,
) -> None:
    analyzer = FakeAnalyzer(response=good_response())
    env = build_env(database, analyzer=analyzer)
    await prepare_material(env)

    outcome = await env.service.analyze(env.scene_id, agent_id=env.agent_ids[0], material_seqs=())

    assert outcome.status is AnalysisStatus.BLOCKED
    assert outcome.provider_attempts == 0
    assert analyzer.requests == [], "被本地规则拦截时不得调用外部分析"
    assert env.runtime.budget_used(env.scene_id)["analysis_requests_used"] == 0
    # 仍然记录一次分析操作（PRD 5.3）。
    assert env.service.operations_total(env.scene_id) == 1


async def test_disabled_analysis_is_reported_as_disabled(database: Database) -> None:
    env = build_env(database, port=DisabledAnalysisPort(reason="分析能力未开启"))
    seqs = await prepare_material(env)

    outcome = await env.service.analyze(env.scene_id, agent_id=env.agent_ids[0], material_seqs=seqs)

    assert outcome.status is AnalysisStatus.DISABLED
    assert outcome.provider_attempts == 0
    assert "未开启" in (outcome.error or "")


async def test_failed_analysis_is_reported_and_consumes_budget(database: Database) -> None:
    analyzer = FakeAnalyzer(response=None, raise_error=RuntimeError("provider exploded"))
    env = build_env(database, analyzer=analyzer)
    seqs = await prepare_material(env)

    outcome = await env.service.analyze(env.scene_id, agent_id=env.agent_ids[0], material_seqs=seqs)

    assert outcome.status is AnalysisStatus.FAILED
    assert "provider exploded" in (outcome.error or "")
    assert env.runtime.budget_used(env.scene_id)["analysis_requests_used"] == 1, "失败不退款"


# --- A5 降级识别 --------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"degradation_flags": ["provider_exception_swallowed"]},
        {"behavior_labels": []},
        {"alternative_explanations": ["只有一个解释"]},
        {"degraded": True},
    ],
)
async def test_swallowed_provider_problems_are_never_reported_as_normal(
    database: Database, payload: dict
) -> None:
    analyzer = FakeAnalyzer(response=good_response(**payload))
    env = build_env(database, analyzer=analyzer)
    seqs = await prepare_material(env)

    outcome = await env.service.analyze(env.scene_id, agent_id=env.agent_ids[0], material_seqs=seqs)

    assert outcome.status is AnalysisStatus.DEGRADED
    assert outcome.report.degradation_flags, "必须保留降级标记"


async def test_degraded_report_always_keeps_two_alternatives_and_disclaimer(
    database: Database,
) -> None:
    analyzer = FakeAnalyzer(response={"behavior_labels": ["某标签"], "degradation_flags": ["x"]})
    env = build_env(database, analyzer=analyzer)
    seqs = await prepare_material(env)

    outcome = await env.service.analyze(env.scene_id, agent_id=env.agent_ids[0], material_seqs=seqs)

    assert outcome.status is AnalysisStatus.DEGRADED
    assert len(outcome.report.alternative_explanations) >= 2
    assert outcome.report.disclaimer


# --- A6 强制 persist_profile=false -------------------------------------------


async def test_persist_profile_is_forced_off(database: Database) -> None:
    analyzer = FakeAnalyzer(response=good_response())
    env = build_env(database, analyzer=analyzer)
    seqs = await prepare_material(env)

    await env.service.analyze(env.scene_id, agent_id=env.agent_ids[0], material_seqs=seqs)

    assert analyzer.requests, "应当发生一次调用"
    assert analyzer.requests[0].persist_profile is False


def test_analysis_request_contract_rejects_persist_profile_true() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AnalysisRequest(
            scene_id="scn-1",
            agent_id="agt-1",
            behavior_description="描述",
            persist_profile=True,
        )


# --- A8 外部包缺失 ------------------------------------------------------------


def test_external_package_missing_is_reported_not_crashed() -> None:
    def failing_importer(name: str):
        raise ModuleNotFoundError(f"No module named '{name}'")

    with pytest.raises(ExternalAnalysisUnavailable) as excinfo:
        load_external_analyzer(importer=failing_importer)

    assert "No module named" in str(excinfo.value)


def test_load_analysis_port_disabled_does_not_need_the_external_package() -> None:
    from role_theater.ports import load_analysis_port

    port = load_analysis_port(enabled=False)

    assert port.enabled is False
    assert "未开启" in port.capability.reason


def test_load_analysis_port_enabled_without_package_gives_a_concrete_reason() -> None:
    from role_theater.ports import load_analysis_port

    port = load_analysis_port(enabled=True)

    # 本环境未安装外部仓库：必须明确不可用，且原因可读。
    assert port.enabled is False
    assert "外部分析仓库不可用" in port.capability.reason
    assert "src" in port.capability.reason


# --- A9 预算 ------------------------------------------------------------------


async def test_analysis_budget_is_independent_and_exhaustible(database: Database) -> None:
    analyzer = FakeAnalyzer(response=good_response())
    env = build_env(database, analyzer=analyzer, max_analysis_requests=2)
    seqs = await prepare_material(env)

    first = await env.service.analyze(env.scene_id, agent_id=env.agent_ids[0], material_seqs=seqs)
    second = await env.service.analyze(env.scene_id, agent_id=env.agent_ids[0], material_seqs=seqs)
    third = await env.service.analyze(env.scene_id, agent_id=env.agent_ids[0], material_seqs=seqs)

    assert first.status is AnalysisStatus.NORMAL
    assert second.status is AnalysisStatus.NORMAL
    assert third.status is AnalysisStatus.BLOCKED
    assert "已用尽" in (third.error or "")
    assert third.provider_attempts == 0
    assert len(analyzer.requests) == 2, "预算耗尽后不得再调用"
    # 角色请求预算不受影响（独立计数）。
    assert env.runtime.budget_used(env.scene_id)["role_requests_used"] == 2


async def test_analysis_is_allowed_after_the_scene_ended(database: Database) -> None:
    analyzer = FakeAnalyzer(response=good_response())
    env = build_env(database, analyzer=analyzer)
    seqs = await prepare_material(env)
    await env.runner.run_command(env.scene_id, request_id="stop", command=ControlCommandType.STOP)

    outcome = await env.service.analyze(env.scene_id, agent_id=env.agent_ids[0], material_seqs=seqs)

    assert outcome.status is AnalysisStatus.NORMAL, "已结束的场景仍可分析（沿用本场预算）"


# --- A10 记录隔离与无画像 -----------------------------------------------------


async def test_records_are_isolated_by_scene_and_agent(database: Database) -> None:
    analyzer = FakeAnalyzer(response=good_response())
    env = build_env(database, analyzer=analyzer)
    seqs = await prepare_material(env)

    await env.service.analyze(env.scene_id, agent_id=env.agent_ids[0], material_seqs=seqs)
    await env.service.analyze(env.scene_id, agent_id=env.agent_ids[1], material_seqs=seqs)

    first_agent = env.service.list_records(env.scene_id, agent_id=env.agent_ids[0])
    second_agent = env.service.list_records(env.scene_id, agent_id=env.agent_ids[1])

    assert len(first_agent) == 1
    assert len(second_agent) == 1
    assert first_agent[0]["agent_id"] != second_agent[0]["agent_id"]
    assert first_agent[0]["materials"], "记录必须保留送出的材料原文"


def test_there_is_no_profile_table_in_the_schema(database: Database) -> None:
    """无画像写入：schema 里不存在画像表（PRD 6.2）。"""

    with database.connection() as conn:
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }

    assert "analysis_records" in tables
    assert not any("profile" in name for name in tables), tables


# --- A11 受控客户端 -----------------------------------------------------------


def test_controlled_client_closes_implicit_retries_and_tracks_usage() -> None:
    attempts = {"n": 0}

    def transport(payload: dict) -> dict:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("first attempt fails")
        return {"usage": {"prompt_tokens": 11, "completion_tokens": 5}}

    client = ControlledAnalysisClient(transport=transport)

    with pytest.raises(RuntimeError):
        client.create_completion(prompt="hello")

    assert client.provider_attempts == 1, "失败不得自动重试"
    assert client.attempts[0].ok is False
    assert client.usage.is_unknown, "失败尝试的用量记为 unknown 而不是 0"

    client.create_completion(prompt="hello")
    assert attempts["n"] == 2
    assert client.usage.input_tokens == 11
    assert client.usage.output_tokens == 5


def test_controlled_client_explicit_api_behaviour() -> None:
    client = ControlledAnalysisClient()
    payload = client.build_request(prompt="材料")

    assert payload["stream"] is False
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["thinking"] == {"type": "disabled"}
    assert "tools" not in payload
    assert "temperature" not in payload
    assert client.settings["sdk_max_retries"] == 0


def test_controlled_client_requires_a_transport() -> None:
    client = ControlledAnalysisClient()

    with pytest.raises(RuntimeError):
        client.create_completion(prompt="x")

    assert client.provider_attempts == 1, "尝试本身也要被记录"


def test_controlled_client_refuses_implicit_retries_config() -> None:
    with pytest.raises(ValueError):
        ControlledAnalysisClient(sdk_max_retries=3)


# --- A12 不影响剧情与运行状态 -------------------------------------------------


async def test_analysis_does_not_change_the_scene_or_the_role_context(database: Database) -> None:
    analyzer = FakeAnalyzer(response=good_response())
    env = build_env(database, analyzer=analyzer)
    seqs = await prepare_material(env)

    before_scene = env.scene_repo.get_scene(env.scene_id)
    before_viewpoint = env.runner.viewpoint(env.scene_id, env.agent_ids[0])[1]
    before_messages = len(env.runtime.list_messages(env.scene_id))

    await env.service.analyze(env.scene_id, agent_id=env.agent_ids[0], material_seqs=seqs)

    after_scene = env.scene_repo.get_scene(env.scene_id)
    after_viewpoint = env.runner.viewpoint(env.scene_id, env.agent_ids[0])[1]

    assert after_scene == before_scene, "分析不得改变运行状态"
    assert after_viewpoint == before_viewpoint, "分析结果不得进入角色上下文"
    assert len(env.runtime.list_messages(env.scene_id)) == before_messages
    # 也不消耗角色请求预算。
    assert env.runtime.budget_used(env.scene_id)["role_requests_used"] == 2


async def test_analysis_failure_does_not_break_chatting(database: Database) -> None:
    analyzer = FakeAnalyzer(response=None, raise_error=RuntimeError("boom"))
    env = build_env(database, analyzer=analyzer)
    seqs = await prepare_material(env)

    failed = await env.service.analyze(env.scene_id, agent_id=env.agent_ids[0], material_seqs=seqs)
    assert failed.status is AnalysisStatus.FAILED

    # 失败之后仍可继续运行场景。
    ack = await env.runner.run_command(
        env.scene_id, request_id="after-failure", command=ControlCommandType.STEP
    )
    assert ack.accepted is True
    scene = env.scene_repo.get_scene(env.scene_id)
    assert scene is not None and scene.status is RunState.PAUSED


async def test_external_port_maps_a_normal_response_directly() -> None:
    analyzer = FakeAnalyzer(response=good_response())
    port = ExternalAnalysisPort(analyzer=analyzer)

    report = await port.analyze(
        AnalysisRequest(scene_id="scn-1", agent_id="agt-1", behavior_description="描述")
    )

    assert isinstance(report, AnalysisReport)
    assert report.status is AnalysisStatus.NORMAL
    assert report.usage is not None


async def test_external_port_reports_usage_from_the_controlled_client() -> None:
    class RecordingAnalyzer:
        async def analyze(self, request):
            request_client.create_completion(prompt="材料") if hasattr(request, "x") else None
            return good_response()

    client = ControlledAnalysisClient(
        transport=lambda payload: {"usage": {"prompt_tokens": 7, "completion_tokens": 3}}
    )
    client.create_completion(prompt="材料")
    port = ExternalAnalysisPort(analyzer=RecordingAnalyzer(), client=client)

    report = await port.analyze(
        AnalysisRequest(scene_id="scn-1", agent_id="agt-1", behavior_description="描述")
    )

    assert report.usage.input_tokens == 7
    assert report.usage.output_tokens == 3
    assert isinstance(report.usage, Usage)
