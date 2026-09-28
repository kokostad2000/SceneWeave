"""Six fixed localization calls through the application and pinned upstream.

Default is a fake SDK. --live is required for paid analysis; role actions stay Mock.
Capture only explicit safe fields, never serialize an SDK object or configuration.
"""
from __future__ import annotations

import argparse
import atexit
import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from fastapi.testclient import TestClient

from role_theater.analysis.external import build_upstream_port
from role_theater.config import Settings
from role_theater.contracts import ActionDraft, ActionType
from role_theater.main import create_app
from role_theater.ports import MockModelPort
from role_theater.ports.token_limit import MESSAGE_OVERHEAD_RESERVE, check_single_call_token_limit


EXPLICIT = [
    "对不起，刚才我把你们买的饮料弄洒了，我会擦干净。",
    "晚饭吃什么我都可以，你们决定吧。",
    "我再解释一遍：费用按三个人平分，不是由一个人全部承担。",
    "对不起，擦桌子时我又把你的纸碰湿了，我把它换掉。",
    "看哪部电影也随便，我不选，你们定就好。",
    "我再说一次刚才的意思：总费用分成三份，每个人付一份。",
]
DISTRACTION = [
    EXPLICIT[0],
    "我说杯子要放稳，你还弄洒！别拿道歉敷衍我，你这点小事都做不好！",
    "我在公司主持过十次大型会议，有五年管理经验，这里应当由我来定。",
    EXPLICIT[3],
    "刚才已经指出你粗心了，你还碰湿纸！你说什么我都不想听！",
    "再强调一次，我拿过三次优秀管理奖，有五年管理经验，我比你们更懂安排。",
]
CASES = [
    {"id": "L1", "group": "explicit", "target": 0,
     "expected_behavior": "两次具体失误后的道歉", "texts": EXPLICIT},
    {"id": "L2", "group": "explicit", "target": 1,
     "expected_behavior": "两次不表达偏好并交出选择", "texts": EXPLICIT},
    {"id": "L3", "group": "explicit", "target": 2,
     "expected_behavior": "重复解释费用平分", "texts": EXPLICIT},
    {"id": "L4", "group": "distraction", "target": 0,
     "expected_behavior": "只分析安然的道歉，不归入许川的攻击或陈禾的资历", "texts": DISTRACTION},
    {"id": "L5", "group": "sparse-alone", "target": 0,
     "expected_behavior": "单个嗯不足以推断稳定行为模式", "texts": ["嗯。"]},
    {"id": "L6", "group": "sparse-context", "target": 0,
     "expected_behavior": "收到不足以归入其他角色的反复道歉或资历强调",
     "texts": ["收到。", "对不起刚才弄洒饮料，对不起又碰湿纸，我来收拾。",
               "我有五年经验，我拿过三次奖，再说一遍我有五年经验。"]},
]


def build_tag_trace(raw_model: dict, normalized_tags: list[str] | None,
                    final_labels: list[str]) -> dict:
    """Inspect raw tag types without replacing or interpreting malformed evidence."""
    parsed = raw_model.get("parsed_content")
    raw_tags = parsed.get("tags") if isinstance(parsed, dict) else None
    error = raw_model.get("content_parse_error")
    if error is None:
        if not isinstance(parsed, dict):
            error = "expected_json_object"
        elif not isinstance(raw_tags, list):
            error = "expected_tags_list"
        elif not all(isinstance(tag, str) for tag in raw_tags):
            error = "expected_string_tags"
    return {
        "raw": raw_tags,
        "normalized": normalized_tags,
        "final": final_labels,
        "raw_structure_error": error,
        "removed_by_normalization": (
            [tag for tag in raw_tags if tag not in normalized_tags]
            if error is None and normalized_tags is not None else None
        ),
    }


def snapshot(api, scene_id, agents):
    state = api.get(f"/api/scenes/{scene_id}/state").json()
    state.pop("analysis_requests_used", None)  # Only the separate paid budget may change.
    timeline = api.get(f"/api/scenes/{scene_id}/timeline").json()
    timeline.pop("analysis_requests_used", None)
    return {
        "state": state,
        "scene": api.get(f"/api/scenes/{scene_id}").json(),
        "timeline": timeline,
        "agents": api.get(f"/api/scenes/{scene_id}/agents/status").json(),
        "viewpoints": [api.get(
            f"/api/scenes/{scene_id}/agents/{a['agent_id']}/viewpoint"
        ).json() for a in agents],
    }


