"""契约产物导出与漂移检测（PRD 第 8 节：后端是接口唯一来源）。"""

from __future__ import annotations

import json

from role_theater.contracts import CONTRACT_ENUMS, CONTRACT_MODELS, build_contract_summary

from scripts.export_contracts import (  # type: ignore[import-not-found]
    CONTRACT_SUMMARY_PATH,
    OPENAPI_PATH,
    render_contract_summary,
    render_openapi,
)


def test_openapi_render_is_reproducible() -> None:
    assert render_openapi() == render_openapi()
    assert render_contract_summary() == render_contract_summary()


def test_openapi_contains_m00_routes() -> None:
    spec = json.loads(render_openapi())

    assert spec["info"]["title"] == "SceneWeave"
    assert "/api/health" in spec["paths"]
    assert "/api/contracts/summary" in spec["paths"]


def test_openapi_declares_every_contract_model_and_enum() -> None:
    """前端类型必须能从 OpenAPI 一次性生成，而不是只覆盖 M00 的两个路由。"""

    spec = json.loads(render_openapi())
    schema_names = set(spec["components"]["schemas"])

    for enum_name in CONTRACT_ENUMS:
        assert enum_name in schema_names, f"枚举 {enum_name} 未出现在 OpenAPI schema 中"
    for model_name in CONTRACT_MODELS:
        assert model_name in schema_names, f"契约模型 {model_name} 未出现在 OpenAPI schema 中"


def test_openapi_action_and_event_shapes_are_published() -> None:
    """行动与事件结构必须对外可见（M00 交付项）。"""

    schemas = json.loads(render_openapi())["components"]["schemas"]

    assert set(schemas["ActionDraft"]["properties"]) == {
        "action",
        "text",
        "reply_to_message_id",
        "requested_speaker_id",
        "recipient_id",
    }
    assert set(schemas["Event"]["properties"]) >= {
        "event_id",
        "scene_id",
        "seq",
        "body",
        "visibility",
        "target_agent_id",
        "status",
        "schema_version",
    }


def test_openapi_has_no_unresolved_schema_references() -> None:
    """注入契约 schema 后，所有 ``$ref`` 都必须能解析。"""

    spec = json.loads(render_openapi())
    schemas = spec["components"]["schemas"]

    def walk(node: object) -> list[str]:
        found: list[str] = []
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "$ref" and isinstance(value, str):
                    found.append(value)
                else:
                    found.extend(walk(value))
        elif isinstance(node, list):
            for item in node:
                found.extend(walk(item))
        return found

    for ref in walk(spec):
        prefix = "#/components/schemas/"
        assert ref.startswith(prefix), f"不支持的外部引用 {ref}"
        assert ref[len(prefix) :] in schemas, f"引用无法解析：{ref}"


def test_openapi_never_exposes_secrets_or_settings() -> None:
    text = render_openapi()

    assert "api_key" not in text
    assert "SCENEWEAVE_" not in text


def test_exported_artifacts_match_the_contract_source() -> None:
    """产物必须与契约源码一致；不一致时应重新运行导出脚本，而不是放宽断言。"""

    assert OPENAPI_PATH.exists(), "缺少 backend/openapi.json，请运行 scripts/export_contracts.py"
    assert CONTRACT_SUMMARY_PATH.exists(), (
        "缺少前端契约摘要，请运行 scripts/export_contracts.py"
    )

    assert OPENAPI_PATH.read_text(encoding="utf-8") == render_openapi()
    assert CONTRACT_SUMMARY_PATH.read_text(encoding="utf-8") == render_contract_summary()


def test_exported_summary_matches_model_dump() -> None:
    payload = json.loads(CONTRACT_SUMMARY_PATH.read_text(encoding="utf-8"))

    assert payload == build_contract_summary().model_dump(mode="json")
    assert payload["app_name"] == "SceneWeave"
