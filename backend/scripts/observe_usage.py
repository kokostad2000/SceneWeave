"""串行真实使用观察；不替代人工质量验收，不做隐式重试。

显式 --live 后使用应用已有配置，运行完整 API/存储/模型/分析链路。
TestClient 不验证浏览器或真实 HTTP 代理。默认三场景各两会话，上限
84 次角色请求、6 次分析请求；每次发送仍由应用检查单次 token 上界。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

EVENTS = {
    "roommates": (
        "客厅灯突然熄灭，物业群通知十分钟后恢复供电。大家可以自行决定等候或离开。",
        "只有你收到物业短信：今晚厨房水管需要关阀检查，其他室友暂时不知道。",
    ),
    "convenience_store": (
        "店外雨势变大，广播说附近末班公交还有五分钟到站。大家可以自行决定接下来做什么。",
        "只有你收到公交提醒：末班车临时提前两分钟，其他人暂时不知道。",
    ),
    "campsite": (
        "营地广播提醒风正在变大，天黑前需要检查帐篷固定。大家可以自行决定怎么安排。",
        "只有你收到营地短信：河边步道即将临时关闭，其他人暂时不知道。",
    ),
}


def save(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def summarize(samples: list[dict]) -> dict:
    all_roles = [row for sample in samples for row in sample["actions"]]
    roles = [row for row in all_roles if row["sent"]]
    uncertain_roles = [row for row in all_roles if row["status"] == "UNKNOWN"]
    analyses = [sample["analysis"] for sample in samples if sample.get("analysis")]
    usage_rows = [row for row in all_roles if row["sent"] or row["status"] == "UNKNOWN"] + [
        item for item in analyses if item["provider_attempts"]
    ]
    return {
        "sessions": len(samples),
        "role_provider_requests": len(roles),
        "role_budget_consumed": sum(row["budget_consumed"] for row in all_roles),
        "role_delivery_unknown": len(uncertain_roles),
        "role_succeeded": sum(row["status"] == "SUCCEEDED" for row in roles),
        "role_failed": sum(row["status"] == "FAILED" for row in all_roles),
        "role_unknown": len(uncertain_roles),
        "speak": sum(row["action"] == "SPEAK" for row in roles),
        "pass": sum(row["action"] == "PASS" for row in roles),
        "analysis_operations": len(analyses),
        "analysis_provider_requests": sum(item["provider_attempts"] for item in analyses),
        "usage_incomplete_records": sum(
            row["input_tokens"] is None or row["output_tokens"] is None for row in usage_rows
        ),
        "known_input_tokens": sum(row["input_tokens"] or 0 for row in usage_rows),
        "known_output_tokens": sum(row["output_tokens"] or 0 for row in usage_rows),
        "actual_single_call_over_limit": sum(
            (row["input_tokens"] or 0) + (row["output_tokens"] or 0) > 10_000_000
            for row in usage_rows
        ),
    }


def observe_session(app, preset: str, repeat: int, *, engine: str = "live-deepseek") -> dict:
    from fastapi.testclient import TestClient

    sample = {
        "engine": engine, "preset_key": preset, "repeat": repeat,
        "started_at": datetime.now(UTC).isoformat(),
        "steps": [], "events": [], "analysis": None,
    }
    with TestClient(app) as client:
        response = client.post("/api/scenes/preset", json={"preset_key": preset})
        response.raise_for_status()
        detail = response.json()
        scene_id = detail["scene"]["scene_id"]
        sample["scene_id"] = scene_id
        sample["title"] = detail["scene"]["title"]
        sample["agents"] = detail["agents"]
        target = detail["agents"][1]
        provider_failed = False

        def steps(phase, count):
            nonlocal provider_failed
            if provider_failed:
                return
            for index in range(count):
                before = client.get(f"/api/scenes/{scene_id}/state").json()
                if before["status"] == "ENDED":
                    break
                start = time.monotonic()
                ack = client.post(f"/api/scenes/{scene_id}/commands", json={
                    "request_id": f"observe-{scene_id}-{phase}-{index}", "command": "STEP",
                })
                ack.raise_for_status()
                body = ack.json()
                sample["steps"].append({
                    "phase": phase, "index": index + 1,
                    "api_elapsed_ms": round((time.monotonic() - start) * 1000),
                    "accepted": body["accepted"], "run_state": body["run_state"],
                    "pause_reason": body["pause_reason"], "detail": body["detail"],
                })
                if not body["accepted"] or body["pause_reason"] == "PROVIDER_ERROR":
                    provider_failed = body["pause_reason"] == "PROVIDER_ERROR"
                    break

        steps("natural", 6)
        for visibility, body, phase in (
            ("ALL", EVENTS[preset][0], "public_event"),
            ("TARGETED", EVENTS[preset][1], "targeted_event"),
        ):
            if provider_failed:
                break
            state = client.get(f"/api/scenes/{scene_id}/state").json()
            if state["status"] == "ENDED":
                break
            event = client.post(f"/api/scenes/{scene_id}/events", json={
                "request_id": f"observe-{scene_id}-{phase}", "body": body,
                "visibility": visibility,
                "target_agent_id": target["agent_id"] if visibility == "TARGETED" else None,
            })
            event.raise_for_status()
            sample["events"].append({"visibility": visibility, "body": body, "ack": event.json()})
            if visibility == "TARGETED" and event.json()["accepted"]:
                sample["targeted_visibility_before_response"] = {
                    agent["name"]: body in client.get(
                        f"/api/scenes/{scene_id}/agents/{agent['agent_id']}/viewpoint"
                    ).json()["prompt"] for agent in detail["agents"]
                }
            steps(phase, 4)

        timeline = client.get(f"/api/scenes/{scene_id}/timeline").json()
        sample["timeline"] = timeline["entries"]
        messages = [entry for entry in timeline["entries"] if entry["kind"] == "message"]
        if messages:
            selected_agent = messages[0]["message"]["actor_id"]
            selected = [entry["seq"] for entry in messages][:6]
            start = time.monotonic()
            response = client.post(f"/api/scenes/{scene_id}/analyses", json={
                "agent_id": selected_agent, "material_seqs": selected,
            })
            response.raise_for_status()
            analysis = response.json()
            usage = analysis["report"]["usage"]
            sample["analysis"] = {
                "agent_id": selected_agent,
                "agent_name": next(a["name"] for a in detail["agents"] if a["agent_id"] == selected_agent),
                "material_seqs": selected,
                "api_elapsed_ms": round((time.monotonic() - start) * 1000),
                "status": analysis["status"], "provider_attempts": analysis["provider_attempts"],
                "degradation_flags": analysis["degradation_flags"],
                "report": analysis["report"],
                "input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"],
            }
        else:
            sample["analysis_not_run_reason"] = "无公开发言材料，未发起分析请求"

        names = {agent["agent_id"]: agent["name"] for agent in detail["agents"]}
        fields = (
            "action_id", "actor_id", "status", "action", "text", "reply_to_message_id",
            "requested_speaker_id", "input_cursor_seq", "prompt_template_id",
            "requested_model", "returned_model", "provider_request_id", "input_tokens",
            "output_tokens", "cached_tokens", "usage_unknown", "failure_kind", "sent",
            "budget_consumed", "latency_ms", "created_at", "finished_at",
        )
        sample["actions"] = [
            {"actor": names[row["actor_id"]], **{key: row[key] for key in fields}}
            for row in app.state.runtime_repository.list_turns(scene_id)
        ]
        sample["summary"] = client.get(f"/api/scenes/{scene_id}/summary").json()
        sample["state_before_stop"] = client.get(f"/api/scenes/{scene_id}/state").json()
        stop = client.post(f"/api/scenes/{scene_id}/commands", json={
            "request_id": f"observe-{scene_id}-stop", "command": "STOP",
        })
        stop.raise_for_status()
        sample["stop"] = stop.json()
    sample["finished_at"] = datetime.now(UTC).isoformat()
    return sample


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--rounds", type=int, choices=(1, 2, 3), default=2)
    parser.add_argument("--out", type=Path, required=True, help="项目内新的证据目录")
    args = parser.parse_args(argv)
    if not args.live:
        print("缺少 --live；未发送请求。")
        return 2
    output = args.out.resolve()
    if not output.is_relative_to(ROOT):
        print("观察证据必须保存在项目内。")
        return 2
    if output.exists() and any(output.iterdir()):
        print("证据目录非空；拒绝覆盖或重复执行原有会话。")
        return 2

    from role_theater.config import Settings
    from role_theater.main import create_app

    settings = Settings()
    if settings.resolved_provider != "deepseek" or not settings.model_api_key_present:
        print("未配置可用的真实 DeepSeek；未发送请求。")
        return 3
    output.mkdir(parents=True, exist_ok=True)
    settings = settings.model_copy(update={
        "model_provider": "deepseek", "model_force_mock": False,
        "analysis_enabled": True, "database_url": f"sqlite:///{output / 'observations.db'}",
    })
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    record = {
        "source_commit": head, "observer": "Codex agent; not human acceptance",
        "scope": "完整应用 API 链路，TestClient；未验证浏览器、HTTP 代理或长期稳定性",
        "latency_definition": "角色 latency_ms 为应用记录的模型请求耗时；api_elapsed_ms 为单步/分析端到端耗时",
        "max_role_requests": args.rounds * 3 * 14,
        "max_analysis_requests": args.rounds * 3,
        "samples": [],
    }
    save(output / "summary.json", record)
    for repeat in range(1, args.rounds + 1):
        for preset in EVENTS:
            sample = observe_session(create_app(settings), preset, repeat)
            save(output / f"{preset}-{repeat}.json", sample)
            record["samples"].append(sample)
            record["totals"] = summarize(record["samples"])
            save(output / "summary.json", record)
            print(json.dumps({"preset": preset, "repeat": repeat, "totals": record["totals"]}, ensure_ascii=False), flush=True)
            if record["totals"]["role_failed"] or record["totals"]["role_unknown"]:
                record["collection_status"] = "stopped_on_provider_error"
                record["finished_at"] = datetime.now(UTC).isoformat()
                save(output / "summary.json", record)
                return 4
    record["finished_at"] = datetime.now(UTC).isoformat()
    record["collection_status"] = "completed"
    save(output / "summary.json", record)
    return 0 if record["totals"]["role_succeeded"] > 0 else 4


if __name__ == "__main__":
    raise SystemExit(main())
