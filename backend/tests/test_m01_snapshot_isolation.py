"""M01 快照隔离：旧场景不受模板改动影响（PRD 3.2；tasks/M01.md A3）。

这是 PRD 第 9 节 M01 通过条件的第二条，必须由独立测试证明，而不是靠代码阅读。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

PROFILE = {
    "name": "安然",
    "persona": "主动热情。",
    "speech_style": "热情提问。",
    "initial_goal": "想找人一起度过晚上。",
    "private_background": "朋友临时取消了聚会。",
}


def _create_template(client: TestClient, **overrides: str) -> dict:
    response = client.post("/api/templates", json={**PROFILE, **overrides})
    assert response.status_code == 201, response.text
    return response.json()


def _create_pair_scene(client: TestClient) -> tuple[dict, dict, dict]:
    first = _create_template(client)
    second = _create_template(client, name="许川", private_background="今天工作很累。")
    response = client.post(
        "/api/scenes",
        json={
            "title": "快照隔离场景",
            "background": "晚上，三个室友在客厅相遇。",
            "agents": [
                {"template_id": first["template_id"]},
                {"template_id": second["template_id"]},
            ],
        },
    )
    assert response.status_code == 201, response.text
    return first, second, response.json()


def test_editing_a_template_does_not_change_existing_scenes(api_client: TestClient) -> None:
    first, _, scene = _create_pair_scene(api_client)
    scene_id = scene["scene"]["scene_id"]

    patched = api_client.patch(
        f"/api/templates/{first['template_id']}",
        json={
            "name": "安然（改）",
            "persona": "完全改写的人物设定。",
            "speech_style": "完全改写的表达习惯。",
            "initial_goal": "完全改写的目标。",
            "private_background": "完全改写的私有背景。",
        },
    )
    assert patched.status_code == 200

    reloaded = api_client.get(f"/api/scenes/{scene_id}").json()
    agent = reloaded["agents"][0]

    # 显示名与快照都必须保持创建时的值。
    assert agent["name"] == "安然"
    assert agent["snapshot"]["name"] == "安然"
    assert agent["snapshot"]["persona"] == "主动热情。"
    assert agent["snapshot"]["speech_style"] == "热情提问。"
    assert agent["snapshot"]["initial_goal"] == "想找人一起度过晚上。"
    assert agent["snapshot"]["private_background"] == "朋友临时取消了聚会。"
    # 快照仍指向原模板，便于追溯来源。
    assert agent["snapshot"]["source_template_id"] == first["template_id"]


def test_deleting_a_template_does_not_break_existing_scenes(api_client: TestClient) -> None:
    first, _, scene = _create_pair_scene(api_client)
    scene_id = scene["scene"]["scene_id"]

    assert api_client.delete(f"/api/templates/{first['template_id']}").status_code == 204

    reloaded = api_client.get(f"/api/scenes/{scene_id}").json()
    assert len(reloaded["agents"]) == 2
    assert reloaded["agents"][0]["snapshot"]["private_background"] == "朋友临时取消了聚会。"
    # 场景本身仍可读取、仍可增删角色之外的只读操作。
    assert api_client.get("/api/scenes").json()["scenes"][0]["agent_count"] == 2


def test_deleted_template_can_no_longer_be_used_for_new_agents(api_client: TestClient) -> None:
    first, _, scene = _create_pair_scene(api_client)
    scene_id = scene["scene"]["scene_id"]
    api_client.delete(f"/api/templates/{first['template_id']}")

    response = api_client.post(
        f"/api/scenes/{scene_id}/agents", json={"template_id": first["template_id"]}
    )

    assert response.status_code == 409
    assert response.json()["error"] == "unknown_template"


def test_copying_a_template_does_not_touch_existing_scenes(api_client: TestClient) -> None:
    first, _, scene = _create_pair_scene(api_client)
    scene_id = scene["scene"]["scene_id"]
    before = api_client.get(f"/api/scenes/{scene_id}").json()

    copied = api_client.post(f"/api/templates/{first['template_id']}/copy", json={})
    assert copied.status_code == 201

    after = api_client.get(f"/api/scenes/{scene_id}").json()
    assert after == before


def test_two_scenes_from_the_same_template_are_independent(api_client: TestClient) -> None:
    first = _create_template(api_client)
    second = _create_template(api_client, name="许川")

    def new_scene(title: str) -> str:
        response = api_client.post(
            "/api/scenes",
            json={
                "title": title,
                "background": "背景。",
                "agents": [
                    {"template_id": first["template_id"]},
                    {"template_id": second["template_id"]},
                ],
            },
        )
        assert response.status_code == 201
        return response.json()["scene"]["scene_id"]

    scene_a = new_scene("场景 A")
    scene_b = new_scene("场景 B")

    # 在场景 A 里改显示名，场景 B 不受影响。
    agent_a = api_client.get(f"/api/scenes/{scene_a}").json()["agents"][0]["agent_id"]
    assert api_client.patch(
        f"/api/scenes/{scene_a}/agents/{agent_a}", json={"name": "只在 A 生效"}
    ).status_code == 200

    assert api_client.get(f"/api/scenes/{scene_b}").json()["agents"][0]["name"] == "安然"
    # 两个场景的 agent_id 互不相同（新的 agent_id，而不是复用模板 ID）。
    ids_a = {a["agent_id"] for a in api_client.get(f"/api/scenes/{scene_a}").json()["agents"]}
    ids_b = {a["agent_id"] for a in api_client.get(f"/api/scenes/{scene_b}").json()["agents"]}
    assert ids_a.isdisjoint(ids_b)
    assert first["template_id"] not in ids_a


def test_locked_scene_snapshot_cannot_be_rewritten(api_client: TestClient) -> None:
    """锁定后即使改模板，也必须保持快照原样（PRD 3.2）。"""

    first, _, scene = _create_pair_scene(api_client)
    scene_id = scene["scene"]["scene_id"]
    api_client.app.state.scene_service.lock(scene_id)

    api_client.patch(
        f"/api/templates/{first['template_id']}",
        json={"private_background": "试图悄悄改写。"},
    )

    reloaded = api_client.get(f"/api/scenes/{scene_id}").json()
    assert reloaded["locked"] is True
    assert reloaded["agents"][0]["snapshot"]["private_background"] == "朋友临时取消了聚会。"


def test_preset_templates_are_recreated_on_demand_after_removal(
    api_client: TestClient,
) -> None:
    """预置模板被移除后，预置场景仍可再次创建（tasks/M01.md §3.4）。"""

    first_preset = api_client.post("/api/scenes/preset", json={}).json()
    assert len(first_preset["agents"]) == 3

    templates = api_client.get("/api/templates").json()["templates"]
    for template in templates:
        assert api_client.delete(f"/api/templates/{template['template_id']}").status_code == 204
    assert api_client.get("/api/templates").json()["templates"] == []

    second_preset = api_client.post("/api/scenes/preset", json={}).json()
    assert [agent["name"] for agent in second_preset["agents"]] == ["安然", "许川", "陈禾"]
    # 旧场景不受影响。
    assert len(api_client.get(f"/api/scenes/{first_preset['scene']['scene_id']}").json()["agents"]) == 3
