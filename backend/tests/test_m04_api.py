"""M04 HTTP 接口（PRD 4.3、5.2、5.4、7.2；tasks/M04.md A1–A13）。"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from role_theater.contracts import ActionDraft, ActionType, EventVisibility


def speak(text: str) -> ActionDraft:
    return ActionDraft(action=ActionType.SPEAK, text=text)


def make_preset_scene(client: TestClient) -> str:
    response = client.post("/api/scenes/preset", json={"chat_policy_version": 1})
    assert response.status_code == 201, response.text
    return response.json()["scene"]["scene_id"]


def step(client: TestClient, scene_id: str, request_id: str) -> dict:
    response = client.post(
        f"/api/scenes/{scene_id}/commands",
        json={"request_id": request_id, "command": "STEP"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def command(client: TestClient, scene_id: str, request_id: str, name: str) -> dict:
    return client.post(
        f"/api/scenes/{scene_id}/commands", json={"request_id": request_id, "command": name}
    ).json()


# --- 命令 ---------------------------------------------------------------------


def test_step_command_runs_one_call_and_pauses(api_client: TestClient) -> None:
    scene_id = make_preset_scene(api_client)

    ack = step(api_client, scene_id, "req-step-1")

    assert ack["accepted"] is True
    assert ack["run_state"] == "PAUSED"
    assert ack["pause_reason"] == "MANUAL"
    state = api_client.get(f"/api/scenes/{scene_id}/state").json()
    assert state["role_requests_used"] == 1
    assert state["in_flight"] is False


def test_command_is_idempotent_through_http(api_client: TestClient) -> None:
    scene_id = make_preset_scene(api_client)

    first = step(api_client, scene_id, "same-req")
    second = step(api_client, scene_id, "same-req")

    assert first["deduplicated"] is False
    assert second["deduplicated"] is True
    assert api_client.get(f"/api/scenes/{scene_id}/state").json()["role_requests_used"] == 1


def test_all_roles_passing_leads_to_no_new_information_pause(api_client: TestClient) -> None:
    """Mock 默认 PASS：三个角色各一次启动机会后自然停下（PRD 5.1）。"""

    scene_id = make_preset_scene(api_client)
    for index in range(3):
        step(api_client, scene_id, f"step-{index}")

    ack = step(api_client, scene_id, "step-3")

    assert ack["accepted"] is True
    assert ack["detail"] == "没有候选角色"
    assert ack["pause_reason"] == "NO_NEW_INFORMATION"
    state = api_client.get(f"/api/scenes/{scene_id}/state").json()
    assert state["status"] == "PAUSED"
    assert state["role_requests_used"] == 3


def test_ended_scene_rejects_further_commands(api_client: TestClient) -> None:
    scene_id = make_preset_scene(api_client)
    assert command(api_client, scene_id, "stop-1", "STOP")["run_state"] == "ENDED"

    for name in ("START", "STEP", "RESUME"):
        ack = command(api_client, scene_id, f"after-{name}", name)
        assert ack["accepted"] is False
        assert ack["run_state"] == "ENDED"

    # STOP 本身是幂等的无操作。
    again = command(api_client, scene_id, "stop-2", "STOP")
    assert again["accepted"] is True
    assert again["run_state"] == "ENDED"


def test_unknown_command_name_is_rejected(api_client: TestClient) -> None:
    scene_id = make_preset_scene(api_client)

    response = api_client.post(
        f"/api/scenes/{scene_id}/commands",
        json={"request_id": "r1", "command": "EXPLODE"},
    )

    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"


def test_commands_on_unknown_scene_return_404(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/scenes/scn_missing/commands", json={"request_id": "r1", "command": "STEP"}
    )

    assert response.status_code == 404


def test_auto_run_reaches_a_pause_and_is_observable(api_client: TestClient) -> None:
    scene_id = make_preset_scene(api_client)

    ack = command(api_client, scene_id, "run-1", "START")
    assert ack["accepted"] is True
    assert ack["run_state"] == "RUNNING"

    # 轮询到停下为止（Mock 为 PASS，三个启动机会后 NO_NEW_INFORMATION）。
    for _ in range(200):
        state = api_client.get(f"/api/scenes/{scene_id}/state").json()
        if state["status"] == "PAUSED" and not state["in_flight"]:
            break
        import time

        time.sleep(0.02)

    assert state["status"] == "PAUSED"
    assert state["pause_reason"] == "NO_NEW_INFORMATION"
    assert state["role_requests_used"] == 3


# --- 事件 ---------------------------------------------------------------------


def test_public_event_injection_while_paused(api_client: TestClient) -> None:
    scene_id = make_preset_scene(api_client)

    response = api_client.post(
        f"/api/scenes/{scene_id}/events",
        json={"request_id": "e1", "body": "停电了。", "visibility": "ALL"},
    )

    assert response.status_code == 200
    ack = response.json()
    assert ack["accepted"] is True
    assert ack["event_status"] == "EFFECTIVE"
    assert ack["event_id"]

    events = api_client.get(f"/api/scenes/{scene_id}/events").json()
    assert len(events) == 1
    assert events[0]["status"] == "EFFECTIVE"
    assert events[0]["event"]["seq"] == 1


def test_targeted_event_requires_a_target(api_client: TestClient) -> None:
    scene_id = make_preset_scene(api_client)

    response = api_client.post(
        f"/api/scenes/{scene_id}/events",
        json={"request_id": "e1", "body": "只给一个人。", "visibility": "TARGETED"},
    )

    assert response.status_code == 422


def test_event_body_limit_is_enforced(api_client: TestClient) -> None:
    scene_id = make_preset_scene(api_client)

    response = api_client.post(
        f"/api/scenes/{scene_id}/events",
        json={"request_id": "e1", "body": "字" * 1001, "visibility": "ALL"},
    )

    assert response.status_code == 422


def test_events_are_rejected_after_the_scene_ended(api_client: TestClient) -> None:
    scene_id = make_preset_scene(api_client)
    command(api_client, scene_id, "stop-1", "STOP")

    response = api_client.post(
        f"/api/scenes/{scene_id}/events",
        json={"request_id": "e-late", "body": "太晚了。", "visibility": "ALL"},
    )

    assert response.status_code == 200
    assert response.json()["accepted"] is False
    assert api_client.get(f"/api/scenes/{scene_id}/events").json() == []


def test_event_injection_is_idempotent(api_client: TestClient) -> None:
    scene_id = make_preset_scene(api_client)
    payload = {"request_id": "e1", "body": "只生效一次。", "visibility": "ALL"}

    first = api_client.post(f"/api/scenes/{scene_id}/events", json=payload).json()
    second = api_client.post(f"/api/scenes/{scene_id}/events", json=payload).json()

    assert second["deduplicated"] is True
    assert second["event_id"] == first["event_id"]
    assert len(api_client.get(f"/api/scenes/{scene_id}/events").json()) == 1


# --- 时间线与历史 -------------------------------------------------------------


def test_timeline_merges_messages_and_events_by_seq(make_client) -> None:
    """消息与事件共享单调 seq，且时间线顺序 = 生效顺序。"""

    script = [speak("我先说一句。"), speak("有人敲门后我接一句。")]
    with make_client(script) as api_client:
        scene_id = make_preset_scene(api_client)
        step(api_client, scene_id, "s1")

        api_client.post(
            f"/api/scenes/{scene_id}/events",
            json={"request_id": "e1", "body": "有人敲门。", "visibility": "ALL"},
        )
        step(api_client, scene_id, "s2")

        timeline = api_client.get(f"/api/scenes/{scene_id}/timeline").json()

    kinds = [entry["kind"] for entry in timeline["entries"]]
    seqs = [entry["seq"] for entry in timeline["entries"]]
    assert kinds == ["message", "event", "message"]
    assert seqs == [1, 2, 3]
    assert timeline["entries"][0]["message"]["text"] == "我先说一句。"
    assert timeline["entries"][1]["event"]["body"] == "有人敲门。"
    assert timeline["entries"][2]["message"]["text"] == "有人敲门后我接一句。"
    assert timeline["last_seq"] == 3


def test_timeline_since_seq_returns_only_newer_entries(make_client) -> None:
    with make_client([speak("第一句。")]) as api_client:
        scene_id = make_preset_scene(api_client)
        step(api_client, scene_id, "s1")
        api_client.post(
            f"/api/scenes/{scene_id}/events",
            json={"request_id": "e1", "body": "第二件事。", "visibility": "ALL"},
        )

        timeline = api_client.get(
            f"/api/scenes/{scene_id}/timeline", params={"since_seq": 1}
        ).json()

    assert [entry["seq"] for entry in timeline["entries"]] == [2]


def test_timeline_does_not_call_the_model(api_client: TestClient) -> None:
    scene_id = make_preset_scene(api_client)
    step(api_client, scene_id, "s1")
    before = api_client.get(f"/api/scenes/{scene_id}/state").json()["role_requests_used"]

    for _ in range(5):
        api_client.get(f"/api/scenes/{scene_id}/timeline")

    assert api_client.get(f"/api/scenes/{scene_id}/state").json()["role_requests_used"] == before


def test_timeline_of_unknown_scene_is_404(api_client: TestClient) -> None:
    assert api_client.get("/api/scenes/scn_missing/timeline").status_code == 404
    assert api_client.get("/api/scenes/scn_missing/state").status_code == 404
    assert api_client.get("/api/scenes/scn_missing/events").status_code == 404
    assert api_client.get("/api/scenes/scn_missing/summary").status_code == 404


# --- 角色视角 -----------------------------------------------------------------


def test_viewpoint_matches_the_caller_context_and_hides_other_private_data(
    api_client: TestClient,
) -> None:
    scene_id = make_preset_scene(api_client)
    detail = api_client.get(f"/api/scenes/{scene_id}").json()
    target = detail["agents"][0]

    viewpoint = api_client.get(
        f"/api/scenes/{scene_id}/agents/{target['agent_id']}/viewpoint"
    ).json()

    assert viewpoint["agent_id"] == target["agent_id"]
    assert viewpoint["agent_name"] == target["name"]
    assert viewpoint["prompt_template_id"] == "role_action@simulation.p1.1"
    assert "朋友临时取消了聚会" in viewpoint["prompt"], "本人私有背景在内"
    assert "今天工作很累" not in viewpoint["prompt"], "他人私有背景不得出现"
    assert viewpoint["public_roster"] == ["安然", "许川", "陈禾"]


def test_viewpoint_reflects_only_effective_events(api_client: TestClient) -> None:
    scene_id = make_preset_scene(api_client)
    detail = api_client.get(f"/api/scenes/{scene_id}").json()
    target = detail["agents"][1]["agent_id"]

    api_client.post(
        f"/api/scenes/{scene_id}/events",
        json={"request_id": "e1", "body": "只给许川的提示。", "visibility": "TARGETED",
              "target_agent_id": target},
    )

    with_event = api_client.get(f"/api/scenes/{scene_id}/agents/{target}/viewpoint").json()
    other = detail["agents"][0]["agent_id"]
    without = api_client.get(f"/api/scenes/{scene_id}/agents/{other}/viewpoint").json()

    assert "只给许川的提示" in with_event["prompt"]
    assert "只给许川的提示" not in without["prompt"]


def test_viewpoint_of_unknown_agent_is_404(api_client: TestClient) -> None:
    scene_id = make_preset_scene(api_client)

    response = api_client.get(f"/api/scenes/{scene_id}/agents/agt_missing/viewpoint")

    assert response.status_code == 404


# --- 概览与预算 ---------------------------------------------------------------


def test_summary_reports_actual_call_counts(api_client: TestClient) -> None:
    scene_id = make_preset_scene(api_client)
    step(api_client, scene_id, "s1")
    step(api_client, scene_id, "s2")

    summary = api_client.get(f"/api/scenes/{scene_id}/summary").json()

    assert summary["role_requests_used"] == 2
    assert summary["max_role_requests"] == 200
    assert summary["succeeded"] == 2
    assert summary["failed"] == 0
    assert summary["unknown"] == 0


def test_budget_limit_from_scene_creation_is_respected(api_client: TestClient) -> None:
    templates = api_client.get("/api/templates").json()["templates"]
    if not templates:
        api_client.post("/api/scenes/preset", json={"chat_policy_version": 1})
        templates = api_client.get("/api/templates").json()["templates"]

    created = api_client.post(
        "/api/scenes",
        json={
            "title": "预算场景",
            "background": "背景。",
            "agents": [{"template_id": templates[0]["template_id"]},
                       {"template_id": templates[1]["template_id"]}],
            "max_role_requests": 2,
        },
    ).json()
    scene_id = created["scene"]["scene_id"]

    step(api_client, scene_id, "s1")
    step(api_client, scene_id, "s2")
    third = step(api_client, scene_id, "s3")

    assert third["run_state"] == "ENDED"
    assert api_client.get(f"/api/scenes/{scene_id}/state").json()["role_requests_used"] == 2


def test_first_request_locks_the_scene_roster(api_client: TestClient) -> None:
    scene_id = make_preset_scene(api_client)
    step(api_client, scene_id, "s1")

    detail = api_client.get(f"/api/scenes/{scene_id}").json()
    assert detail["locked"] is True

    response = api_client.post(
        f"/api/scenes/{scene_id}/agents",
        json={"template_id": api_client.get("/api/templates").json()["templates"][0]["template_id"]},
    )
    assert response.status_code == 409
    assert response.json()["error"] == "scene_locked"