class Capture:
    def __init__(self, port, *, live, maximum_attempts):
        self.port = port
        self.live = live
        self.current = None
        self.attempts = 0
        self.maximum_attempts = maximum_attempts
        original_ensure = port.client._ensure_sdk

        def ensure():
            sdk = original_ensure() if self.live else None

            async def create(**kwargs):
                if self.attempts >= self.maximum_attempts:
                    raise RuntimeError("定位测试达到指定样例请求数，禁止隐式追加")
                check_single_call_token_limit(kwargs["messages"], kwargs["max_tokens"])
                self.attempts += 1
                self.current["provider_request"] = {
                    k: kwargs[k] for k in (
                        "model", "messages", "max_tokens", "temperature", "response_format",
                        "stream", "extra_body"
                    ) if k in kwargs
                }
                self.current["conservative_token_upper_bound"] = (
                    len(json.dumps(kwargs["messages"], ensure_ascii=False,
                                   separators=(",", ":")).encode("utf-8"))
                    + MESSAGE_OVERHEAD_RESERVE + kwargs["max_tokens"]
                )
                if self.live:
                    response = await sdk.chat.completions.create(**kwargs)
                else:
                    tags = {"L1": ["repeated_apology"], "L2": ["decision_delegation"],
                            "L3": ["repeated_explanation"], "L4": ["repeated_apology"]}
                    content = json.dumps({
                        "tags": tags.get(self.current["id"], []),
                        "mechanisms": [{"name": "situational_stress",
                                        "explanation": "假 SDK 工程检查", "confidence": 0.2}],
                        "alternative_explanations": [
                            {"perspective": "情境", "reasoning": "假 SDK 工程检查之一"},
                            {"perspective": "信息", "reasoning": "假 SDK 工程检查之二"}],
                        "confidence": 0.2, "universality_rating": "低",
                    }, ensure_ascii=False)
                    response = SimpleNamespace(
                        id="fake-localization", model=kwargs["model"],
                        choices=[SimpleNamespace(finish_reason="stop",
                                                 message=SimpleNamespace(content=content))],
                        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50,
                                              prompt_tokens_details=SimpleNamespace(cached_tokens=0)))
                content = response.choices[0].message.content
                parse_error = None
                try:
                    parsed = json.loads(content)
                except (ValueError, TypeError):
                    parsed = None
                    parse_error = "invalid_json"
                self.current["raw_model"] = {
                    "request_id": response.id, "returned_model": response.model,
                    "finish_reason": response.choices[0].finish_reason,
                    "content": content, "parsed_content": parsed,
                    "content_parse_error": parse_error,
                }
                return response

            return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

        port.client._ensure_sdk = ensure
        original_analyze = port._analyzer.analyze

        async def analyze(request):
            self.current["upstream_request"] = {
                "behavior_description": request.behavior_description,
                "context": request.context, "persist_profile": request.persist_profile,
                "subject_id": request.subject_id,
            }
            result = await original_analyze(request)
            self.current["normalized_upstream"] = result.model_dump(mode="json")
            return result

        port._analyzer.analyze = analyze

        def forbidden_update(**kwargs):
            self.current["profile_write_attempted"] = True
            raise RuntimeError("分析测试禁止画像写入")

        port._analyzer._profile_store.update = forbidden_update


