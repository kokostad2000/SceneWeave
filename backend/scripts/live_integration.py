"""真实 DeepSeek API 端到端联调（PRD 第 10 节的「真实验收」）。

与 `live_smoke.py` 的区别：`live_smoke.py` 只验证一次模型调用；本脚本用**真实
DeepSeek 端口**跑完整应用栈——建场景、真实三人聊天、定向事件、读时间线／视角，
并把**不含密钥**的证据写入 `state/reports/live/`。

两项前置条件（缺任一即拒绝运行，绝不回退成 Mock 后宣称通过）：

1. ``--live``
2. 项目配置中存在可用的 DeepSeek 模型凭证

用法::

    cd backend
    .venv/bin/python scripts/live_integration.py --live --turns 3

凭证可由项目 `.env` 或环境变量提供；**不要把密钥粘贴到对话里**。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

EXIT_MISSING_SWITCH = 2
EXIT_MISSING_KEY = 3
EXIT_SCENE_FAILED = 4

DEFAULT_TURNS = 3


def _preflight(args: argparse.Namespace, settings) -> int | None:
    if not args.live:
        print("未提供 --live：真实联调不会执行。", file=sys.stderr)
        print("该项按 PRD 10 记为「未验证」，不得用 Mock 结果替代。", file=sys.stderr)
        return EXIT_MISSING_SWITCH
    if settings.resolved_provider != "deepseek" or not settings.model_api_key_present:
        print("缺项：未配置可用的 DeepSeek 模型凭证。", file=sys.stderr)
        print(
            "请在项目 .env 或你自己的终端配置；不要把密钥粘贴到对话中。",
            file=sys.stderr,
        )
        return EXIT_MISSING_KEY
    return None


async def _drive(app, turns: int, *, preset_key: str = "roommates",
                 after_event_turns: int = 6, with_analysis: bool = False,
                 engine: str = "live-deepseek") -> dict:
    """用真实端口驱动应用栈（不经过网络层，但经过完整业务链路）。"""

    from fastapi.testclient import TestClient

    record: dict = {
        "started_at": datetime.now(UTC).isoformat(),
        "engine": engine,
        "turns_requested": turns,
        "preset_key": preset_key,
    }

    with TestClient(app) as client:
        health = client.get("/api/health").json()
        record["health"] = health

        created = client.post("/api/scenes/preset", json={"preset_key": preset_key})
        created.raise_for_status()
        detail = created.json()
        scene_id = detail["scene"]["scene_id"]
        record["scene"] = {
            "scene_id": scene_id,
            "title": detail["scene"]["title"],
            "agents": [agent["name"] for agent in detail["agents"]],
            "max_role_requests": detail["scene"]["budget"]["max_role_requests"],
        }

        steps: list[dict] = []
        for index in range(turns):
            ack = client.post(
                f"/api/scenes/{scene_id}/commands",
                json={"request_id": f"live-step-{index}", "command": "STEP"},
            ).json()
            state = client.get(f"/api/scenes/{scene_id}/state").json()
            steps.append(
                {
                    "step": index + 1,
                    "accepted": ack["accepted"],
                    "run_state": ack["run_state"],
                    "pause_reason": ack["pause_reason"],
                    "detail": ack["detail"],
                    "role_requests_used": state["role_requests_used"],
                }
            )
            if ack["run_state"] == "ENDED":
                break
        record["steps"] = steps

        timeline = client.get(f"/api/scenes/{scene_id}/timeline").json()
        record["timeline"] = [
            {
                "kind": entry["kind"],
                "seq": entry["seq"],
                "author": entry["author_name"],
                "text": (entry["message"] or {}).get("text"),
                "event": (entry["event"] or {}).get("body"),
            }
            for entry in timeline["entries"]
        ]
        record["initial_authors"] = [
            entry["author_name"] for entry in timeline["entries"] if entry["kind"] == "message"
        ]
        record["role_requests_used"] = timeline["role_requests_used"]

        # 定向事件：既验证视角隔离，也确认目标角色后来处理了事件序号。
        target = detail["agents"][1]
        event_marker = "客厅窗边的水管漏水"
        event_body = (
            f"你的手机收到物业紧急通知：{event_marker}，今晚需要有人处理；"
            "其他室友还不知道这条通知。"
        )
        event_ack = client.post(
            f"/api/scenes/{scene_id}/events",
            json={
                "request_id": "live-event-1",
                "body": event_body,
                "visibility": "TARGETED",
                "target_agent_id": target["agent_id"],
            },
        ).json()
        record["event"] = {
            "accepted": event_ack["accepted"],
            "status": event_ack["event_status"],
            "target": target["name"],
            "event_id": event_ack["event_id"],
            "body": event_body,
        }
        events = client.get(f"/api/scenes/{scene_id}/events").json()
        recorded_event = next(
            (item["event"] for item in events if item["event"]["event_id"] == event_ack["event_id"]),
            None,
        )
        event_seq = recorded_event["seq"] if recorded_event else None
        record["event"]["seq"] = event_seq

        leakage = {}
        for agent in detail["agents"]:
            viewpoint = client.get(
                f"/api/scenes/{scene_id}/agents/{agent['agent_id']}/viewpoint"
            ).json()
            leakage[agent["name"]] = event_marker in viewpoint["prompt"]
        record["targeted_event_visibility"] = leakage

        after_event: list[dict] = []
        for index in range(after_event_turns):
            step = client.post(
                f"/api/scenes/{scene_id}/commands",
                json={"request_id": f"live-after-event-{index}", "command": "STEP"},
            ).json()
            statuses = client.get(f"/api/scenes/{scene_id}/agents/status").json()["agents"]
            target_status = next(item for item in statuses if item["agent_id"] == target["agent_id"])
            processed = target_status["processed_seq"]
            after_event.append({
                "accepted": step["accepted"],
                "run_state": step["run_state"],
                "target_processed_seq": processed,
                "target_processed_event": event_seq is not None and processed >= event_seq,
            })
            if after_event[-1]["target_processed_event"] or not step["accepted"]:
                break
        record["after_event_steps"] = after_event

        summary = client.get(f"/api/scenes/{scene_id}/summary").json()
        record["summary"] = summary

        # 分析只在明确指定时调用，避免每场质量观察都额外计费。
        if with_analysis:
            seqs = [entry["seq"] for entry in timeline["entries"] if entry["kind"] == "message"][:3]
            analysis = client.post(
                f"/api/scenes/{scene_id}/analyses",
                json={"agent_id": detail["agents"][0]["agent_id"], "material_seqs": seqs},
            ).json()
            record["analysis"] = {
                "status": analysis["status"],
                "provider_attempts": analysis["provider_attempts"],
                "error": analysis["error"],
                "degradation_flags": analysis["degradation_flags"],
            }

        refreshed = client.get(f"/api/scenes/{scene_id}/timeline").json()
        record["timeline"] = [
            {
                "kind": entry["kind"], "seq": entry["seq"],
                "author": entry["author_name"],
                "text": (entry["message"] or {}).get("text"),
                "event": (entry["event"] or {}).get("body"),
            }
            for entry in refreshed["entries"]
        ]
        record["target_post_event_messages"] = [
            {"seq": entry["seq"], "text": entry["text"]}
            for entry in record["timeline"]
            if entry["kind"] == "message"
            and entry["author"] == target["name"]
            and event_seq is not None
            and entry["seq"] > event_seq
        ]
        record["target_mentions_event_marker"] = any(
            "漏水" in entry["text"]
            for entry in record["target_post_event_messages"]
        )

        record["run_state_final"] = client.get(f"/api/scenes/{scene_id}/state").json()["status"]

    record["finished_at"] = datetime.now(UTC).isoformat()
    return record


async def _drive_quality(app, *, preset_key: str, turns: int = 3) -> dict:
    """Collect one three-person sample without an event or analysis call."""
    from fastapi.testclient import TestClient

    record = {
        "started_at": datetime.now(UTC).isoformat(),
        "engine": "live-deepseek",
        "purpose": "quality-observation-sample",
        "preset_key": preset_key,
        "turns_requested": turns,
    }
    with TestClient(app) as client:
        created = client.post("/api/scenes/preset", json={"preset_key": preset_key})
        created.raise_for_status()
        detail = created.json()
        scene_id = detail["scene"]["scene_id"]
        record["scene"] = {"scene_id": scene_id, "title": detail["scene"]["title"]}
        record["steps"] = []
        for index in range(turns):
            ack = client.post(
                f"/api/scenes/{scene_id}/commands",
                json={"request_id": f"quality-step-{index}", "command": "STEP"},
            ).json()
            record["steps"].append({
                "accepted": ack["accepted"],
                "run_state": ack["run_state"],
                "pause_reason": ack["pause_reason"],
            })
            if not ack["accepted"] or ack["run_state"] == "ENDED":
                break
        timeline = client.get(f"/api/scenes/{scene_id}/timeline").json()
        record["timeline"] = [
            {"seq": entry["seq"], "kind": entry["kind"],
             "author": entry["author_name"],
             "text": (entry["message"] or {}).get("text")}
            for entry in timeline["entries"]
        ]
        agent_names = {agent["agent_id"]: agent["name"] for agent in detail["agents"]}
        record["actions"] = [
            {
                "step": index + 1,
                "actor": agent_names.get(turn["actor_id"]),
                "status": turn["status"],
                "action": turn["action"],
                "input_tokens": turn["input_tokens"],
                "output_tokens": turn["output_tokens"],
            }
            for index, turn in enumerate(client.app.state.runtime_repository.list_turns(scene_id))
        ]
        record["summary"] = client.get(f"/api/scenes/{scene_id}/summary").json()
    record["finished_at"] = datetime.now(UTC).isoformat()
    return record


def _quality_sample_met(record: dict) -> bool:
    # PASS 是允许沉默的正常行动；每份样本无需强迫三人都发言。
    summary = record["summary"]
    return (
        len(record["steps"]) >= 3
        and all(step["accepted"] for step in record["steps"])
        and summary["role_requests_used"] >= 3
        and summary["succeeded"] >= 3
        and summary["failed"] == 0
        and summary["unknown"] == 0
        and all(action["status"] == "SUCCEEDED" for action in record.get("actions", []))
    )


def _acceptance_met(record: dict, *, initial_turns: int, with_analysis: bool) -> bool:
    initial_authors = set(record["initial_authors"][:initial_turns])
    target = record["event"]["target"]
    visibility = record["targeted_event_visibility"]
    event_ok = (
        record["event"]["accepted"]
        and record["event"]["status"] == "EFFECTIVE"
        and record["event"]["seq"] is not None
        and visibility.get(target) is True
        and all(not seen for name, seen in visibility.items() if name != target)
        and any(item["target_processed_event"] for item in record["after_event_steps"])
    )
    analysis_ok = not with_analysis or (
        record.get("analysis", {}).get("status") == "NORMAL"
        and record["analysis"]["provider_attempts"] >= 1
    )
    return len(initial_authors) >= 3 and event_ok and analysis_ok


def main() -> int:
    parser = argparse.ArgumentParser(description="真实 DeepSeek API 端到端联调")
    parser.add_argument("--live", action="store_true", help="显式开启真实调用")
    parser.add_argument("--turns", type=int, default=DEFAULT_TURNS, help="先跑几次单步")
    parser.add_argument("--preset", choices=("roommates", "convenience_store", "campsite"),
                        default="roommates")
    parser.add_argument("--after-event-turns", type=int, default=6,
                        help="定向事件后最多运行几次单步")
    parser.add_argument("--with-analysis", action="store_true",
                        help="显式增加一次真实行为分析调用")
    parser.add_argument("--quality-only", action="store_true",
                        help="只留三人对话样本，不注入事件或调用分析")
    parser.add_argument("--model", default=None, help="覆盖模型名（默认取契约初值）")
    parser.add_argument("--out", default=None, help="证据输出路径（不含密钥）")
    args = parser.parse_args()

    if not args.live:
        return _preflight(args, None)

    from role_theater.config import Settings

    settings = Settings()
    blocked = _preflight(args, settings)
    if blocked is not None:
        return blocked
    if args.turns < 3 or args.after_event_turns < 1:
        print("真实三人聊天至少需要 3 次单步，事件后至少需要 1 次单步。", file=sys.stderr)
        return EXIT_MISSING_SWITCH
    if args.quality_only and args.with_analysis:
        print("质量留样模式不执行行为分析；请单独运行专项验收。", file=sys.stderr)
        return EXIT_MISSING_SWITCH

    from role_theater.main import create_app
    from role_theater.ports import build_model_port

    if args.model:
        # 模型名经配置注入运行器（SCENEWEAVE_MODEL_NAME 的真实生效路径）。
        settings = settings.model_copy(update={"model_name": args.model})
    port = build_model_port(
        api_key=settings.model_api_key.get_secret_value() if settings.model_api_key else None,
        base_url=settings.model_base_url,
        force_mock=False,
    )
    output = (
        Path(args.out)
        if args.out
        else REPO_ROOT / "state" / "reports" / "live" /
        f"live-{'quality' if args.quality_only else 'integration'}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    settings = settings.model_copy(update={
        "database_url": f"sqlite:///{output.with_suffix('.db').resolve()}",
        "analysis_enabled": args.with_analysis,
    })
    app = create_app(settings, model_port=port)
    if args.quality_only:
        record = asyncio.run(_drive_quality(app, preset_key=args.preset, turns=args.turns))
    else:
        record = asyncio.run(_drive(
            app, args.turns, preset_key=args.preset,
            after_event_turns=args.after_event_turns, with_analysis=args.with_analysis,
        ))
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False, indent=2))
    print(f"\n证据已写入 {output}（不含密钥）")

    accepted = (
        _quality_sample_met(record) if args.quality_only
        else _acceptance_met(record, initial_turns=args.turns, with_analysis=args.with_analysis)
    )
    if not accepted:
        print("真实验收条件未全部满足；请检查三人聊天、定向事件及分析结果。", file=sys.stderr)
        return EXIT_SCENE_FAILED
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
