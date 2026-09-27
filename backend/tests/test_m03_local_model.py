"""本地模型接入（PRD 第 8 节「可替换模型适配器」）。

分两层验证：

1. **单元层**（``httpx.MockTransport``）：请求体、请求头、解析与失败分类；
2. **真实 socket 层**：启动 :mod:`fake_local_model` 假本地服务，用**真实 HTTP**
   驱动**完整应用栈**（建场景 → 单步 → 时间线），证明本地提供方确实可用。

严格模式的假服务会拒绝 ``thinking`` 等 DeepSeek 专有字段，因此这些用例同时证明了
「本地请求体没有泄漏云服务专有字段」。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR / "scripts") not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR / "scripts"))

from fake_local_model import serve  # noqa: E402

from role_theater.config import Settings  # noqa: E402
from role_theater.contracts import (  # noqa: E402
    ActionType,
    ModelActionRequest,
    ModelFailureKind,
    ModelParams,
)
from role_theater.main import create_app  # noqa: E402
from role_theater.ports import (  # noqa: E402
    DEFAULT_LOCAL_BASE_URL,
    DeepSeekModelClient,
    LocalModelClient,
    MockModelPort,
    build_model_port,
)

FROM_DOTENV = "placeholder-not-a-real-key"


def _request(prompt: str = "只返回 JSON", *, model: str = "qwen2.5:7b") -> ModelActionRequest:
    return ModelActionRequest(
        scene_id="scn-1",
        actor_id="agt-1",
        prompt_template_id="role_action@m02",
        prompt=prompt,
        cursor_seq=0,
        params=ModelParams(model=model),
    )


def _completion(content: Any, finish_reason: str = "stop", **extra: Any) -> httpx.Response:
    payload: dict[str, Any] = {
        "choices": [
            {
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3},
        "model": "qwen2.5:7b",
    }
    payload.update(extra)
    return httpx.Response(200, json=payload)


def _client(transport: httpx.AsyncBaseTransport, **kwargs: Any) -> LocalModelClient:
    return LocalModelClient(
        base_url="http://127.0.0.1:11434/v1", transport=transport, **kwargs
    )


# --- 请求体差异（本地 vs 云服务） ---


def test_local_payload_omits_deepseek_specific_fields() -> None:
    payload = _client(httpx.MockTransport(lambda r: _completion("{}"))).build_payload(_request())

    assert "thinking" not in payload, "本地服务不认识 thinking，发送会被拒绝"
    assert "reasoning_effort" not in payload
    assert "tools" not in payload
    assert "temperature" not in payload
    assert payload["stream"] is False
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["model"] == "qwen2.5:7b"


def test_deepseek_payload_still_carries_thinking() -> None:
    """云服务路径不受本次改动影响（回归保护）。"""

    payload = DeepSeekModelClient(api_key="placeholder").build_payload(_request())

    assert payload["thinking"] == {"type": "disabled"}


def test_local_payload_can_disable_response_format_for_limited_servers() -> None:
    client = _client(
        httpx.MockTransport(lambda r: _completion("{}")), include_response_format=False
    )

    payload = client.build_payload(_request())

    assert "response_format" not in payload, "部分本地实现不支持 JSON 模式，需可关闭"
    # 仍由提示词约束 JSON；判定不因此放宽（见解析用例）。


async def test_local_client_works_without_any_credential() -> None:
    """本地服务不需要凭证；这是与云服务最关键的行为差异。"""

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _completion(json.dumps({"action": "SPEAK", "text": "本地模型的发言。"}))

    response = await _client(httpx.MockTransport(handler)).generate_action(_request())

    assert response.ok is True
    assert response.draft is not None
    assert response.draft.action is ActionType.SPEAK
    assert "authorization" not in {key.lower() for key in seen[0].headers}


async def test_local_client_sends_authorization_only_when_a_key_is_given() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _completion(json.dumps({"action": "PASS", "text": ""}))

    await _client(httpx.MockTransport(handler), api_key="local-gateway-token").generate_action(
        _request()
    )

    assert seen[0].headers.get("authorization") == "Bearer local-gateway-token"


def test_local_endpoint_defaults_and_overrides() -> None:
    assert LocalModelClient().endpoint == f"{DEFAULT_LOCAL_BASE_URL}/chat/completions"
    assert (
        LocalModelClient(base_url="http://127.0.0.1:1234/v1/").endpoint
        == "http://127.0.0.1:1234/v1/chat/completions"
    )


def test_local_client_never_leaks_the_key_in_repr() -> None:
    client = LocalModelClient(api_key="placeholder-secret-value")

    assert "placeholder-secret-value" not in repr(client)


# --- 失败分类（与云服务共用，不因换后端而放宽） ---


@pytest.mark.parametrize(
    ("content", "finish_reason", "expected"),
    [
        (None, "stop", ModelFailureKind.EMPTY_CONTENT),
        ("", "stop", ModelFailureKind.EMPTY_CONTENT),
        ('{"action": "SPEAK", "text": "截断', "length", ModelFailureKind.TRUNCATED),
        ("不是 JSON", "stop", ModelFailureKind.INVALID_JSON),
        ('{"action": "SPEAK", "text": "x", "extra": 1}', "stop", ModelFailureKind.SCHEMA_INVALID),
        ('{"action": "SPEAK", "text": ""}', "stop", ModelFailureKind.SCHEMA_INVALID),
        (json.dumps({"action": "SPEAK", "text": "x"}), "aborted", ModelFailureKind.PROVIDER_ERROR),
    ],
)
async def test_local_failures_are_classified_the_same_way(
    content: Any, finish_reason: str, expected: ModelFailureKind
) -> None:
    transport = httpx.MockTransport(lambda r: _completion(content, finish_reason))

    response = await _client(transport).generate_action(_request())

    assert response.ok is False
    assert response.failure is not None
    assert response.failure.kind is expected


async def test_local_server_http_error_is_a_provider_error() -> None:
    transport = httpx.MockTransport(
        lambda r: httpx.Response(500, json={"error": {"message": "本地服务崩了"}})
    )

    response = await _client(transport).generate_action(_request())

    assert response.failure is not None
    assert response.failure.kind is ModelFailureKind.PROVIDER_ERROR


async def test_local_timeout_is_reported_as_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("本地推理超时")

    response = await _client(httpx.MockTransport(handler)).generate_action(_request())

    assert response.failure is not None
    assert response.failure.kind is ModelFailureKind.TIMEOUT


# --- 提供方选择 ---


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({}, MockModelPort),
        ({"provider": "mock"}, MockModelPort),
        ({"api_key": "k"}, DeepSeekModelClient),
        ({"provider": "deepseek"}, DeepSeekModelClient),
        ({"provider": "local"}, LocalModelClient),
        ({"provider": "local", "api_key": "k"}, LocalModelClient),
        ({"provider": "local", "force_mock": True}, MockModelPort),
    ],
)
def test_provider_selection_matrix(kwargs: dict[str, Any], expected: type) -> None:
    assert isinstance(build_model_port(**kwargs), expected)


def test_settings_resolve_provider_and_configured_flag() -> None:
    assert Settings(_env_file=None).resolved_provider == "mock"
    assert Settings(_env_file=None).model_configured is False

    local = Settings(_env_file=None, model_provider="local")
    assert local.resolved_provider == "local"
    assert local.model_configured is True, "本地服务不需要凭证，必须视为已配置"
    assert local.model_endpoint == f"{DEFAULT_LOCAL_BASE_URL}/chat/completions"

    deepseek_without_key = Settings(_env_file=None, model_provider="deepseek")
    assert deepseek_without_key.resolved_provider == "deepseek"
    assert deepseek_without_key.model_configured is False

    forced = Settings(_env_file=None, model_provider="local", model_force_mock=True)
    assert forced.resolved_provider == "mock"


def test_health_reports_local_provider(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        model_provider="local",
        database_url=f"sqlite:///{tmp_path/'local.db'}",
    )

    with TestClient(create_app(settings)) as client:
        body = client.get("/api/health").json()

    assert body["model_provider"] == "local"
    assert body["model_configured"] is True
    assert body["model_credential_source"] == "none", "本地服务不需要凭证"


def test_explicit_local_provider_is_not_silently_replaced_by_mock(tmp_path: Path) -> None:
    """选了本地提供方就必须真的走本地客户端，不得静默回落 Mock（否则是假成功）。"""

    settings = Settings(
        _env_file=None,
        model_provider="local",
        database_url=f"sqlite:///{tmp_path/'local2.db'}",
    )
    app = create_app(settings)

    with TestClient(app) as client:
        assert client.get("/api/health").json()["model_provider"] == "local"
    assert isinstance(app.state.scene_runner._model, LocalModelClient)


# --- 真实 socket：假本地服务 + 完整应用栈 ---


def test_full_stack_against_a_real_local_endpoint(tmp_path: Path) -> None:
    """真实 HTTP（本机 socket）驱动完整应用栈：建场景 → 3 次单步 → 时间线。"""

    with serve(model="qwen2.5:7b") as server:
        settings = Settings(
            _env_file=None,
            model_provider="local",
            model_base_url=server.base_url,
            model_name="qwen2.5:7b",
            database_url=f"sqlite:///{tmp_path/'stack.db'}",
        )
        with TestClient(create_app(settings)) as client:
            detail = client.post("/api/scenes/preset", json={}).json()
            scene_id = detail["scene"]["scene_id"]

            for index in range(3):
                ack = client.post(
                    f"/api/scenes/{scene_id}/commands",
                    json={"request_id": f"local-step-{index}", "command": "STEP"},
                ).json()
                assert ack["accepted"] is True

            timeline = client.get(f"/api/scenes/{scene_id}/timeline").json()
            summary = client.get(f"/api/scenes/{scene_id}/summary").json()

        # 真实调用了假本地服务，并且记录里是本地模型名。
        assert server.recorder.calls >= 3
        assert all(
            payload["model"] == "qwen2.5:7b" for payload in server.recorder.payloads
        ), "应使用本地配置的模型名"
        # 严格模式的假服务未拒绝任何请求 → 证明没有发送 thinking 等专有字段。
        assert all(
            "thinking" not in payload for payload in server.recorder.payloads
        )
        # 请求确实只发往本机（不含 Authorization，因为未配置凭证）。
        assert all("authorization" not in headers for headers in server.recorder.headers)
        assert all(path.endswith("/v1/chat/completions") for path in server.recorder.paths)

        messages = [entry for entry in timeline["entries"] if entry["kind"] == "message"]
        assert [entry["message"]["text"] for entry in messages] == [
            "今晚要不要一起吃饭？",
            "我想先休息一会儿。",
        ]
        assert summary["role_requests_used"] == 3
        assert summary["succeeded"] == 3
        assert summary["failed"] == 0


def test_strict_local_server_rejects_cloud_only_fields(tmp_path: Path) -> None:
    """严格模式的反向验证：把 DeepSeek 客户端指向假本地服务会被拒。

    这条证明「严格模式确实在把关」，从而上面那条「未被拒绝」的断言才有意义。
    """

    with serve() as server:
        port = server.base_url.rsplit(":", 1)[1].split("/")[0]
        settings = Settings(
            _env_file=None,
            model_provider="deepseek",
            model_api_key=FROM_DOTENV,
            model_base_url=server.base_url,
            model_name="qwen2.5:7b",
            database_url=f"sqlite:///{tmp_path/'strict.db'}",
        )
        with TestClient(create_app(settings)) as client:
            detail = client.post("/api/scenes/preset", json={}).json()
            scene_id = detail["scene"]["scene_id"]
            ack = client.post(
                f"/api/scenes/{scene_id}/commands",
                json={"request_id": "strict-1", "command": "STEP"},
            ).json()
            assert ack["accepted"] is True, ack
            summary = client.get(f"/api/scenes/{scene_id}/summary").json()

        assert server.recorder.calls >= 1
        assert "thinking" in server.recorder.payloads[0], "云服务客户端会发送 thinking"
        assert summary["succeeded"] == 0, "严格本地服务应拒绝云服务专有字段"
        assert summary["failed"] == 1
        assert port.isdigit()


@pytest.mark.parametrize("scenario", ["empty", "truncated", "invalid-json", "server-error"])
def test_local_endpoint_failures_surface_as_failed_turns(
    tmp_path: Path, scenario: str
) -> None:
    """本地服务异常时必须体现为失败，绝不能被当成成功。"""

    with serve(scenario=scenario) as server:
        settings = Settings(
            _env_file=None,
            model_provider="local",
            model_base_url=server.base_url,
            database_url=f"sqlite:///{tmp_path/f'{scenario}.db'}",
        )
        with TestClient(create_app(settings)) as client:
            detail = client.post("/api/scenes/preset", json={}).json()
            scene_id = detail["scene"]["scene_id"]
            ack = client.post(
                f"/api/scenes/{scene_id}/commands",
                json={"request_id": "f1", "command": "STEP"},
            ).json()
            assert ack["accepted"] is True, ack
            summary = client.get(f"/api/scenes/{scene_id}/summary").json()

        assert summary["succeeded"] == 0
        assert summary["failed"] == 1
