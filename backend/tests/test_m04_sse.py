"""M04 SSE（PRD 第 8 节；tasks/M04.md A10）。

SSE 从**已提交**数据按 ``seq`` 补发：断线重连只靠 ``since_seq`` 追赶，
不会重放模型请求，也不会重复推送同一条。
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from role_theater.contracts import ActionDraft, ActionType


def speak(text: str) -> ActionDraft:
    return ActionDraft(action=ActionType.SPEAK, text=text)


def make_scene(client: TestClient) -> str:
    return client.post("/api/scenes/preset", json={"chat_policy_version": 1}).json()["scene"]["scene_id"]


def read_sse(client: TestClient, scene_id: str, **params) -> list[dict]:
    """读取 SSE 流并解析出 data 负载（用 replay_limit 有界结束）。"""

    events: list[dict] = []
    with client.stream(
        "GET", f"/api/scenes/{scene_id}/stream", params=params
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        current: dict[str, str] = {}
        for raw in response.iter_lines():
            line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            if line.startswith("id: "):
                current["id"] = line[4:]
            elif line.startswith("event: "):
                current["event"] = line[7:]
            elif line.startswith("data: "):
                current["data"] = line[6:]
            elif line == "" and "data" in current:
                if current.get("event") == "timeline":
                    events.append(json.loads(current["data"]))
                current = {}
    return events


def test_stream_replays_committed_timeline_by_seq(make_client) -> None:
    draft = ActionDraft(action=ActionType.SPEAK, text="我先说一句。")
    with make_client([draft]) as api_client:
        scene_id = make_scene(api_client)
        api_client.post(
            f"/api/scenes/{scene_id}/commands", json={"request_id": "s1", "command": "STEP"}
        )
        api_client.post(
            f"/api/scenes/{scene_id}/events",
            json={"request_id": "e1", "body": "有人敲门。", "visibility": "ALL"},
        )

        events = read_sse(api_client, scene_id, since_seq=0, replay_limit=5)

    assert [event["seq"] for event in events] == [1, 2]
    assert [event["kind"] for event in events] == ["message", "event"]
    assert events[0]["payload"]["text"] == "我先说一句。"
    assert events[1]["payload"]["body"] == "有人敲门。"


def test_stream_since_seq_catches_up_without_replaying_old_entries(make_client) -> None:
    with make_client([speak("第一句。")]) as api_client:
        scene_id = make_scene(api_client)
        api_client.post(
            f"/api/scenes/{scene_id}/commands", json={"request_id": "s1", "command": "STEP"}
        )
        api_client.post(
            f"/api/scenes/{scene_id}/events",
            json={"request_id": "e1", "body": "第二件事。", "visibility": "ALL"},
        )

        events = read_sse(api_client, scene_id, since_seq=1, replay_limit=5)

    assert [event["seq"] for event in events] == [2], "只补发断线之后的新条目"


def test_stream_does_not_duplicate_entries_on_reconnect(make_client) -> None:
    with make_client([speak("第一句。"), speak("第二句。")]) as api_client:
        scene_id = make_scene(api_client)
        for index in range(2):
            api_client.post(
                f"/api/scenes/{scene_id}/commands",
                json={"request_id": f"s{index}", "command": "STEP"},
            )

        first = read_sse(api_client, scene_id, since_seq=0, replay_limit=10)
        second = read_sse(api_client, scene_id, since_seq=first[-1]["seq"], replay_limit=10)

    assert [event["seq"] for event in first] == [1, 2]
    assert second == [], "重连不重复推送已见过的 seq"


def test_stream_does_not_call_the_model(api_client: TestClient) -> None:
    scene_id = make_scene(api_client)
    api_client.post(
        f"/api/scenes/{scene_id}/commands", json={"request_id": "s1", "command": "STEP"}
    )
    before = api_client.get(f"/api/scenes/{scene_id}/state").json()["role_requests_used"]

    read_sse(api_client, scene_id, since_seq=0, replay_limit=10)

    assert api_client.get(f"/api/scenes/{scene_id}/state").json()["role_requests_used"] == before


def test_replay_limit_bounds_a_single_connection(api_client: TestClient) -> None:
    scene_id = make_scene(api_client)
    for index in range(3):
        api_client.post(
            f"/api/scenes/{scene_id}/events",
            json={"request_id": f"e{index}", "body": f"第{index}件事。", "visibility": "ALL"},
        )

    events = read_sse(api_client, scene_id, since_seq=0, replay_limit=2)

    assert [event["seq"] for event in events] == [1, 2], "有界追赶后可再连"


def test_stream_of_unknown_scene_is_404(api_client: TestClient) -> None:
    response = api_client.get("/api/scenes/scn_missing/stream")

    assert response.status_code == 404


def test_accepted_events_are_not_streamed_until_effective(api_client: TestClient) -> None:
    """待生效事件不得出现在时间线／SSE 中（PRD 4.3）。"""

    scene_id = make_scene(api_client)
    accepted = api_client.post(
        f"/api/scenes/{scene_id}/events",
        json={"request_id": "e1", "body": "尚未生效。", "visibility": "ALL"},
    ).json()
    assert accepted["event_status"] == "EFFECTIVE"

    events = read_sse(api_client, scene_id, since_seq=0, replay_limit=5)

    assert [event["seq"] for event in events] == [1]
    assert events[0]["payload"]["status"] == "EFFECTIVE"


def test_heartbeat_is_a_comment_and_never_becomes_a_timeline_entry(
    api_client: TestClient,
) -> None:
    """心跳是传输层内容，不进入剧情、不产生 seq（PRD 4.1）。"""

    scene_id = make_scene(api_client)

    with api_client.stream(
        "GET", f"/api/scenes/{scene_id}/stream", params={"since_seq": 0, "replay_limit": 1}
    ) as response:
        body = b"".join(response.iter_bytes())

    # 该场景没有任何已提交条目，因此不会有 timeline 事件。
    assert b"event: timeline" not in body
    timeline = api_client.get(f"/api/scenes/{scene_id}/timeline").json()
    assert timeline["entries"] == []
    assert timeline["last_seq"] == 0


def test_stream_closes_after_the_scene_ends(api_client: TestClient) -> None:
    scene_id = make_scene(api_client)
    api_client.post(
        f"/api/scenes/{scene_id}/commands", json={"request_id": "stop", "command": "STOP"}
    )

    with api_client.stream("GET", f"/api/scenes/{scene_id}/stream", params={"since_seq": 0}) as response:
        body = b"".join(response.iter_bytes())

    assert b"event: closed" in body
