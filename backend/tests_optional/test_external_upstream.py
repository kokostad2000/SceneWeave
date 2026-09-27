"""Explicit optional acceptance against behavior-psychology at the locked commit.

Run with ``uv sync --extra analysis --dev`` then
``.venv/bin/python -m pytest tests_optional/test_external_upstream.py``.
The SDK is replaced with a deterministic in-process fake; no provider call occurs.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from role_theater.analysis.external import UpstreamCompletionClient, build_upstream_port
from role_theater.config import Settings
from role_theater.contracts import ActionDraft, ActionType, AnalysisRequest, AnalysisStatus
from role_theater.main import create_app
from role_theater.ports import MockModelPort


class FakeCompletionSDK:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=self)
        self.closed = False

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        content = json.dumps(
            {
                "tags": ["conversation_interruption"],
                "mechanisms": [
                    {"name": "situational_stress", "explanation": "当时可能有时间压力", "confidence": 0.3}
                ],
                "alternative_explanations": [
                    {"perspective": "节奏", "reasoning": "双方的轮流发言习惯可能不同"},
                    {"perspective": "环境", "reasoning": "现场噪声可能影响判断"},
                ],
                "confidence": 0.3,
                "universality_rating": "中",
            },
            ensure_ascii=False,
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(prompt_tokens=23, completion_tokens=17,
                                  prompt_tokens_details=SimpleNamespace(cached_tokens=2)),
        )

    async def close(self) -> None:
        self.closed = True


async def test_sdk_is_created_with_no_implicit_retry(monkeypatch) -> None:
    import openai

    captured = {}
    fake = FakeCompletionSDK()

    def factory(**kwargs):
        captured.update(kwargs)
        return fake

    monkeypatch.setattr(openai, "AsyncOpenAI", factory)
    client = UpstreamCompletionClient(
        provider="deepseek", api_key="placeholder-not-real",
        base_url="https://example.invalid",
    )
    await client.create(
        model="deepseek-flash", messages=[{"role": "user", "content": "测试"}],
        max_tokens=1400,
    )
    await client.close()

    assert captured["max_retries"] == 0
    assert captured["timeout"] == 90.0
    assert len(fake.calls) == 1
    assert fake.calls[0]["extra_body"] == {"thinking": {"type": "disabled"}}
    assert fake.closed is True


async def test_analysis_sdk_rejects_single_call_limit_before_send() -> None:
    from role_theater.ports.token_limit import SingleCallTokenLimitExceeded

    client = UpstreamCompletionClient(
        provider="deepseek", api_key="placeholder-not-real",
        base_url="https://example.invalid",
    )
    fake = FakeCompletionSDK()
    client._sdk = fake

    with pytest.raises(SingleCallTokenLimitExceeded):
        await client.create(
            model="deepseek-flash", messages=[{"role": "user", "content": "测试"}],
            max_tokens=10_000_000,
        )
    assert fake.calls == []
    assert client.provider_attempts == 0


async def test_analysis_sdk_flags_reported_token_overrun() -> None:
    from role_theater.ports.token_limit import SingleCallTokenLimitExceeded

    class ExcessiveUsageSDK(FakeCompletionSDK):
        async def create(self, **kwargs):
            response = await super().create(**kwargs)
            response.usage.prompt_tokens = 9_999_999
            response.usage.completion_tokens = 2
            return response

    client = UpstreamCompletionClient(
        provider="deepseek", api_key="placeholder-not-real",
        base_url="https://example.invalid",
    )
    fake = ExcessiveUsageSDK()
    client._sdk = fake

    with pytest.raises(SingleCallTokenLimitExceeded):
        await client.create(
            model="deepseek-flash", messages=[{"role": "user", "content": "测试"}],
            max_tokens=1400,
        )
    assert len(fake.calls) == 1
    assert client.provider_attempts == 1
    assert client.usage.input_tokens == 9_999_999
    assert client.usage.output_tokens == 2


def test_optional_analysis_configuration_matrix() -> None:
    for absent in (None, "", "   "):
        settings = Settings(
            _env_file=None, model_provider="deepseek",
            model_api_key=absent, analysis_enabled=True,
        )
        assert settings.analysis_capability.enabled is False
        assert settings.analysis_capability.external_package_installed is True
    configured = Settings(
        _env_file=None, model_provider="deepseek",
        model_api_key="placeholder-not-real", analysis_enabled=True,
    )
    assert configured.analysis_capability.enabled is True
    assert configured.analysis_capability.external_package_installed is True


async def test_pinned_upstream_contract_and_controlled_request() -> None:
    port = build_upstream_port(
        provider="deepseek", api_key="placeholder-not-real",
        base_url="https://example.invalid", model="deepseek-flash",
    )
    fake = FakeCompletionSDK()
    port.client._sdk = fake
    observed = {}
    original_analyze = port._analyzer.analyze

    async def capture_request(request):
        observed["persist_profile"] = request.persist_profile
        observed["subject_id"] = request.subject_id
        return await original_analyze(request)

    port._analyzer.analyze = capture_request

    report = await port.analyze(
        AnalysisRequest(
            scene_id="scn-1", agent_id="agt-1",
            behavior_description="[#1] 安然（发言）：你刚才打断我说话了。",
            context="[#2] 许川（发言）：抱歉，我担心时间不够。",
        )
    )

    assert report.status is AnalysisStatus.NORMAL
    assert observed == {"persist_profile": False, "subject_id": None}
    assert report.behavior_labels == ["conversation_interruption"]
    assert report.mechanisms and "situational_stress" in report.mechanisms[0]
    assert len(report.alternative_explanations) >= 2
    assert report.provider_attempts == 1
    assert report.usage.input_tokens == 23
    assert report.usage.output_tokens == 17
    assert fake.closed is True
    assert len(fake.calls) == 1
    request = fake.calls[0]
    assert request["extra_body"] == {"thinking": {"type": "disabled"}}
    assert request["stream"] is False
    assert "tools" not in request
    assert "api_key" not in request
    assert port._analyzer.config.max_retries == 0


async def test_upstream_block_does_not_call_provider() -> None:
    port = build_upstream_port(
        provider="deepseek", api_key="placeholder-not-real",
        base_url="https://example.invalid", model="deepseek-flash",
    )
    fake = FakeCompletionSDK()
    port.client._sdk = fake

    report = await port.analyze(
        AnalysisRequest(
            scene_id="scn-1", agent_id="agt-1",
            behavior_description="[#1] 安然（发言）：我想自残。",
        )
    )

    assert report.status is AnalysisStatus.BLOCKED
    assert report.provider_attempts == 0
    assert fake.calls == []
    assert fake.closed is True


def test_full_app_uses_pinned_upstream_without_changing_scene(tmp_path) -> None:
    port = build_upstream_port(
        provider="deepseek", api_key="placeholder-not-real",
        base_url="https://example.invalid", model="deepseek-flash",
    )
    fake = FakeCompletionSDK()
    port.client._sdk = fake
    settings = Settings(
        _env_file=None, model_provider="deepseek",
        model_api_key="placeholder-not-real", analysis_enabled=True,
        database_url=f"sqlite:///{tmp_path / 'optional-app.db'}",
    )
    model = MockModelPort(script=[
        ActionDraft(action=ActionType.SPEAK, text="你刚才打断我了。"),
        ActionDraft(action=ActionType.SPEAK, text="抱歉，我担心时间不够。"),
    ])
    with TestClient(create_app(settings, model_port=model, analysis_port=port)) as api:
        detail = api.post("/api/scenes/preset", json={"preset_key": "roommates"}).json()
        scene_id = detail["scene"]["scene_id"]
        agent_id = detail["agents"][0]["agent_id"]
        for n in range(2):
            ack = api.post(
                f"/api/scenes/{scene_id}/commands",
                json={"request_id": f"step-{n}", "command": "STEP"},
            ).json()
            assert ack["accepted"] is True
        before = api.get(f"/api/scenes/{scene_id}/state").json()
        result = api.post(
            f"/api/scenes/{scene_id}/analyses",
            json={"agent_id": agent_id, "material_seqs": [1, 2]},
        ).json()
        after = api.get(f"/api/scenes/{scene_id}/state").json()
        blocked = api.post(
            f"/api/scenes/{scene_id}/analyses",
            json={"agent_id": agent_id, "material_seqs": [2]},
        ).json()
        listing = api.get(f"/api/scenes/{scene_id}/analyses").json()

    assert result["status"] == "NORMAL"
    assert result["provider_attempts"] == 1
    assert blocked["status"] == "BLOCKED"
    assert blocked["provider_attempts"] == 0
    assert listing["analysis_requests_used"] == 1
    assert {key: value for key, value in before.items() if key != "analysis_requests_used"} == {
        key: value for key, value in after.items() if key != "analysis_requests_used"
    }
    assert len(fake.calls) == 1
