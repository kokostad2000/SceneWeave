"""聊天质量观察样本生成（PRD 第 10 节）。

PRD 要求「预置三个场景各运行三次，记录样本和异常」，但第 3.1 节**只定义了
一个**预置场景（“三个室友的客厅”）。本脚本因此：

- 对已定义的唯一预置场景运行三次，输出样本与可机器判定的统计；
- **不编造**另外两个场景；缺项在输出与 `docs/ACCEPTANCE.md` 中明确标为未验证。

统计只覆盖可自动判定的部分（是否回应具体内容、是否泄露未提供的私有事实、
是否有重复套话、是否允许沉默）。**它不替代 PRD 要求的人工观察**。

用法::

    uv run python scripts/quality_observation.py          # 用确定性 Mock
    uv run python scripts/quality_observation.py --repeat 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from role_theater.context import (  # noqa: E402
    ContextBuilder,
    SceneSnapshot,
    TimelineItem,
    TimelineKind,
    agent_profile_views,
)
from role_theater.contracts import (  # noqa: E402
    ActionDraft,
    ActionType,
    ModelActionRequest,
    ModelParams,
    RoleCursor,
    Scene,
    Budget,
    RunState,
)
from role_theater.ports import MockModelPort  # noqa: E402
from role_theater.presets import PRESET_SCENES, PresetScene  # noqa: E402
from role_theater.scheduling import Scheduler, SchedulerState  # noqa: E402
from datetime import UTC, datetime  # noqa: E402

NOW = datetime(2026, 9, 26, 20, 0, tzinfo=UTC)

#: 未提供给角色的具体私有事实（用于检测泄露）。
OTHER_PRIVATE_FACTS = [
    "朋友临时取消了聚会",
    "今天工作很累",
]


def build_snapshot(preset: PresetScene) -> SceneSnapshot:
    from role_theater.contracts import AgentSnapshot, SceneAgent

    agents = []
    for index, preset_agent in enumerate(preset.agents):
        profile = preset_agent.to_profile()
        agents.append(
            SceneAgent(
                agent_id=f"agt-{index}",
                scene_id="quality",
                name=preset_agent.name,
                order_index=index,
                snapshot=AgentSnapshot(
                    source_template_id=f"tpl-{index}",
                    captured_at=NOW,
                    **profile.model_dump(),
                ),
                created_at=NOW,
            )
        )
    return SceneSnapshot(
        scene_id="quality",
        background=preset.background,
        agents=agent_profile_views(agents),
        timeline=(),
    )


async def run_once(preset: PresetScene, run_index: int) -> dict:
    """对某个预置场景用确定性 Mock 跑一轮，并统计可自动判定的质量信号。"""

    snapshot = build_snapshot(preset)
    builder = ContextBuilder()
    scheduler = Scheduler()
    port = MockModelPort(
        script=[
            ActionDraft(action=ActionType.SPEAK, text="今晚要不要一起吃饭？"),
            ActionDraft(action=ActionType.SPEAK, text="我今天挺累的，想先歇一会儿。"),
            ActionDraft(action=ActionType.PASS),
            ActionDraft(action=ActionType.PASS),
        ],
        default_draft=ActionDraft(action=ActionType.PASS),
    )

    state = SchedulerState(scene=snapshot, cursors=())
    timeline: list[TimelineItem] = []
    turns: list[dict] = []
    cursors: dict[str, RoleCursor] = {}

    for _ in range(6):
        outcome = scheduler.select(state)
        if outcome.actor_id is None:
            break
        context = builder.build(state.scene, outcome.actor_id)
        response = await port.generate_action(
            ModelActionRequest(
                scene_id="quality",
                actor_id=outcome.actor_id,
                prompt_template_id=context.prompt_template_id,
                prompt=context.prompt,
                cursor_seq=outcome.based_on_seq,
            )
        )
        if not response.ok or response.draft is None:
            break
        draft = response.draft
        actor = next(agent for agent in snapshot.agents if agent.agent_id == outcome.actor_id)
        turns.append(
            {
                "actor": actor.name,
                "action": draft.action.value,
                "text": draft.text,
                "responds_to_previous": bool(timeline) and draft.action is ActionType.SPEAK,
                "mentions_other_private_fact": any(
                    fact in draft.text for fact in OTHER_PRIVATE_FACTS
                ),
            }
        )
        if draft.action is ActionType.SPEAK:
            timeline.append(
                TimelineItem(
                    kind=TimelineKind.MESSAGE,
                    seq=len(timeline) + 1,
                    body=draft.text,
                    author_agent_id=actor.agent_id,
                    author_name=actor.name,
                )
            )
        cursors[actor.agent_id] = RoleCursor(
            scene_id="quality",
            agent_id=actor.agent_id,
            processed_seq=outcome.based_on_seq,
            startup_opportunity_consumed=True,
            last_action_at=NOW,
        )
        state = SchedulerState(
            scene=SceneSnapshot(
                scene_id=snapshot.scene_id,
                background=snapshot.background,
                agents=snapshot.agents,
                timeline=tuple(timeline),
            ),
            cursors=tuple(cursors.values()),
        )

    speeches = [turn for turn in turns if turn["action"] == ActionType.SPEAK.value]
    passes = [turn for turn in turns if turn["action"] == ActionType.PASS.value]
    texts = [turn["text"] for turn in speeches]
    return {
        "preset_key": preset.key,
        "scene": preset.title,
        "run": run_index,
        "turns": turns,
        "stats": {
            "turns": len(turns),
            "speeches": len(speeches),
            "passes": len(passes),
            "allows_silence": len(passes) > 0,
            # 第一句没有可回应的上下文，因此只统计其后的发言是否落在已有上下文上。
            "later_speeches_reference_context": (
                all(turn["responds_to_previous"] for turn in speeches[1:])
                if len(speeches) > 1
                else None
            ),
            "leaks_other_private_fact": any(turn["mentions_other_private_fact"] for turn in turns),
            "repeated_phrases": _repeated_phrases(texts),
        },
    }


def _repeated_phrases(texts: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    for text in texts:
        seen[text] = seen.get(text, 0) + 1
    return [text for text, count in seen.items() if count > 1]


def main() -> int:
    parser = argparse.ArgumentParser(description="聊天质量观察样本（确定性 Mock）")
    parser.add_argument("--repeat", type=int, default=3, help="同一预置场景运行次数")
    parser.add_argument("--out", default=None, help="输出 JSON 路径")
    args = parser.parse_args()

    scenes = list(PRESET_SCENES.values())
    print(f"说明：PRD 10 要求「预置三个场景各运行三次」；当前预置场景 {len(scenes)} 个，每个运行 {args.repeat} 次。")
    print("      新增的两个场景由人工裁决补齐（B6 决议），角色与情境为项目自撰内容。")
    print("      统计仅覆盖可自动判定的信号（且本轮用的是确定性 Mock，不代表真实模型质量），")
    print("      不替代 PRD 要求的人工观察。\n")

    results = [
        asyncio.run(run_once(preset, run_index + 1))
        for preset in scenes
        for run_index in range(args.repeat)
    ]
    output = {
        "preset_scenes_defined": len(scenes),
        "preset_scenes_required_by_prd10": 3,
        "runs_per_scene": args.repeat,
        "engine": "deterministic-mock",
        "runs": results,
    }
    text = json.dumps(output, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
