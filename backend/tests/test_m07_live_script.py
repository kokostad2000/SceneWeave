"""The paid acceptance driver is exercised with a deterministic port only."""

from __future__ import annotations

import asyncio
from argparse import Namespace

from scripts.live_integration import (
    _acceptance_met, _drive, _drive_quality, _preflight, _quality_sample_met,
)
from role_theater.config import Settings
from role_theater.contracts import ActionDraft, ActionType
from role_theater.main import create_app
from role_theater.ports import MockModelPort


def test_live_driver_requires_live_switch_and_a_real_provider() -> None:
    keyless = Settings(_env_file=None, model_api_key=None, model_provider="mock")
    assert _preflight(Namespace(live=False), keyless) == 2
    assert _preflight(Namespace(live=True), keyless) == 3
    configured = Settings(
        _env_file=None, model_api_key="placeholder-not-real", model_provider="deepseek",
    )
    assert _preflight(Namespace(live=True), configured) is None


def test_offline_driver_checks_target_processed_the_event(tmp_path) -> None:
    settings = Settings(
        _env_file=None, model_api_key=None, model_provider="mock",
        database_url=f"sqlite:///{tmp_path / 'live-driver.db'}",
    )
    model = MockModelPort(
        script=[ActionDraft(action=ActionType.SPEAK, text=f"第 {n} 次发言。") for n in range(9)]
    )
    record = asyncio.run(_drive(
        create_app(settings, model_port=model), 3,
        after_event_turns=6, engine="deterministic-mock",
    ))

    assert record["event"]["status"] == "EFFECTIVE"
    assert record["targeted_event_visibility"]["许川"] is True
    assert all(
        not seen for name, seen in record["targeted_event_visibility"].items()
        if name != "许川"
    )
    assert any(step["target_processed_event"] for step in record["after_event_steps"])
    assert record["event"]["body"].find("水管漏水") >= 0
    assert record["target_post_event_messages"]
    assert _acceptance_met(record, initial_turns=3, with_analysis=False) is True
    # A visible event alone is insufficient: the target must process its seq.
    for step in record["after_event_steps"]:
        step["target_processed_event"] = False
    assert _acceptance_met(record, initial_turns=3, with_analysis=False) is False


def test_quality_sample_uses_only_three_mock_role_requests(tmp_path) -> None:
    settings = Settings(
        _env_file=None, model_api_key=None, model_provider="mock",
        database_url=f"sqlite:///{tmp_path / 'quality.db'}",
    )
    model = MockModelPort(
        script=[ActionDraft(action=ActionType.SPEAK, text=f"样本发言 {n}。") for n in range(3)]
    )
    record = asyncio.run(_drive_quality(
        create_app(settings, model_port=model), preset_key="campsite", turns=3,
    ))

    assert record["preset_key"] == "campsite"
    assert record["summary"]["role_requests_used"] == 3
    assert _quality_sample_met(record) is True
    assert [action["action"] for action in record["actions"]] == ["SPEAK"] * 3
    assert "event" not in record
    assert "analysis" not in record


def test_quality_sample_accepts_pass_as_valid_silence(tmp_path) -> None:
    settings = Settings(
        _env_file=None, model_api_key=None, model_provider="mock",
        database_url=f"sqlite:///{tmp_path / 'quality-pass.db'}",
    )
    model = MockModelPort(script=[
        ActionDraft(action=ActionType.PASS, text=""),
        ActionDraft(action=ActionType.PASS, text=""),
        ActionDraft(action=ActionType.SPEAK, text="现在轮到我说话。"),
    ])
    record = asyncio.run(_drive_quality(
        create_app(settings, model_port=model), preset_key="convenience_store", turns=3,
    ))

    assert record["summary"]["succeeded"] == 3
    assert [action["action"] for action in record["actions"]] == ["PASS", "PASS", "SPEAK"]
    assert _quality_sample_met(record) is True
