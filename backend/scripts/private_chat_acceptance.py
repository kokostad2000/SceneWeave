"""PC 私聊独立验收入口；默认只做 Mock，真实必须 --live，不隐式重试。"""
from __future__ import annotations
import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from datetime import UTC, datetime

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def _acceptance_met(record: dict) -> bool:
    """样本覆盖不能掩盖后续失败、结果不明或尚未完成的请求。"""
    requests = record.get("requests", [])
    steps = record.get("steps", [])
    return bool(
        record.get("sample_covered") and requests and steps
        and all(t.get("status") == "SUCCEEDED" and not t.get("failure_kind") for t in requests)
        and all(step.get("accepted") is True
                and step.get("pause_reason") in (None, "MANUAL", "NO_NEW_INFORMATION")
                for step in steps)
    )


def drive(output: Path, *, live: bool, turns: int) -> dict:
    from fastapi.testclient import TestClient
    from role_theater.config import Settings
    from role_theater.main import create_app
    from role_theater.contracts import ActionDraft
    from role_theater.ports import MockModelPort
    output.mkdir(parents=True, exist_ok=True)
    settings = Settings(**({"_env_file": None, "model_api_key": None} if not live else {}), model_provider="deepseek" if live else "mock", model_force_mock=not live,
        analysis_enabled=False, database_url=f"sqlite:///{output / 'sample.db'}")
    if live and not settings.model_api_key_present:
        raise RuntimeError("model_configured=false；真实私聊未验证")
    port = None if live else MockModelPort()
    app = create_app(settings, model_port=port)
    if (output / "sample.db").exists():
        raise RuntimeError("输出数据库已存在，请使用新的输出目录")
    started_at = datetime.now(UTC).isoformat()
    started = time.perf_counter()
    with TestClient(app) as client:
        templates = []
        specs = [
            ("甲", "希望先私下邀请乙参加周末两人的活动，再听听乙的意见。行动仍可自由选择。", "只想把私人邀请告诉乙"),
            ("乙", "对甲的私人邀请感兴趣，想私下把自己的意见告诉甲。行动仍可自由选择。", "周末下午方便"),
            ("丙", "想听听大家的公共安排。不知道其他角色的私有资料。", ""),
        ]
        for name, goal, background in specs:
            response = client.post("/api/templates", json=dict(name=name,persona="虚构室友",speech_style="自然简短",initial_goal=goal,private_background=background))
            response.raise_for_status(); templates.append(response.json()["template_id"])
        response = client.post("/api/scenes", json=dict(title="PC 私聊联调", chat_policy_version=1, background="三位室友在客厅自由交谈，不预设最终决定。", agents=[dict(template_id=t) for t in templates], max_role_requests=turns))
        response.raise_for_status(); detail = response.json(); sid = detail["scene"]["scene_id"]
        a,b,c = [x["agent_id"] for x in detail["agents"]]
        if port is not None:
            port._script = [ActionDraft(action="PRIVATE", text="MOCK_PRIVATE", recipient_id=b)]
        steps = []
        for n in range(turns):
            if port is not None and n == 1:
                first = app.state.runtime_repository.list_messages(sid)[0]
                port._script = [ActionDraft(action="PRIVATE",text="MOCK_REPLY",recipient_id=a,reply_to_message_id=first.message_id)]
            response = client.post(f"/api/scenes/{sid}/commands",json=dict(request_id=f"pc-{n}",command="STEP"))
            response.raise_for_status()
            ack = response.json()
            steps.append(ack)
            if ack.get("accepted") is not True or ack.get("pause_reason") in ("PROVIDER_ERROR","CONTEXT_LIMIT","PROCESS_INTERRUPT","NO_NEW_INFORMATION") or ack.get("run_state") == "ENDED": break
        runtime = app.state.runtime_repository
        messages = runtime.list_messages(sid)
        requests = runtime.list_turns(sid)
        private = [m for m in messages if m.visibility == "PRIVATE"]
        replies = [m for m in private if m.reply_to_message_id]
        third_checks = []
        for t in requests:
            request = json.loads(t["request_snapshot_json"])
            for m in private:
                if m.created_at <= datetime.fromisoformat(t["created_at"]) and t["actor_id"] not in (m.actor_id,m.recipient_id):
                    third_checks.append(dict(actor_id=t["actor_id"],message_id=m.message_id,
                        original_id_absent=m.message_id not in json.dumps(request,ensure_ascii=False),
                        original_text_absent=m.text not in request["prompt"]))
        covered = bool(private and replies and third_checks and all(
            x["original_id_absent"] and x["original_text_absent"] for x in third_checks))
        record = dict(engine="live-deepseek" if live else "mock", started_at=started_at,
            scene_id=sid, steps=steps, messages=[m.model_dump(mode="json") for m in messages],
            requests=requests, third_party_actual_request_checks=third_checks, private_count=len(private), reply_count=len(replies),
            sample_covered=covered, elapsed_seconds=round(time.perf_counter()-started,3),
            unverified=["人工行为质量", "真实长期容量"] + ([] if live else ["真实供应商私聊"]))
        record["request_status_counts"] = dict(Counter(t["status"] for t in requests))
        record["acceptance_passed"] = _acceptance_met(record)
    (output / 'evidence.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n")
    return record


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--live",action="store_true")
    parser.add_argument("--turns",type=int,default=8,choices=range(3,13))
    parser.add_argument("--output",type=Path,default=BACKEND.parent / "state/reports/private-chat/mock")
    args=parser.parse_args(argv)
    if args.live and args.output == BACKEND.parent / "state/reports/private-chat/mock":
        args.output = BACKEND.parent / "state/reports/private-chat/live"
    args.output = args.output / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    try: record=drive(args.output,live=args.live,turns=args.turns)
    except RuntimeError as exc:
        print(str(exc)); return 3
    print(json.dumps({k:record[k] for k in ["engine","private_count","reply_count","sample_covered","acceptance_passed","request_status_counts","elapsed_seconds"]},ensure_ascii=False))
    return 0 if _acceptance_met(record) else 4

if __name__ == "__main__": raise SystemExit(main())
