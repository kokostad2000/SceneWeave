"""M01 场景与本场角色（PRD 1.2、3.1、3.2、5.3；tasks/M01.md A2、A3、A5、A7、A8、A10）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from role_theater.contracts import AgentProfileFields
from role_theater.domain import AgentSpec, SceneService, TemplateService

PROFILE = {
    "persona": "人物设定。",
    "speech_style": "表达习惯。",
    "initial_goal": "初始目标。",
    "private_background": "私有背景。",
}


def make_template(client: TestClient, name: str, **overrides: str) -> str:
    response = client.post("/api/templates", json={**PROFILE, "name": name, **overrides})
    assert response.status_code == 201, response.text
    return response.json()["template_id"]


def make_templates(client: TestClient, names: list[str]) -> list[str]:
    return [make_template(client, name) for name in names]


def create_scene(client: TestClient, template_ids: list[str], **overrides: object) -> dict:
    payload: dict[str, object] = {
        "title": "测试场景",
        "background": "一段场景背景。",
        "agents": [{"template_id": tid} for tid in template_ids],
    }
    payload.update(overrides)
    response = client.post("/api/scenes", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# --- 规模：三人增至五人不改代码 -------------------------------------------------


@pytest.mark.parametrize("count", [2, 3, 5, 8])
def test_scene_creation_is_data_driven_for_any_allowed_size(
    api_client: TestClient, count: int
) -> None:
    names = [f"角色{index}" for index in range(count)]
    detail = create_scene(api_client, make_templates(api_client, names))

    assert len(detail["agents"]) == count
    assert [agent["name"] for agent in detail["agents"]] == names
    assert [agent["order_index"] for agent in detail["agents"]] == list(range(count))
    assert len({agent["agent_id"] for agent in detail["agents"]}) == count


@pytest.mark.parametrize("count", [0, 1, 9, 20])
def test_scene_creation_outside_two_to_eight_is_rejected(
    api_client: TestClient, count: int
) -> None:
    names = [f"角色{index}" for index in range(max(count, 1))]
    template_ids = make_templates(api_client, names)

    response = api_client.post(
        "/api/scenes",
        json={
            "title": "测试场景",
            "background": "背景。",
            "agents": [{"template_id": tid} for tid in template_ids[:count]],
        },
    )

    assert response.status_code == 422, response.text


def test_default_preset_uses_three_agents(api_client: TestClient) -> None:
    detail = api_client.post("/api/scenes/preset", json={}).json()

    assert len(detail["agents"]) == 3


# --- 快照与主键 ----------------------------------------------------------------


def test_scene_agents_carry_snapshot_and_source_template_id(api_client: TestClient) -> None:
    template_id = make_template(api_client, "安然", private_background="朋友临时取消了聚会。")
    detail = create_scene(api_client, [template_id, make_template(api_client, "许川")])

    first = detail["agents"][0]
    assert first["agent_id"].startswith("agt_")
    assert first["snapshot"]["source_template_id"] == template_id
    assert first["snapshot"]["name"] == "安然"
    assert first["snapshot"]["private_background"] == "朋友临时取消了聚会。"
    assert first["snapshot"]["captured_at"]
    assert first["scene_id"] == detail["scene"]["scene_id"]


def test_display_name_can_override_template_name_while_snapshot_stays_faithful(
    api_client: TestClient,
) -> None:
    template_id = make_template(api_client, "安然")
    other_id = make_template(api_client, "许川")

    response = api_client.post(
        "/api/scenes",
        json={
            "title": "改名场景",
            "background": "背景。",
            "agents": [
                {"template_id": template_id, "name": "安小然"},
                {"template_id": other_id},
            ],
        },
    )

    assert response.status_code == 201, response.text
    scene = response.json()
    assert scene["agents"][0]["name"] == "安小然"
    # 快照忠实记录模板内容，不因显示名变化而改写（PRD 3.2）。
    assert scene["agents"][0]["snapshot"]["name"] == "安然"
    assert scene["agents"][1]["name"] == "许川"
    assert scene["agents"][1]["snapshot"]["name"] == "许川"


def test_agent_id_is_not_accepted_where_a_template_id_is_required(
    api_client: TestClient,
) -> None:
    detail = create_scene(api_client, make_templates(api_client, ["安然", "许川"]))
    agent_id = detail["agents"][0]["agent_id"]

    response = api_client.post(
        "/api/scenes",
        json={
            "title": "错用 ID",
            "background": "背景。",
            "agents": [
                {"template_id": agent_id},
                {"template_id": detail["agents"][1]["agent_id"]},
            ],
        },
    )

    assert response.status_code == 409
    assert response.json()["error"] == "unknown_template"


# --- 唯一性 --------------------------------------------------------------------


def test_duplicate_names_inside_one_scene_are_rejected(api_client: TestClient) -> None:
    first = make_template(api_client, "安然")
    second = make_template(api_client, "许川")

    response = api_client.post(
        "/api/scenes",
        json={
            "title": "重名场景",
            "background": "背景。",
            "agents": [
                {"template_id": first, "name": "同名"},
                {"template_id": second, "name": "同名"},
            ],
        },
    )

    assert response.status_code == 409
    assert response.json()["error"] == "duplicate_name"


def test_unknown_template_reference_is_rejected(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/scenes",
        json={
            "title": "缺模板场景",
            "background": "背景。",
            "agents": [
                {"template_id": "tpl_missing"},
                {"template_id": "tpl_missing2"},
            ],
        },
    )

    assert response.status_code == 409
    assert response.json()["error"] == "unknown_template"


# --- 预算 ----------------------------------------------------------------------


def test_budget_can_be_configured_at_creation_and_is_locked_out_later(
    api_client: TestClient,
) -> None:
    detail = create_scene(
        api_client,
        make_templates(api_client, ["安然", "许川"]),
        max_role_requests=10,
        max_analysis_requests=2,
    )

    budget = detail["scene"]["budget"]
    assert budget["max_role_requests"] == 10
    assert budget["max_analysis_requests"] == 2
    assert budget["locked_at"] is None
    assert detail["locked"] is False


@pytest.mark.parametrize("bad_limit", [0, 10_000])
def test_budget_outside_the_allowed_range_is_rejected(
    api_client: TestClient, bad_limit: int
) -> None:
    template_ids = make_templates(api_client, ["陈禾", "阿明"])

    response = api_client.post(
        "/api/scenes",
        json={
            "title": "越界预算",
            "background": "背景。",
            "agents": [{"template_id": tid} for tid in template_ids],
            "max_role_requests": bad_limit,
        },
    )

    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"


def test_budget_defaults_match_the_contract(api_client: TestClient) -> None:
    detail = create_scene(api_client, make_templates(api_client, ["安然", "许川"]))
    budget = detail["scene"]["budget"]

    assert budget["max_role_requests"] == 24
    assert budget["max_analysis_requests"] == 4


# --- 增删改 --------------------------------------------------------------------


def test_agents_can_be_added_up_to_the_limit(api_client: TestClient) -> None:
    names = [f"角色{index}" for index in range(8)]
    template_ids = make_templates(api_client, names)
    detail = create_scene(api_client, template_ids[:7])
    scene_id = detail["scene"]["scene_id"]

    added = api_client.post(
        f"/api/scenes/{scene_id}/agents", json={"template_id": template_ids[7]}
    )
    assert added.status_code == 201
    assert added.json()["name"] == "角色7"

    # 第 9 名必须被拒绝（PRD 1.2）。
    ninth = make_template(api_client, "第九人")
    rejected = api_client.post(
        f"/api/scenes/{scene_id}/agents", json={"template_id": ninth}
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"] == "agent_count_out_of_range"
    assert len(api_client.get(f"/api/scenes/{scene_id}").json()["agents"]) == 8


def test_agents_cannot_be_removed_below_the_minimum(api_client: TestClient) -> None:
    detail = create_scene(api_client, make_templates(api_client, ["安然", "许川"]))
    scene_id = detail["scene"]["scene_id"]
    agent_id = detail["agents"][0]["agent_id"]

    response = api_client.delete(f"/api/scenes/{scene_id}/agents/{agent_id}")

    assert response.status_code == 409
    assert response.json()["error"] == "agent_count_out_of_range"


def test_remove_then_add_keeps_the_scene_consistent(api_client: TestClient) -> None:
    template_ids = make_templates(api_client, ["安然", "许川", "陈禾"])
    detail = create_scene(api_client, template_ids)
    scene_id = detail["scene"]["scene_id"]
    removed = detail["agents"][1]["agent_id"]

    assert api_client.delete(f"/api/scenes/{scene_id}/agents/{removed}").status_code == 204
    remaining = api_client.get(f"/api/scenes/{scene_id}").json()["agents"]
    assert [agent["name"] for agent in remaining] == ["安然", "陈禾"]

    fourth = make_template(api_client, "阿明")
    added = api_client.post(f"/api/scenes/{scene_id}/agents", json={"template_id": fourth})
    assert added.status_code == 201
    # 顺序号继续递增，不复用被删除角色的位置。
    assert added.json()["order_index"] == 3


def test_rename_agent_and_reject_duplicates(api_client: TestClient) -> None:
    detail = create_scene(api_client, make_templates(api_client, ["安然", "许川"]))
    scene_id = detail["scene"]["scene_id"]
    first, second = detail["agents"]

    renamed = api_client.patch(
        f"/api/scenes/{scene_id}/agents/{first['agent_id']}", json={"name": "安小然"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "安小然"
    # 快照不因显示名变化而改写。
    assert renamed.json()["snapshot"]["name"] == "安然"

    conflict = api_client.patch(
        f"/api/scenes/{scene_id}/agents/{first['agent_id']}", json={"name": second["name"]}
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"] == "duplicate_name"


def test_unknown_scene_and_agent_return_404(api_client: TestClient) -> None:
    detail = create_scene(api_client, make_templates(api_client, ["安然", "许川"]))
    scene_id = detail["scene"]["scene_id"]
    agent_id = detail["agents"][0]["agent_id"]

    assert api_client.get("/api/scenes/scn_missing").status_code == 404
    assert api_client.post(
        "/api/scenes/scn_missing/agents", json={"template_id": "tpl_x"}
    ).status_code == 404
    assert api_client.patch(
        "/api/scenes/scn_missing/agents/agt_x", json={"name": "新名字"}
    ).status_code == 404
    assert api_client.delete("/api/scenes/scn_missing/agents/agt_x").status_code == 404
    assert api_client.patch(
        f"/api/scenes/{scene_id}/agents/agt_missing", json={"name": "新名字"}
    ).status_code == 404


def test_scene_list_reports_agent_counts(api_client: TestClient) -> None:
    create_scene(api_client, make_templates(api_client, ["安然", "许川"]), title="两人场景")
    create_scene(
        api_client,
        make_templates(api_client, ["陈禾", "阿明", "小雨"]),
        title="三人场景",
    )

    scenes = api_client.get("/api/scenes").json()["scenes"]

    assert {scene["title"]: scene["agent_count"] for scene in scenes} == {
        "两人场景": 2,
        "三人场景": 3,
    }
    assert all(scene["status"] == "READY" for scene in scenes)
    assert all(scene["budget_locked"] is False for scene in scenes)


# --- 锁定 ----------------------------------------------------------------------


def test_locked_scene_rejects_agent_mutations(api_client: TestClient) -> None:
    template_ids = make_templates(api_client, ["安然", "许川", "陈禾"])
    detail = create_scene(api_client, template_ids)
    scene_id = detail["scene"]["scene_id"]

    locked = api_client.app.state.scene_service.lock(scene_id)
    assert locked.budget.locked_at is not None

    assert api_client.get(f"/api/scenes/{scene_id}").json()["locked"] is True
    assert api_client.get("/api/scenes").json()["scenes"][0]["budget_locked"] is True

    extra = make_template(api_client, "阿明")
    added = api_client.post(f"/api/scenes/{scene_id}/agents", json={"template_id": extra})
    renamed = api_client.patch(
        f"/api/scenes/{scene_id}/agents/{detail['agents'][0]['agent_id']}",
        json={"name": "改名"},
    )
    removed = api_client.delete(
        f"/api/scenes/{scene_id}/agents/{detail['agents'][0]['agent_id']}"
    )

    for response in (added, renamed, removed):
        assert response.status_code == 409
        assert response.json()["error"] == "scene_locked"

    # 锁定后角色集合保持不变（PRD 3.2：变化应通过事件表达）。
    assert len(api_client.get(f"/api/scenes/{scene_id}").json()["agents"]) == 3


def test_lock_is_idempotent(services: tuple[TemplateService, SceneService]) -> None:
    template_service, scene_service = services
    first = template_service.create(
        AgentProfileFields(
            name="安然", persona="", speech_style="", initial_goal="", private_background=""
        )
    )
    second = template_service.create(
        AgentProfileFields(
            name="许川", persona="", speech_style="", initial_goal="", private_background=""
        )
    )
    detail = scene_service.create(
        title="锁定幂等",
        background="背景。",
        agent_specs=[
            AgentSpec(template_id=first.template_id),
            AgentSpec(template_id=second.template_id),
        ],
    )

    locked_once = scene_service.lock(detail.scene.scene_id)
    locked_twice = scene_service.lock(detail.scene.scene_id)

    assert locked_once.budget.locked_at == locked_twice.budget.locked_at


# --- 预置场景 ------------------------------------------------------------------


def test_presets_endpoint_exposes_three_scenes(api_client: TestClient) -> None:
    """PRD 10 要求「预置三个场景」；第 3.1 节只定义了第一个，另两个由人工裁决新增。"""

    presets = api_client.get("/api/scenes/presets").json()["presets"]

    assert [preset["key"] for preset in presets] == [
        "roommates",
        "convenience_store",
        "campsite",
    ]
    roommate = presets[0]
    assert roommate["title"] == "三个室友的客厅"
    assert roommate["agent_names"] == ["安然", "许川", "陈禾"]
    # 每个预置场景都是 3 名角色，且角色名互不相同（模板名全局唯一）。
    all_names = [name for preset in presets for name in preset["agent_names"]]
    assert all(len(preset["agent_names"]) == 3 for preset in presets)
    assert len(set(all_names)) == len(all_names) == 9


@pytest.mark.parametrize(
    ("key", "title", "names"),
    [
        ("convenience_store", "深夜便利店的三个顾客", ["林小满", "周远", "郑好"]),
        ("campsite", "周末露营地的三个人", ["何澜", "苏木", "涂山"]),
    ],
)
def test_new_preset_scenes_can_be_created(
    api_client: TestClient, key: str, title: str, names: list[str]
) -> None:
    detail = api_client.post("/api/scenes/preset", json={"preset_key": key}).json()

    assert detail["scene"]["title"] == title
    assert [agent["name"] for agent in detail["agents"]] == names
    assert detail["locked"] is False
    assert detail["scene"]["status"] == "READY"
    # 每名角色都从模板取得了完整快照（私有背景各自独立，不是空壳）。
    assert all(agent["snapshot"]["private_background"] for agent in detail["agents"])
    assert all(agent["snapshot"]["initial_goal"] for agent in detail["agents"])
    # 各自带来源模板 ID，便于追溯。
    assert all(agent["snapshot"]["source_template_id"] for agent in detail["agents"])


def test_preset_scene_only_materialises_its_own_templates(api_client: TestClient) -> None:
    """创建某预置场景不应顺带写入其它场景的模板。"""

    api_client.post("/api/scenes/preset", json={"preset_key": "campsite"})

    names = sorted(t["name"] for t in api_client.get("/api/templates").json()["templates"])
    # 模板列表按名称排序返回（M01 契约），因此用集合语义比较。
    assert names == sorted(["何澜", "苏木", "涂山"])


def test_two_preset_scenes_can_coexist(api_client: TestClient) -> None:
    first = api_client.post("/api/scenes/preset", json={"preset_key": "roommates"}).json()
    second = api_client.post("/api/scenes/preset", json={"preset_key": "convenience_store"}).json()

    assert first["scene"]["scene_id"] != second["scene"]["scene_id"]
    assert len(api_client.get("/api/scenes").json()["scenes"]) == 2
    # 两个场景的 agent_id 互不相同，且各自快照独立。
    ids = {a["agent_id"] for a in first["agents"]} | {a["agent_id"] for a in second["agents"]}
    assert len(ids) == 6


def test_preset_scene_creates_the_three_roommates(api_client: TestClient) -> None:
    detail = api_client.post("/api/scenes/preset", json={"preset_key": "roommates"}).json()

    assert detail["scene"]["title"] == "三个室友的客厅"
    assert detail["scene"]["background"] == "晚上，三个室友在客厅相遇，尚未确定今晚做什么。"
    assert [agent["name"] for agent in detail["agents"]] == ["安然", "许川", "陈禾"]

    by_name = {agent["name"]: agent for agent in detail["agents"]}
    assert by_name["安然"]["snapshot"]["initial_goal"] == "想找人一起度过晚上。"
    assert by_name["安然"]["snapshot"]["private_background"] == "朋友临时取消了聚会。"
    assert by_name["许川"]["snapshot"]["private_background"] == "今天工作很累。"
    # PRD 3.1 未给出陈禾的私有背景：留空，不编造具体私有事实。
    assert by_name["陈禾"]["snapshot"]["private_background"] == ""
    assert by_name["陈禾"]["snapshot"]["initial_goal"] == "想融入，但不想打扰别人。"


def test_preset_scene_can_be_created_repeatedly(api_client: TestClient) -> None:
    first = api_client.post("/api/scenes/preset", json={}).json()
    second = api_client.post("/api/scenes/preset", json={}).json()

    assert first["scene"]["scene_id"] != second["scene"]["scene_id"]
    assert len(api_client.get("/api/scenes").json()["scenes"]) == 2
    # 预置模板被复用而不是重复创建。
    assert [t["name"] for t in api_client.get("/api/templates").json()["templates"]] == [
        "安然",
        "许川",
        "陈禾",
    ]


def test_unknown_preset_key_returns_404(api_client: TestClient) -> None:
    response = api_client.post("/api/scenes/preset", json={"preset_key": "nope"})

    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_scene_creation_rejects_extra_fields(api_client: TestClient) -> None:
    template_ids = make_templates(api_client, ["安然", "许川"])
    response = api_client.post(
        "/api/scenes",
        json={
            "title": "多余字段",
            "background": "背景。",
            "agents": [{"template_id": tid} for tid in template_ids],
            "scene_id": "scn_injected",
        },
    )

    assert response.status_code == 422
