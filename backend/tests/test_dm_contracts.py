"""P1 契约：兼容入站、模式配置和 Unicode 边界。"""
import pytest
from pydantic import ValidationError

from role_theater.contracts import (
    SceneCreateRequest, AgentProfileFields, DiscussionParticipantConfig,
    SimulationConfig, DiscussionConfig, SceneMode,
)


def payload(mode="simulation", count=3):
    return dict(title="模式测试", mode=mode,
                mode_config=({"situation": "场景", "public_information": "资料"}
                             if mode == "simulation" else {"topic": "议题", "materials": "资料"}),
                agents=[{"template_id": f"tpl_{i}"} for i in range(count)])


@pytest.mark.parametrize("mode", list(SceneMode))
@pytest.mark.parametrize("count", [2, 3, 5, 8])
def test_valid_modes_and_counts(mode, count):
    req = SceneCreateRequest(**payload(mode, count))
    assert req.mode == mode
    assert len(req.agents) == count
    assert req.background == req.mode_config.background_text()


@pytest.mark.parametrize("mode", list(SceneMode))
@pytest.mark.parametrize("count", [1, 9])
def test_invalid_counts(mode, count):
    with pytest.raises(ValidationError):
        SceneCreateRequest(**payload(mode, count))


@pytest.mark.parametrize("change", [
    {"mode": "unknown"}, {"mode": "discussion", "mode_config": None},
    {"mode": "discussion", "mode_config": {"topic": "  "}},
    {"mode_config": {"topic": "跨模式"}},
    {"mode": "discussion", "mode_config": {"situation": "跨模式"}},
    {"mode_config": {"situation": "x", "extra": True}},
    {"background": "矛盾"},
    {"agents": [{"template_id": "tpl_a", "discussion_config": {}}, {"template_id": "tpl_b"}]},
])
def test_invalid_mode_config(change):
    with pytest.raises(ValidationError):
        SceneCreateRequest(**(payload() | change))


def test_legacy_defaults_and_empty_position():
    req = SceneCreateRequest(title="旧调用", background="  背景  ", agents=payload()["agents"])
    assert req.mode is SceneMode.SIMULATION
    assert req.mode_config == SimulationConfig(situation="背景")
    for position in [None, "", "  "]:
        assert DiscussionParticipantConfig(initial_position=position).initial_position is None
    assert DiscussionParticipantConfig(initial_position="  可调整想法  ").initial_position == "可调整想法"


@pytest.mark.parametrize("cls,field,limit", [
    (SimulationConfig, "situation", 2000), (SimulationConfig, "public_information", 2000),
    (DiscussionConfig, "topic", 2000), (DiscussionConfig, "materials", 1998),
    (DiscussionParticipantConfig, "focus", 500), (DiscussionParticipantConfig, "initial_position", 1000),
])
def test_codepoint_limits(cls, field, limit):
    base = {"topic": "题"} if cls is DiscussionConfig and field != "topic" else {}
    assert cls(**(base | {field: " " + "😀" * limit + " "}))
    with pytest.raises(ValidationError):
        cls(**(base | {field: "😀" * (limit + 1)}))


def test_combined_background_and_public_profile():
    for cls, data in [(SimulationConfig, {"situation": "😀" * 1000, "public_information": "x" * 1000}),
                      (DiscussionConfig, {"topic": "😀" * 1000, "materials": "x" * 1000})]:
        with pytest.raises(ValidationError):
            cls(**data)
    base = dict(name="人", persona="PRIVATE", speech_style="", initial_goal="", private_background="")
    assert AgentProfileFields(**base).public_profile == ""
    assert AgentProfileFields(**base, public_profile="  " + "😀" * 1000 + "  ").public_profile == "😀" * 1000
    with pytest.raises(ValidationError):
        AgentProfileFields(**base, public_profile="😀" * 1001)
