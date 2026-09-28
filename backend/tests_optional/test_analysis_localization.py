"""取证脚本通过锁定上游与假 SDK 处理异常响应，不调用真实供应商。"""

from __future__ import annotations

import argparse
import json

import pytest

from scripts import analysis_localization as localization


@pytest.fixture
def inject_contents(monkeypatch):
    original = localization.SimpleNamespace
    contents = {}
    # 失败复现时也不留下测试临时路径的进程退出回调。
    callbacks = []
    monkeypatch.setattr(localization.atexit, "register", callbacks.append)
    monkeypatch.setattr(localization.atexit, "unregister", lambda callback: callbacks.remove(callback))

    def namespace(**kwargs):
        if kwargs.get("id") == "fake-localization":
            current = capture.current["id"]
            if current in contents:
                kwargs["choices"][0].message.content = contents[current]
        return original(**kwargs)

    original_capture = localization.Capture
    capture = None

    def capture_factory(*args, **kwargs):
        nonlocal capture
        capture = original_capture(*args, **kwargs)
        return capture

    monkeypatch.setattr(localization, "SimpleNamespace", namespace)
    monkeypatch.setattr(localization, "Capture", capture_factory)
    return contents


def run_harness(tmp_path, cases):
    output = tmp_path / "localization.json"
    code = localization.run(argparse.Namespace(live=False, cases=cases, output=output))
    return code, json.loads(output.read_text())


def test_malformed_tags_preserve_evidence_and_complete_all_cases(tmp_path, inject_contents):
    contents = {
        "L1": '["unexpected"]',
        "L2": '{"tags": null}',
        "L3": '{"tags": "repeated_apology"}',
        "L4": '{"tags": ["repeated_apology", 1]}',
    }
    inject_contents.update(contents)
    code, record = run_harness(tmp_path, [case["id"] for case in localization.CASES])

    assert code == 1
    assert record["completed_at"]
    assert record["engineering_passed"] is False
    assert record["provider_attempts"] == 6
    assert [case["id"] for case in record["cases"]] == ["L1", "L2", "L3", "L4", "L5", "L6"]
    for case in record["cases"]:
        assert case["project_api"]["status"] == "DEGRADED"
        assert case["engineering_checks"]
        assert case["usage"] == {"input_tokens": 100, "output_tokens": 50, "cached_tokens": 0}
        assert case["engineering_checks"]["scene_state_timeline_all_viewpoints_unchanged"]
        assert case["engineering_checks"]["api_record_persisted"]
        failed = [key for key, value in case["engineering_checks"].items() if not value]
        if case["id"] in contents:
            assert failed == ["raw_model_tag_structure_valid"]
            assert case["tag_trace"]["raw_structure_error"]
            assert case["tag_trace"]["removed_by_normalization"] is None
            assert case["raw_model"]["content"] == contents[case["id"]]
            assert case["raw_model"]["parsed_content"] == json.loads(contents[case["id"]])
            assert "llm_invalid_output" in case["normalized_upstream"]["degradation_flags"]
        else:
            assert failed == []
            assert case["tag_trace"]["raw"] == []


@pytest.mark.parametrize("content", ["", "not JSON"])
def test_invalid_json_is_recorded_with_nonzero_exit(tmp_path, inject_contents, content):
    inject_contents["L1"] = content
    code, record = run_harness(tmp_path, ["L1"])
    case = record["cases"][0]

    assert code == 1
    assert record["completed_at"]
    assert record["provider_attempts"] == 1
    assert case["raw_model"]["content"] == content
    assert case["raw_model"]["parsed_content"] is None
    assert case["tag_trace"]["raw_structure_error"] == "invalid_json"
    assert case["engineering_checks"]["raw_model_tag_structure_valid"] is False
    assert case["project_api"]["status"] == "DEGRADED"
    assert case["engineering_checks"]["correct_status_mapping"]


def test_normal_fake_suite_still_passes(tmp_path, inject_contents):
    code, record = run_harness(tmp_path, [case["id"] for case in localization.CASES])

    assert code == 0
    assert record["engineering_passed"] is True
    assert record["provider_attempts"] == 6
    assert all(all(case["engineering_checks"].values()) for case in record["cases"])
    assert all(case["tag_trace"]["raw_structure_error"] is None for case in record["cases"])
