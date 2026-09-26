"""M01 角色模板（PRD 3.2、3.3；tasks/M01.md A1、A4）。"""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from role_theater.domain import DuplicateNameError, TemplateService

FULL_PROFILE = {
    "name": "安然",
    "persona": "主动热情，愿意张罗。",
    "speech_style": "热情、主动提问。",
    "initial_goal": "想找人一起度过今晚。",
    "private_background": "朋友临时取消了聚会。",
}


def _create(client: TestClient, **overrides: str) -> dict:
    payload = {**FULL_PROFILE, **overrides}
    response = client.post("/api/templates", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_template_echoes_the_five_fields(api_client: TestClient) -> None:
    body = _create(api_client)

    assert body["name"] == "安然"
    assert body["persona"] == FULL_PROFILE["persona"]
    assert body["speech_style"] == FULL_PROFILE["speech_style"]
    assert body["initial_goal"] == FULL_PROFILE["initial_goal"]
    assert body["private_background"] == FULL_PROFILE["private_background"]
    assert body["template_id"].startswith("tpl_")
    assert body["created_at"] == body["updated_at"]


def test_template_is_listed_and_fetchable(api_client: TestClient) -> None:
    created = _create(api_client)

    listed = api_client.get("/api/templates").json()["templates"]
    assert [item["template_id"] for item in listed] == [created["template_id"]]

    fetched = api_client.get(f"/api/templates/{created['template_id']}")
    assert fetched.status_code == 200
    assert fetched.json() == created


def test_unknown_template_returns_404(api_client: TestClient) -> None:
    response = api_client.get("/api/templates/tpl_missing")

    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_duplicate_template_name_returns_409(api_client: TestClient) -> None:
    _create(api_client)
    response = api_client.post("/api/templates", json=FULL_PROFILE)

    assert response.status_code == 409
    assert response.json()["error"] == "duplicate_name"


def test_update_changes_only_provided_fields(api_client: TestClient) -> None:
    created = _create(api_client)

    response = api_client.patch(
        f"/api/templates/{created['template_id']}",
        json={"persona": "改过的人物设定。"},
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["persona"] == "改过的人物设定。"
    assert updated["name"] == created["name"]
    assert updated["private_background"] == created["private_background"]
    assert updated["created_at"] == created["created_at"]


def test_update_to_existing_name_returns_409(api_client: TestClient) -> None:
    first = _create(api_client)
    _create(api_client, name="许川")

    response = api_client.patch(
        f"/api/templates/{first['template_id']}", json={"name": "许川"}
    )

    assert response.status_code == 409
    assert response.json()["error"] == "duplicate_name"


def test_update_with_same_name_is_allowed(api_client: TestClient) -> None:
    created = _create(api_client)

    response = api_client.patch(
        f"/api/templates/{created['template_id']}",
        json={"name": created["name"], "initial_goal": "改过的目标。"},
    )

    assert response.status_code == 200
    assert response.json()["initial_goal"] == "改过的目标。"


def test_copy_auto_renames_to_a_non_duplicate(api_client: TestClient) -> None:
    created = _create(api_client)

    first = api_client.post(f"/api/templates/{created['template_id']}/copy", json={})
    second = api_client.post(f"/api/templates/{created['template_id']}/copy", json={})

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["name"] == "安然（副本）"
    assert second.json()["name"] == "安然（副本2）"
    # 复制保留其余四项内容。
    assert first.json()["private_background"] == created["private_background"]
    assert first.json()["template_id"] != created["template_id"]


def test_copy_with_duplicate_explicit_name_returns_409(api_client: TestClient) -> None:
    created = _create(api_client)

    response = api_client.post(
        f"/api/templates/{created['template_id']}/copy", json={"name": "安然"}
    )

    assert response.status_code == 409
    assert response.json()["error"] == "duplicate_name"


def test_copy_of_unknown_template_returns_404(api_client: TestClient) -> None:
    response = api_client.post("/api/templates/tpl_missing/copy", json={})

    assert response.status_code == 404


def test_delete_removes_the_template(api_client: TestClient) -> None:
    created = _create(api_client)

    assert api_client.delete(f"/api/templates/{created['template_id']}").status_code == 204
    assert api_client.get(f"/api/templates/{created['template_id']}").status_code == 404
    assert api_client.get("/api/templates").json()["templates"] == []

    assert api_client.delete(f"/api/templates/{created['template_id']}").status_code == 404


def test_name_is_trimmed_and_length_is_counted_in_codepoints(api_client: TestClient) -> None:
    created = _create(api_client, name="  许川  ")
    assert created["name"] == "许川"

    # 30 码点可以，31 不行（含 emoji，按码点而非 UTF-16 计）。
    assert api_client.post(
        "/api/templates", json={**FULL_PROFILE, "name": "字" * 30}
    ).status_code == 201
    assert api_client.post(
        "/api/templates", json={**FULL_PROFILE, "name": "字" * 31}
    ).status_code == 422
    assert api_client.post(
        "/api/templates", json={**FULL_PROFILE, "name": "😀" * 31}
    ).status_code == 422


def test_field_length_limits_are_enforced(api_client: TestClient) -> None:
    assert api_client.post(
        "/api/templates", json={**FULL_PROFILE, "persona": "人" * 1000}
    ).status_code == 201
    assert api_client.post(
        "/api/templates", json={**FULL_PROFILE, "persona": "人" * 1001}
    ).status_code == 422
    assert api_client.post(
        "/api/templates", json={**FULL_PROFILE, "speech_style": "语" * 301}
    ).status_code == 422
    assert api_client.post(
        "/api/templates", json={**FULL_PROFILE, "initial_goal": "目" * 501}
    ).status_code == 422
    assert api_client.post(
        "/api/templates", json={**FULL_PROFILE, "private_background": "私" * 1001}
    ).status_code == 422


def test_missing_and_extra_fields_are_rejected(api_client: TestClient) -> None:
    payload = {k: v for k, v in FULL_PROFILE.items() if k != "persona"}
    assert api_client.post("/api/templates", json=payload).status_code == 422

    response = api_client.post("/api/templates", json={**FULL_PROFILE, "actor_id": "agent-1"})
    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"


def test_copy_name_respects_the_codepoint_limit(
    services: tuple[TemplateService, object],
) -> None:
    """超长名称复制时必须仍落在 30 码点以内，而不是生成非法名称。"""

    template_service, _ = services
    from role_theater.contracts import AgentProfileFields

    source = template_service.create(
        AgentProfileFields(
            name="长" * 30,
            persona="",
            speech_style="",
            initial_goal="",
            private_background="",
        )
    )
    copy = template_service.copy(source.template_id)

    assert copy.name != source.name
    assert len(copy.name) <= 30
    assert copy.name.endswith("（副本）")


def test_copy_exhausts_suffixes_before_failing(
    services: tuple[TemplateService, object],
) -> None:
    template_service, _ = services
    from role_theater.contracts import AgentProfileFields

    profile = AgentProfileFields(
        name="安然", persona="", speech_style="", initial_goal="", private_background=""
    )
    source = template_service.create(profile)
    names = {template_service.copy(source.template_id).name for _ in range(3)}

    assert names == {"安然（副本）", "安然（副本2）", "安然（副本3）"}


def test_service_uses_the_injected_clock(
    services: tuple[TemplateService, object],
    fixed_clock: Callable[[], object],
) -> None:
    """时间来自注入的时钟，便于确定性断言（也保证不再有隐藏的 now() 调用）。"""

    template_service, _ = services
    from role_theater.contracts import AgentProfileFields

    created = template_service.create(
        AgentProfileFields(
            name="许川", persona="", speech_style="", initial_goal="", private_background=""
        )
    )

    assert created.created_at == created.updated_at == fixed_clock()


def test_unit_service_raises_duplicate_name(
    services: tuple[TemplateService, object],
) -> None:
    import pytest

    from role_theater.contracts import AgentProfileFields

    template_service, _ = services
    profile = AgentProfileFields(
        name="陈禾", persona="", speech_style="", initial_goal="", private_background=""
    )
    template_service.create(profile)

    with pytest.raises(DuplicateNameError):
        template_service.create(profile)


def test_clock_injection_is_used(fixed_clock: Callable[[], object]) -> None:
    """固定时钟夹具本身可用，避免测试间共享可变时间。"""

    assert fixed_clock() == fixed_clock()