def run(args):
    cases = [case for case in CASES if case["id"] in args.cases]
    settings = Settings(analysis_enabled=True) if args.live else Settings(
        _env_file=None, model_provider="deepseek", model_api_key="placeholder-not-real",
        analysis_enabled=True,
    )
    if args.live and (not settings.model_configured or settings.resolved_provider != "deepseek"):
        print("真实定位测试未执行：既有 DeepSeek 配置不可用。", flush=True)
        return 2
    port = build_upstream_port(
        provider="deepseek", api_key=settings.model_api_key.get_secret_value()
        if settings.model_api_key else None,
        base_url=settings.model_base_url or "https://api.deepseek.com", model=settings.model_name,
    )
    capture = Capture(port, live=args.live, maximum_attempts=len(cases))
    record = {
        "started_at": datetime.now(UTC).isoformat(),
        "engine": "live-analysis-mock-dialogue" if args.live else "fake-sdk-mock-dialogue",
        "model_configured": settings.model_configured,
        "credential_source": settings.model_credential_source,
        "allowed_tags": sorted(port._analyzer._allowed_tags), "cases": [],
        "selected_cases": [case["id"] for case in cases],
        "semantic_review": "pending; engineering checks do not establish semantic quality",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise ValueError("证据文件已存在，禁止覆盖原始测试")

    def save():
        args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")

    atexit.register(save)  # Preserve partial safe evidence even on harness failure.

    model = MockModelPort()
    with TemporaryDirectory(prefix="sceneweave-analysis-") as temp:
        app = create_app(settings.model_copy(update={
            "database_url": f"sqlite:///{temp}/localization.db"}),
            model_port=model, analysis_port=port)
        with TestClient(app) as api:
            scenes = {}
            for case in cases:
                if case["group"] not in scenes:
                    # Fresh fixed script, one committed SPEAK per supplied line.
                    scripted = MockModelPort(script=[ActionDraft(action=ActionType.SPEAK, text=t)
                                                     for t in case["texts"]])
                    app.state.scene_runner._model = scripted
                    response = api.post("/api/scenes/preset", json={"preset_key": "roommates"})
                    response.raise_for_status()
                    detail = response.json()
                    scene_id = detail["scene"]["scene_id"]
                    for n in range(len(case["texts"])):
                        step = api.post(f"/api/scenes/{scene_id}/commands", json={
                            "request_id": f"{case['group']}-{n}", "command": "STEP"})
                        step.raise_for_status()
                        assert step.json()["accepted"], step.json()
                    timeline = api.get(f"/api/scenes/{scene_id}/timeline").json()["entries"]
                    assert [e["message"]["text"] for e in timeline] == case["texts"]
                    assert [e["author_name"] for e in timeline] == [
                        detail["agents"][n % 3]["name"] for n in range(len(timeline))]
                    scenes[case["group"]] = (detail, timeline)
                detail, timeline = scenes[case["group"]]
                scene_id = detail["scene"]["scene_id"]
                agents = detail["agents"]
                target = agents[case["target"]]
                item = {k: case[k] for k in ("id", "group", "expected_behavior")}
                item.update(target_name=target["name"], target_id=target["agent_id"],
                            public_materials=timeline, profile_write_attempted=False)
                record["cases"].append(item)
                capture.current = item
                # The injected port is reused for capture; production constructs a fresh port.
                port.client.attempts.clear()
                before = snapshot(api, scene_id, agents)
                result = api.post(f"/api/scenes/{scene_id}/analyses", json={
                    "agent_id": target["agent_id"], "material_seqs": [e["seq"] for e in timeline]})
                result.raise_for_status()
                item["project_api"] = final = result.json()
                after = snapshot(api, scene_id, agents)
                item["changed_snapshot_sections"] = [k for k in before if before[k] != after[k]]
                upstream = item.get("normalized_upstream", {})
                report = final["report"]
                safe_layers = json.dumps({k: item.get(k) for k in (
                    "provider_request", "raw_model", "normalized_upstream", "project_api")},
                    ensure_ascii=False)
                private = [a["snapshot"]["private_background"] for a in agents]
                own = [e["message"]["text"] for e in timeline if e["message"]["actor_id"] == target["agent_id"]]
                others = [e["message"]["text"] for e in timeline if e["message"]["actor_id"] != target["agent_id"]]
                request = item.get("upstream_request", {})
                item["tag_trace"] = build_tag_trace(
                    item.get("raw_model", {}), upstream.get("tags"), report["behavior_labels"])
                checks = {
                    "raw_model_tag_structure_valid": item["tag_trace"]["raw_structure_error"] is None,
                    "scene_state_timeline_all_viewpoints_unchanged": before == after,
                    "exactly_one_provider_attempt": final["provider_attempts"] == 1,
                    "persist_profile_false": item.get("upstream_request", {}).get("persist_profile") is False,
                    "no_profile_write": not item["profile_write_attempted"] and not upstream.get("profile_persisted", False),
                    "no_private_background_in_any_layer": not any(p and p in safe_layers for p in private),
                    "private_background_probe_present": any(private),
                    "target_speech_isolated": all(t in request.get("behavior_description", "") for t in own)
                        and all(t not in request.get("behavior_description", "") for t in others),
                    "other_speech_context_only": all(t in (request.get("context") or "") for t in others)
                        and all(t not in (request.get("context") or "") for t in own),
                    "target_identity_present": request.get("behavior_description", "").startswith(
                        f"分析对象：{target['name']}。"),
                    "labels_preserved": upstream.get("tags") == report["behavior_labels"],
                    "labels_legal": set(report["behavior_labels"]) <= port._analyzer._allowed_tags,
                    "correct_status_mapping": final["status"] == (
                        "DEGRADED" if report["degradation_flags"] else "NORMAL"),
                    "upstream_flags_preserved": set(upstream.get("degradation_flags", [])) <= set(report["degradation_flags"]),
                    "known_usage_within_single_call_limit": all(
                        report["usage"][k] is not None for k in ("input_tokens", "output_tokens"))
                        and sum(report["usage"][k] or 0 for k in ("input_tokens", "output_tokens")) <= 10_000_000,
                    "api_record_persisted": api.get(f"/api/scenes/{scene_id}/analyses").json()["records"][-1] == final,
                }
                item["engineering_checks"] = checks
                item["usage"] = report["usage"]
                save()
                print(json.dumps({"case": case["id"], "target": target["name"],
                                  "status": final["status"], "labels": report["behavior_labels"],
                                  "flags": report["degradation_flags"],
                                  "raw_structure_error": item["tag_trace"]["raw_structure_error"],
                                  "failed_engineering_checks": [k for k, v in checks.items() if not v],
                                  "usage": item["usage"]}, ensure_ascii=False), flush=True)
    record["completed_at"] = datetime.now(UTC).isoformat()
    record["provider_attempts"] = capture.attempts
    record["engineering_passed"] = all(all(c["engineering_checks"].values()) for c in record["cases"])
    save()
    atexit.unregister(save)
    return 0 if record["engineering_passed"] and capture.attempts == len(cases) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", nargs="+", choices=[case["id"] for case in CASES],
                        default=[case["id"] for case in CASES])
    raise SystemExit(run(parser.parse_args()))
