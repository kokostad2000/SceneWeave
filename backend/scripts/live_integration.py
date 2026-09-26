"""真实 DeepSeek API 端到端联调（PRD 第 10 节的「真实验收」）。

与 `live_smoke.py` 的区别：`live_smoke.py` 只验证一次模型调用；本脚本用**真实
DeepSeek 端口**跑完整应用栈——建场景、真实三人聊天、定向事件、读时间线／视角，
并把**不含密钥**的证据写入 `state/reports/live/`。

三重前置条件（缺任一即拒绝运行，绝不回退成 Mock 后宣称通过）：

1. ``--live``
2. ``--confirm-spend``（真实调用会产生费用）
3. 环境变量 ``SCENEWEAVE_MODEL_API_KEY``

用法::

    cd backend
    SCENEWEAVE_MODEL_API_KEY=... uv run python scripts/live_integration.py \\
        --live --confirm-spend --turns 3

密钥只从环境变量读取；**不要把密钥写进任何文件或粘贴到对话里**。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
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


def _preflight(args: argparse.Namespace) -> int | None:
    if not args.live:
        print("未提供 --live：真实联调不会执行。", file=sys.stderr)
        print("该项按 PRD 10 记为「未验证」，不得用 Mock 结果替代。", file=sys.stderr)
        return EXIT_MISSING_SWITCH
    if not args.confirm_spend:
        print("未提供 --confirm-spend：拒绝发起可能产生费用的真实调用。", file=sys.stderr)
        return EXIT_MISSING_SWITCH
    if not os.environ.get("SCENEWEAVE_MODEL_API_KEY", "").strip():
        print("缺项：环境变量 SCENEWEAVE_MODEL_API_KEY 为空。", file=sys.stderr)
        print(
            "请在你自己的终端 export 该变量后重跑；不要把密钥写进代码或粘贴到对话中。",
            file=sys.stderr,
        )
        return EXIT_MISSING_KEY
    return None


async def _drive(app, turns: int) -> dict:
    """用真实端口驱动应用栈（不经过网络层，但经过完整业务链路）。"""

    from fastapi.testclient import TestClient

    record: dict = {
        "started_at": datetime.now(UTC).isoformat(),
        "engine": "live-deepseek",
        "turns_requested": turns,
    }

    with TestClient(app) as client:
        health = client.get("/api/health").json()
        record["health"] = health

        created = client.post("/api/scenes/preset", json={"preset_key": "roommates"})
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
        record["role_requests_used"] = timeline["role_requests_used"]

        # 定向事件：真实验证“定向只对被指定角色可见”。
        target = detail["agents"][1]
        event_ack = client.post(
            f"/api/scenes/{scene_id}/events",
            json={
                "request_id": "live-event-1",
                "body": "许川的手机震了一下：同事问明天能不能早到。",
                "visibility": "TARGETED",
                "target_agent_id": target["agent_id"],
            },
        ).json()
        record["event"] = {
            "accepted": event_ack["accepted"],
            "status": event_ack["event_status"],
            "target": target["name"],
        }

        leakage = {}
        for agent in detail["agents"]:
            viewpoint = client.get(
                f"/api/scenes/{scene_id}/agents/{agent['agent_id']}/viewpoint"
            ).json()
            leakage[agent["name"]] = "明天能不能早到" in viewpoint["prompt"]
        record["targeted_event_visibility"] = leakage

        # 定向事件后的一次真实调用（证明事件确实进入被指定角色的上下文）。
        step = client.post(
            f"/api/scenes/{scene_id}/commands",
            json={"request_id": "live-step-after-event", "command": "STEP"},
        ).json()
        record["step_after_event"] = {
            "accepted": step["accepted"],
            "run_state": step["run_state"],
            "pause_reason": step["pause_reason"],
        }

        summary = client.get(f"/api/scenes/{scene_id}/summary").json()
        record["summary"] = summary

        # 行为分析：外部仓库未安装时必然是 DISABLED（该子项保持未验证）。
        seqs = [entry["seq"] for entry in timeline["entries"]][:3]
        if seqs:
            analysis = client.post(
                f"/api/scenes/{scene_id}/analyses",
                json={"agent_id": detail["agents"][0]["agent_id"], "material_seqs": seqs},
            ).json()
            record["analysis"] = {
                "status": analysis["status"],
                "provider_attempts": analysis["provider_attempts"],
                "error": analysis["error"],
            }

        record["run_state_final"] = client.get(f"/api/scenes/{scene_id}/state").json()["status"]

    record["finished_at"] = datetime.now(UTC).isoformat()
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="真实 DeepSeek API 端到端联调")
    parser.add_argument("--live", action="store_true", help="显式开启真实调用")
    parser.add_argument("--confirm-spend", action="store_true", help="确认会产生真实费用")
    parser.add_argument("--turns", type=int, default=DEFAULT_TURNS, help="先跑几次单步")
    parser.add_argument("--model", default=None, help="覆盖模型名（默认取契约初值）")
    parser.add_argument("--out", default=None, help="证据输出路径（不含密钥）")
    args = parser.parse_args()

    blocked = _preflight(args)
    if blocked is not None:
        return blocked

    from role_theater.config import Settings
    from role_theater.main import create_app
    from role_theater.ports import build_model_port

    settings = Settings()
    if args.model:
        # 模型名经配置注入运行器（SCENEWEAVE_MODEL_NAME 的真实生效路径）。
        settings = settings.model_copy(update={"model_name": args.model})
    port = build_model_port(
        api_key=settings.model_api_key.get_secret_value() if settings.model_api_key else None,
        base_url=settings.model_base_url,
        force_mock=False,
    )
    app = create_app(settings, model_port=port)
    record = asyncio.run(_drive(app, args.turns))

    output = (
        Path(args.out)
        if args.out
        else REPO_ROOT / "state" / "reports" / "live" / f"live-integration-{record['started_at'][:19].replace(':', '')}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False, indent=2))
    print(f"\n证据已写入 {output}（不含密钥）")

    committed = [entry for entry in record["timeline"] if entry["kind"] == "message"]
    if not committed:
        print("真实调用未产生任何公开发言；请检查失败分类与日志。", file=sys.stderr)
        return EXIT_SCENE_FAILED
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
