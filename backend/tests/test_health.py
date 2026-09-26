"""健康检查与契约自检（M00 通过条件：不用密钥可启动健康检查）。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from role_theater.config import Settings
from role_theater.contracts import (
    CONTRACT_ENUMS,
    CONTRACT_LIMIT_CODEPOINTS,
    EXTERNAL_PORTS,
    build_contract_summary,
)
from role_theater.main import create_app


def test_health_ok_without_any_api_key(keyless_client: TestClient) -> None:
    response = keyless_client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app_name"] == "SceneWeave"
    assert body["run_state"] == "READY"
    assert body["model_configured"] is False
    assert body["analysis_enabled"] is False
    assert body["contract_version"]


def test_health_reports_configured_without_leaking_secret(configured_client: TestClient) -> None:
    response = configured_client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["model_configured"] is True
    # 密钥内容绝不出现在响应里。
    assert "placeholder-not-a-real-key" not in response.text


def test_health_does_not_require_external_analysis_package() -> None:
    """分析能力开启时也不得要求外部包已安装（PRD 6.2）。"""

    client = TestClient(create_app(Settings(_env_file=None, analysis_enabled=True)))
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    # M00 尚未接入真实适配层，因此必须显式报告为关闭，而不是假装可用。
    assert body["analysis_enabled"] is False


def test_contracts_summary_covers_every_registered_enum(keyless_client: TestClient) -> None:
    response = keyless_client.get("/api/contracts/summary")

    assert response.status_code == 200
    body = response.json()
    reported = {item["name"]: item["values"] for item in body["enums"]}

    assert set(reported) == set(CONTRACT_ENUMS)
    for name, enum_cls in CONTRACT_ENUMS.items():
        assert reported[name] == [member.value for member in enum_cls]


def test_contracts_summary_limits_and_ports(keyless_client: TestClient) -> None:
    body = keyless_client.get("/api/contracts/summary").json()

    assert body["limit_codepoints"] == CONTRACT_LIMIT_CODEPOINTS
    assert body["agent_count"] == {"min": 2, "max": 8, "default": 3}
    assert body["budgets"] == {
        "max_role_requests_per_scene": 24,
        "max_analysis_requests_per_scene": 4,
    }
    assert body["ports"] == list(EXTERNAL_PORTS)
    assert body["run_states"] == [
        "READY",
        "RUNNING",
        "PAUSING",
        "STOPPING",
        "PAUSED",
        "ENDED",
    ]
    assert body["model_params"]["sdk_max_retries"] == 0
    assert body["model_params"]["model"] == "deepseek-flash"


def test_build_contract_summary_is_pure() -> None:
    assert build_contract_summary() == build_contract_summary()
