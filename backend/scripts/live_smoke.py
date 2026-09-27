"""真实模型冒烟（PRD 第 10 节、第 9 节 M07）。

**显式 live 开关 + 有效配置**才会发起真实调用；缺少任一条件时**拒绝运行**并以
非零退出码说明缺项——绝不回退成 Mock 后宣称通过（PRD 10）。

用法::

    # 需要显式开关与密钥；会产生真实费用
    SCENEWEAVE_MODEL_API_KEY=... uv run python scripts/live_smoke.py --live

    # 不带开关（或没有密钥）时只会打印缺项并退出 2
    uv run python scripts/live_smoke.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from role_theater.contracts import ActionDraft, ActionType  # noqa: E402
from role_theater.ports import build_model_port  # noqa: E402

EXIT_MISSING_SWITCH = 2
EXIT_MISSING_KEY = 3
EXIT_PROVIDER_FAILURE = 4

SCENE_BACKGROUND = "晚上，三个室友在客厅相遇，尚未确定今晚做什么。"
AN_AN = {"name": "安然", "persona": "主动热情。", "speech_style": "热情提问。", "initial_goal": "想找人一起度过今晚。", "private_background": "朋友临时取消了聚会。"}
XU_CHUAN = {"name": "许川", "persona": "表达直接。", "speech_style": "短句。", "initial_goal": "想休息。", "private_background": "今天工作很累。"}
CHEN_HE = {"name": "陈禾", "persona": "刚搬来。", "speech_style": "客气、简短。", "initial_goal": "想融入但不想打扰。", "private_background": ""}


def _build_prompt(actor: dict, others: tuple[str, ...], background: str) -> str:
    """真实冒烟用最小提示词（与 ContextBuilder 的分区一致，但只用于人工观察）。"""

    return (
        f"你正在扮演虚构角色「{actor['name']}」。\n"
        f"## 共同情境\n{background}\n"
        f"## 在场角色（公开名册）\n{'、'.join(others)}\n"
        f"## 你的私有资料（仅你可见）\n"
        f"- 人物设定：{actor['persona']}\n"
        f"- 表达习惯：{actor['speech_style']}\n"
        f"- 初始目标：{actor['initial_goal']}\n"
        f"- 私有背景：{actor['private_background'] or '（未提供）'}\n"
        "## 行为规则\n"
        "- 只以自己的身份发言，不得替他人发言。\n"
        "- 只返回四字段 JSON。\n"
    )


async def run_live_smoke(model_name: str | None) -> int:
    from role_theater.config import Settings
    from role_theater.contracts import ModelActionRequest, ModelParams

    settings = Settings()
    if not settings.model_configured:
        print("缺项：未配置 SCENEWEAVE_MODEL_API_KEY，无法进行真实模型验收。", file=sys.stderr)
        print("      该项按 PRD 10 记为「未验证」，不得用 Mock 结果替代。", file=sys.stderr)
        return EXIT_MISSING_KEY

    port = build_model_port(
        api_key=settings.model_api_key.get_secret_value() if settings.model_api_key else None,
        base_url=settings.model_base_url,
        force_mock=False,
    )

    actors = [AN_AN, XU_CHUAN, CHEN_HE]
    print("真实模型冒烟：三人各一次请求（会产生真实费用）")
    failures = 0
    for index, actor in enumerate(actors):
        others = tuple(other["name"] for other in actors if other is not actor)
        request = ModelActionRequest(
            scene_id="live-smoke",
            actor_id=f"live-{index}",
            prompt_template_id="live_smoke@m07",
            prompt=_build_prompt(actor, others, SCENE_BACKGROUND),
            cursor_seq=index,
            params=ModelParams(model=model_name or ModelParams().model),
        )
        response = await port.generate_action(request)
        payload = {
            "actor": actor["name"],
            "ok": response.ok,
            "draft": response.draft.model_dump() if response.draft else None,
            "failure": response.failure.model_dump() if response.failure else None,
            "requested_model": response.requested_model,
            "returned_model": response.returned_model,
            "usage": response.usage.model_dump(),
            "latency_ms": response.latency_ms,
            "provider_request_id": response.provider_request_id,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        if not response.ok:
            failures += 1

    return 0 if failures == 0 else EXIT_PROVIDER_FAILURE


def main() -> int:
    parser = argparse.ArgumentParser(description="SceneWeave 真实模型冒烟（需显式 live 开关）")
    parser.add_argument("--live", action="store_true", help="显式开启真实调用")
    parser.add_argument("--model", default=None, help="覆盖模型名（默认取契约初值）")
    args = parser.parse_args()

    if not args.live:
        print("未提供 --live：真实模型验收不会执行。", file=sys.stderr)
        print("该项按 PRD 10 记为「未验证」。", file=sys.stderr)
        return EXIT_MISSING_SWITCH
    if not os.environ.get("SCENEWEAVE_MODEL_API_KEY", "").strip():
        print("缺项：环境变量 SCENEWEAVE_MODEL_API_KEY 为空。", file=sys.stderr)
        return EXIT_MISSING_KEY

    return asyncio.run(run_live_smoke(args.model))


if __name__ == "__main__":
    raise SystemExit(main())
