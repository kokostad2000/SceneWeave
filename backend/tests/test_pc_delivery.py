import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from private_chat_acceptance import drive
from private_chat_capacity import measure
import private_chat_acceptance as acceptance


def test_pc_mock_delivery_preserves_actual_requests(tmp_path):
    record=drive(tmp_path/"sample",live=False,turns=6)
    assert record["engine"] == "mock" and record["sample_covered"]
    assert record["reply_count"]==1
    assert all(t["request_snapshot_json"] for t in record["requests"])
    assert all(t["input_tokens"] is None for t in record["requests"])
    assert all(c["original_text_absent"] and c["original_id_absent"]
        for c in record["third_party_actual_request_checks"])
    with pytest.raises(RuntimeError,match="已存在"): drive(tmp_path/"sample",live=False,turns=6)


def test_pc_live_missing_configuration_never_falls_back(tmp_path,monkeypatch):
    from role_theater import config
    original=config.Settings
    def absent_settings(**kwargs): return original(**{**kwargs,"_env_file":None,"model_api_key":None})
    monkeypatch.setattr(config,"Settings",absent_settings)
    with pytest.raises(RuntimeError,match="model_configured=false"): drive(tmp_path/"live",live=True,turns=3)
    assert not (tmp_path/"live/sample.db").exists()
    assert acceptance.main(["--live", "--turns", "3", "--output", str(tmp_path / "live-cli")]) == 3
    assert not list((tmp_path / "live-cli").glob("*/sample.db"))


def test_pc_capacity_is_mock_only_with_all_pairs():
    results=measure()
    assert [(r["roles"],r["conversations"]) for r in results]==[(2,1),(3,3),(5,10),(8,28)]
    assert all(r["engine"]=="Mock" for r in results)
    assert all(max(r["prompt_codepoints"])<=32000 for r in results)


@pytest.mark.parametrize("kind,status", [
    ("TIMEOUT", "FAILED"),
    ("PROVIDER_ERROR", "FAILED"),
    ("UNKNOWN_REQUEST", "UNKNOWN"),
])
def test_pc_acceptance_late_failure_exits_nonzero_after_coverage(tmp_path, monkeypatch, capsys, kind, status):
    from role_theater.contracts import ActionDraft, ModelFailure
    from role_theater.ports import MockModelPort

    original = MockModelPort.generate_action

    async def late_failure(port, request):
        if port.call_count == 2:
            # 第三次公开发言产生新信息，使第四次请求有资格发送。
            port._script = [ActionDraft(action="SPEAK", text="大家明天再商量。")]
        elif port.call_count == 3:
            port._script = [ModelFailure(kind=kind, detail="可控第四次失败")]
        return await original(port, request)

    monkeypatch.setattr(MockModelPort, "generate_action", late_failure)
    output = tmp_path / "late-failure"
    exit_code = acceptance.main(["--turns", "8", "--output", str(output)])
    record = json.loads(next(output.glob("*/evidence.json")).read_text())
    assert record["sample_covered"] is True
    assert len(record["requests"]) == len(record["steps"]) == 4
    assert [request["status"] for request in record["requests"]] == ["SUCCEEDED"] * 3 + [status]
    assert record["requests"][-1]["failure_kind"] == kind
    assert exit_code == 4
    assert record["acceptance_passed"] is False
    assert record["request_status_counts"] == {"SUCCEEDED": 3, status: 1}
    assert json.loads(capsys.readouterr().out)["acceptance_passed"] is False


@pytest.mark.parametrize("turns,stop_state,stop_reason", [
    (4, "PAUSED", "MANUAL"),
    (8, "PAUSED", "NO_NEW_INFORMATION"),
])
def test_pc_acceptance_normal_stop_exits_zero(tmp_path, capsys, turns, stop_state, stop_reason):
    output = tmp_path / "success"
    assert acceptance.main(["--turns", str(turns), "--output", str(output)]) == 0
    record = json.loads(next(output.glob("*/evidence.json")).read_text())
    assert record["sample_covered"] is True
    assert record["steps"][-1]["run_state"] == stop_state
    assert record["steps"][-1]["pause_reason"] == stop_reason
    assert record["acceptance_passed"] is True
    assert record["request_status_counts"] == {"SUCCEEDED": len(record["requests"])}
    assert json.loads(capsys.readouterr().out)["acceptance_passed"] is True


@pytest.mark.parametrize("override", [
    {"requests": [{"status": "PENDING"}]},
    {"requests": []},
    {"requests": [{}]},
    {"requests": [{"status": "SUCCEEDED", "failure_kind": "TIMEOUT"}]},
    {"steps": []},
    {"steps": [{"accepted": False, "pause_reason": None}]},
    {"steps": [{"accepted": True, "pause_reason": "CONTEXT_LIMIT"}]},
    {"steps": [{"accepted": True, "pause_reason": "PROVIDER_ERROR"}]},
    {"steps": [{"accepted": True, "pause_reason": "PROCESS_INTERRUPT"}]},
    {"sample_covered": False},
])
def test_pc_acceptance_rejects_incomplete_or_failed_evidence(override):
    record = {
        "sample_covered": True,
        "requests": [{"status": "SUCCEEDED", "failure_kind": None}],
        "steps": [{"accepted": True, "pause_reason": None}],
    }
    assert acceptance._acceptance_met(record) is True
    record.update(override)
    assert acceptance._acceptance_met(record) is False
