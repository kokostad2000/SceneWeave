"""M06 分析 API（PRD 6.1、6.2、5.3；tasks/M06.md A7、A9、A13）。

覆盖：能力查询、边界拦截（不占预算）、记录列表把「操作数」与「实际模型请求数」分开、
关闭分析时聊天照常可用。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from role_theater.analysis import ControlledAnalysisClient, ExternalAnalysisPort
from role_theater.contracts import ActionDraft, ActionType


class FakeAnalyzer:
    def __init__(self) -> None:
        self.requests: list = []

    async def analyze(self, request):
        self.requests.append(request)
        return {
            "behavior_labels": ["主动邀请"],
            "mechanisms": ["寻求社会连接"],
            "alternative_explanations": ["只是礼貌寒暄", "想确认今晚的安排"],
            "limitations": ["仅基于公开文本"],
            "disclaimer": "仅用于解释虚构角色的文本行为。",
        }


def speak(text: str) -> ActionDraft:
    return ActionDraft(action=ActionType.SPEAK, text=text)


def prepare(make_client, analyzer=None, *, script=None, **settings):
    """创建客户端并跑两次单步，返回 (client, scene_id, agent_ids, analyzer)。"""

    port = (
        ExternalAnalysisPort(analyzer=analyzer, client=ControlledAnalysisClient())
        if analyzer is not None
        else None
    )
    context = make_client(
        script or [speak("今晚一起吃饭吗？"), speak("我想先休息。")],
        analysis_enabled=analyzer is not None,
        injected_analysis_port=port,
        **settings,
    )
    return context


def scene_with_speech(client: TestClient, *, max_analysis_requests: int | None = None) -> tuple[str, list[str]]:
    detail = client.post("/api/scenes/preset", json={"chat_policy_version": 1}).json()
    if max_analysis_requests is not None:
        detail = create_budget_scene(client, max_analysis_requests)
    scene_id = detail["scene"]["scene_id"]
    agent_ids = [agent["agent_id"] for agent in detail["agents"]]
    client.post(f"/api/scenes/{scene_id}/commands", json={"request_id": "s1", "command": "STEP"})
    client.post(f"/api/scenes/{scene_id}/commands", json={"request_id": "s2", "command": "STEP"})
    return scene_id, agent_ids


def create_budget_scene(client: TestClient, max_analysis_requests: int):
    """用显式预算创建场景（预算是场景属性，不是进程配置）。"""

    templates = client.get("/api/templates").json()["templates"]
    if len(templates) < 2:
        client.post("/api/scenes/preset", json={"chat_policy_version": 1})
        templates = client.get("/api/templates").json()["templates"]
    return client.post(
        "/api/scenes",
        json={
            "title": "分析预算场景",
            "background": "背景。",
            "agents": [
                {"template_id": templates[0]["template_id"]},
                {"template_id": templates[1]["template_id"]},
            ],
            "max_analysis_requests": max_analysis_requests,
        },
    ).json()


def test_capability_endpoint_reports_disabled_without_external_package(
    api_client: TestClient,
) -> None:
    scene_id = api_client.post("/api/scenes/preset", json={"chat_policy_version": 1}).json()["scene"]["scene_id"]

    capability = api_client.get(f"/api/scenes/{scene_id}/analyses/capability").json()["capability"]

    assert capability["enabled"] is False
    assert capability["reason"]


def test_blocked_analysis_returns_201_with_zero_provider_attempts(
    api_client: TestClient,
) -> None:
    scene_id, agent_ids = scene_with_speech(api_client)

    response = api_client.post(
        f"/api/scenes/{scene_id}/analyses", json={"agent_id": agent_ids[0], "material_seqs": []}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "BLOCKED"
    assert body["provider_attempts"] == 0
    assert "尚未选择" in body["error"]


def test_analysis_list_separates_operations_from_provider_requests(
    api_client: TestClient,
) -> None:
    scene_id, agent_ids = scene_with_speech(api_client)
    api_client.post(
        f"/api/scenes/{scene_id}/analyses", json={"agent_id": agent_ids[0], "material_seqs": []}
    )

    listing = api_client.get(f"/api/scenes/{scene_id}/analyses").json()

    assert listing["operations_total"] == 1, "被本地规则拦截也记录一次分析操作"
    assert listing["provider_attempts_total"] == 0, "没有发生任何模型请求"
    assert listing["analysis_requests_used"] == 0, "拦截不占用分析预算"
    assert listing["max_analysis_requests"] == 4


def test_targeted_event_cannot_be_analysed(make_client) -> None:
    with make_client([speak("今晚一起吃饭吗？"), speak("我想先休息。")]) as api_client:
        scene_id, agent_ids = scene_with_speech(api_client)
        _targeted_event_case(api_client, scene_id, agent_ids)


def _targeted_event_case(api_client: TestClient, scene_id: str, agent_ids: list[str]) -> None:
    api_client.post(
        f"/api/scenes/{scene_id}/events",
        json={
            "request_id": "e1",
            "body": "只给许川的提示。",
            "visibility": "TARGETED",
            "target_agent_id": agent_ids[1],
        },
    )

    response = api_client.post(
        f"/api/scenes/{scene_id}/analyses",
        json={"agent_id": agent_ids[0], "material_seqs": [3]},
    ).json()

    assert response["status"] == "BLOCKED"
    assert "定向事件" in response["error"]
    assert response["materials"] == []


def test_analysis_records_are_isolated_per_agent(api_client: TestClient) -> None:
    scene_id, agent_ids = scene_with_speech(api_client)
    for agent_id in agent_ids[:2]:
        api_client.post(
            f"/api/scenes/{scene_id}/analyses", json={"agent_id": agent_id, "material_seqs": []}
        )

    first = api_client.get(
        f"/api/scenes/{scene_id}/analyses", params={"agent_id": agent_ids[0]}
    ).json()
    second = api_client.get(
        f"/api/scenes/{scene_id}/analyses", params={"agent_id": agent_ids[1]}
    ).json()

    assert len(first["records"]) == 1
    assert len(second["records"]) == 1
    assert first["records"][0]["agent_id"] != second["records"][0]["agent_id"]


def test_unknown_scene_and_agent_return_404(api_client: TestClient) -> None:
    scene_id, _ = scene_with_speech(api_client)

    assert api_client.get("/api/scenes/scn_missing/analyses").status_code == 404
    assert (
        api_client.post(
            "/api/scenes/scn_missing/analyses", json={"agent_id": "agt-1", "material_seqs": []}
        ).status_code
        == 404
    )
    assert (
        api_client.post(
            f"/api/scenes/{scene_id}/analyses", json={"agent_id": "agt_missing", "material_seqs": []}
        ).status_code
        == 404
    )


def test_analysis_rejects_extra_fields(api_client: TestClient) -> None:
    scene_id, agent_ids = scene_with_speech(api_client)

    response = api_client.post(
        f"/api/scenes/{scene_id}/analyses",
        json={"agent_id": agent_ids[0], "material_seqs": [], "persist_profile": True},
    )

    assert response.status_code == 422


def test_disabled_analysis_does_not_break_chatting(make_client) -> None:
    """PRD 第 9 节 M06 通过条件：关闭模块可正常聊天。"""

    with make_client([speak("今晚一起吃饭吗？"), speak("我想先休息。")]) as api_client:
        scene_id, agent_ids = scene_with_speech(api_client)

        record = api_client.post(
            f"/api/scenes/{scene_id}/analyses",
            json={"agent_id": agent_ids[0], "material_seqs": [1]},
        ).json()
        assert record["status"] == "DISABLED"
        assert record["provider_attempts"] == 0

        # 聊天继续可用。
        ack = api_client.post(
            f"/api/scenes/{scene_id}/commands", json={"request_id": "s3", "command": "STEP"}
        ).json()
        assert ack["accepted"] is True
        timeline = api_client.get(f"/api/scenes/{scene_id}/timeline").json()
        assert timeline["last_seq"] >= 1


def test_analysis_state_has_no_effect_on_the_scene(make_client) -> None:
    analyzer = FakeAnalyzer()
    with prepare(make_client, analyzer) as client:
        scene_id, agent_ids = scene_with_speech(client)
        before = client.get(f"/api/scenes/{scene_id}/state").json()
        before_viewpoint = client.get(
            f"/api/scenes/{scene_id}/agents/{agent_ids[0]}/viewpoint"
        ).json()

        record = client.post(
            f"/api/scenes/{scene_id}/analyses",
            json={"agent_id": agent_ids[0], "material_seqs": [1, 2]},
        ).json()

        after = client.get(f"/api/scenes/{scene_id}/state").json()
        after_viewpoint = client.get(
            f"/api/scenes/{scene_id}/agents/{agent_ids[0]}/viewpoint"
        ).json()

    assert record["status"] == "NORMAL"
    assert record["provider_attempts"] == 1
    assert len(record["report"]["alternative_explanations"]) >= 2
    assert record["report"]["disclaimer"]
    assert record["materials"], "记录保留送出的材料原文与来源"

    # 剧情侧状态完全不变：运行状态、暂停原因、角色请求预算、在途标记、时间线位置。
    for field in ("status", "pause_reason", "role_requests_used", "max_role_requests", "in_flight", "last_committed_seq"):
        assert after[field] == before[field], f"分析不得改变 {field}"
    # 分析预算独立计数，且恰好增加 1（真实发送）。
    assert after["analysis_requests_used"] == before["analysis_requests_used"] + 1
    assert after_viewpoint == before_viewpoint, "分析结果不得进入角色上下文"
    assert analyzer.requests and analyzer.requests[0].persist_profile is False


def test_analysis_budget_exhaustion_is_reported_without_provider_call(make_client) -> None:
    analyzer = FakeAnalyzer()
    with prepare(make_client, analyzer) as client:
        scene_id, agent_ids = scene_with_speech(client, max_analysis_requests=1)
        first = client.post(
            f"/api/scenes/{scene_id}/analyses", json={"agent_id": agent_ids[0], "material_seqs": [1]}
        ).json()
        second = client.post(
            f"/api/scenes/{scene_id}/analyses", json={"agent_id": agent_ids[0], "material_seqs": [1]}
        ).json()

    assert first["status"] == "NORMAL"
    assert second["status"] == "BLOCKED"
    assert second["provider_attempts"] == 0
    assert "已用尽" in second["error"]
    assert len(analyzer.requests) == 1


def test_pc_private_analysis_blocked_even_mixed_and_public_relay_keeps_author(make_client):
    analyzer = FakeAnalyzer()
    with prepare(make_client, analyzer) as client:
        detail = client.post("/api/scenes/preset", json={"chat_policy_version": 1}).json()
        sid = detail["scene"]["scene_id"]
        a,b,c = [x["agent_id"] for x in detail["agents"]]
        port = client.app.state.scene_runner._model
        port._script = [ActionDraft(action="PRIVATE", text="PRIVATE_ANALYSIS_MARKER", recipient_id=b),
                        ActionDraft(action="SPEAK", text="转述新的公开说法")]
        for n in range(2):
            assert client.post(f"/api/scenes/{sid}/commands", json={"request_id":f"pc{n}","command":"STEP"}).json()["accepted"]
        for seqs in [[1],[1,2]]:
            response = client.post(f"/api/scenes/{sid}/analyses", json={"agent_id":b,"material_seqs":seqs}).json()
            assert response["status"] == "BLOCKED" and response["provider_attempts"] == 0
            assert response["behavior_description"] == "" and response["context"] == ""
        assert analyzer.requests == []
        assert client.get(f"/api/scenes/{sid}/state").json()["analysis_requests_used"] == 0
        response = client.post(f"/api/scenes/{sid}/analyses", json={"agent_id":b,"material_seqs":[2]}).json()
        assert response["status"] == "NORMAL"
        req = analyzer.requests[-1]
        assert "PRIVATE_ANALYSIS_MARKER" not in str(req)
        assert "转述新的公开说法" in req.behavior_description
        assert all(m["author_agent_id"] == b for m in response["materials"])
        assert port.call_count == 2
