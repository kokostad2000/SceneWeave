"""原始取证类型校验不需要上游包，非法字段不能伪装为正常空标签。"""

from copy import deepcopy

import pytest

from scripts.analysis_localization import build_tag_trace


@pytest.mark.parametrize("parsed,error", [
    (["unexpected"], "expected_json_object"),
    ([], "expected_json_object"),
    ("unexpected", "expected_json_object"),
    (0, "expected_json_object"),
    (False, "expected_json_object"),
    (None, "expected_json_object"),
    ({}, "expected_tags_list"),
    ({"tags": None}, "expected_tags_list"),
    ({"tags": "repeated_apology"}, "expected_tags_list"),
    ({"tags": {"name": "repeated_apology"}}, "expected_tags_list"),
    ({"tags": ["repeated_apology", 1]}, "expected_string_tags"),
    ({"tags": [["repeated_apology"]]}, "expected_string_tags"),
])
def test_invalid_raw_structure_is_explicit_and_cannot_be_compared(parsed, error):
    raw_model = {"parsed_content": parsed}
    original = deepcopy(raw_model)
    trace = build_tag_trace(raw_model, ["repeated_apology"], ["repeated_apology"])

    assert trace["raw_structure_error"] == error
    assert trace["removed_by_normalization"] is None
    assert trace["raw"] == (parsed.get("tags") if isinstance(parsed, dict) else None)
    assert trace["normalized"] == trace["final"] == ["repeated_apology"]
    assert raw_model == original


@pytest.mark.parametrize("tags,removed", [
    ([], []),
    (["repeated_apology", "unknown_tag"], ["unknown_tag"]),
])
def test_valid_tags_include_empty_lists_and_preserve_normalization_trace(tags, removed):
    trace = build_tag_trace({"parsed_content": {"tags": tags}}, ["repeated_apology"], [])

    assert trace["raw_structure_error"] is None
    assert trace["raw"] == tags
    assert trace["removed_by_normalization"] == removed
    assert trace["final"] == []


def test_json_parse_failure_remains_distinct_from_json_null():
    trace = build_tag_trace(
        {"content": "not JSON", "parsed_content": None, "content_parse_error": "invalid_json"},
        [], [],
    )

    assert trace["raw_structure_error"] == "invalid_json"
    assert trace["removed_by_normalization"] is None


def test_absent_upstream_tags_does_not_claim_all_raw_tags_were_removed():
    trace = build_tag_trace({"parsed_content": {"tags": ["repeated_apology"]}}, None, [])

    assert trace["raw_structure_error"] is None
    assert trace["normalized"] is None
    assert trace["removed_by_normalization"] is None
