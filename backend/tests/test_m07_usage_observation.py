"""观察脚本只用 Mock 验证；普通 pytest 不发起真实调用。"""

from role_theater.config import Settings
from role_theater.contracts import ActionDraft, ActionType
from role_theater.main import create_app
from role_theater.ports import MockAnalysisPort, MockModelPort
from scripts.observe_usage import main, observe_session, summarize


def test_observation_requires_live_before_loading_settings(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("未开启 live 不应加载凭证配置")
    monkeypatch.setattr("role_theater.config.Settings", forbidden)
    assert main(["--out", str(tmp_path / "unused")]) == 2
    assert not (tmp_path / "unused").exists()


def test_observation_keeps_pass_and_skips_analysis_without_material(tmp_path):
    settings = Settings(_env_file=None, model_provider="mock", model_api_key=None,
                        database_url=f"sqlite:///{tmp_path / 'silent.db'}")
    model = MockModelPort(script=[ActionDraft(action=ActionType.PASS) for _ in range(14)])
    analysis = MockAnalysisPort()
    sample = observe_session(create_app(settings, model_port=model, analysis_port=analysis),
                             "convenience_store", 1, engine="deterministic-mock")
    assert sample["actions"]
    assert all(row["action"] == "PASS" for row in sample["actions"])
    assert sample["timeline"] == [] or all(item["kind"] == "event" for item in sample["timeline"])
    assert sample["analysis"] is None
    assert analysis.call_count == 0
    assert "无公开发言" in sample["analysis_not_run_reason"]
    assert sample["stop"]["run_state"] == "ENDED"
    assert summarize([sample])["speak"] == 0


def test_observation_records_real_counts_and_targeted_visibility(tmp_path):
    settings = Settings(_env_file=None, model_provider="mock", model_api_key=None,
                        database_url=f"sqlite:///{tmp_path / 'active.db'}")
    model = MockModelPort(script=[ActionDraft(action=ActionType.SPEAK, text=f"具体发言 {i}")
                                 for i in range(14)])
    analysis = MockAnalysisPort()
    sample = observe_session(create_app(settings, model_port=model, analysis_port=analysis),
                             "campsite", 1, engine="deterministic-mock")
    assert len(sample["actions"]) == 14
    assert sample["summary"]["role_requests_used"] == 14
    assert sample["targeted_visibility_before_response"] == {"何澜": False, "苏木": True, "涂山": False}
    assert sample["analysis"]["provider_attempts"] == analysis.call_count == 1
    assert sample["analysis"]["agent_name"] == "何澜"
    assert all("latency_ms" in row and "requested_model" in row for row in sample["actions"])
    totals = summarize([sample])
    assert totals["role_provider_requests"] == 14
    assert totals["analysis_provider_requests"] == 1
    assert totals["actual_single_call_over_limit"] == 0


def test_observation_does_not_hide_unknown_delivery_when_sent_is_false():
    sample = {"actions": [{"sent": 0, "status": "UNKNOWN", "action": None,
                           "budget_consumed": 1, "input_tokens": None, "output_tokens": None}],
              "analysis": None}
    totals = summarize([sample])
    assert totals["role_provider_requests"] == 0
    assert totals["role_delivery_unknown"] == totals["role_unknown"] == 1
    assert totals["role_budget_consumed"] == totals["usage_incomplete_records"] == 1
