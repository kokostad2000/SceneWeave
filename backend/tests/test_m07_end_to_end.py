"""M07 假模型端到端回归（PRD 第 9 节 M07、第 10 节）。

确定性端到端：三人聊天 → 定向事件 → 行为分析 → 时间线／预算／视角／历史只读。
全部使用可控 Mock 与假分析器：**不联网、不需要密钥**。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from role_theater.analysis import ControlledAnalysisClient, ExternalAnalysisPort
from role_theater.contracts import (
    ActionDraft,
    ActionType,
    ModelActionResponse,
)


class FakeAnalyzer:
    """假外部分析器：返回结构完整的正常结果。"""

    def __init__(self) -> None:
        self.requests: list = []

    async def analyze(self, request):
        self.requests.append(request)
        return {
            "behavior_labels": ["主动邀请他人"],
            "mechanisms": ["寻求社会连接"],
            "alternative_explanations": ["只是礼貌寒暄", "想确认今晚的安排"],
            "limitations": ["仅基于公开文本", "未考虑镜头外信息"],
            "disclaimer": "仅用于解释虚构角色的文本行为，不构成对真实人物的测量。",
            "degradation_flags": [],
        }


def speak(text: str, *, requested: str | None = None) -> ActionDraft:
    return ActionDraft(action=ActionType.SPEAK, text=text, requested_speaker_id=requested)


class DynamicScriptPort:
    """按顺序返回草稿；步骤可以是函数，从而读取请求里的角色 ID。"""

    def __init__(self, steps) -> None:
        self._steps = list(steps)
        self.calls = 0

    async def generate_action(self, request):
        index = min(self.calls, len(self._steps) - 1)
        self.calls += 1
        step = self._steps[index]
        draft = step(request) if callable(step) else step
        return ModelActionResponse(
            ok=True,
            draft=draft,
            prompt_template_id=request.prompt_template_id,
            requested_model=request.params.model,
            returned_model=request.params.model,
        )


def test_full_deterministic_scenario(make_client) -> None:
    """一个完整场景：三人发言 → 定向事件 → 分析，并核对所有观察面。"""

    analyzer = FakeAnalyzer()
    analysis_port = ExternalAnalysisPort(
        analyzer=analyzer, client=ControlledAnalysisClient()
    )

    def first_step(request) -> ActionDraft:
        """点名本场另一名有效角色（用请求里的引用范围，避免硬编码 ID）。"""

        others = request.references.allowed_speaker_ids
        return speak("今晚要不要一起吃饭？", requested=others[0] if others else None)

    port = DynamicScriptPort(
        [
            first_step,
            speak("我想先休息一会儿。"),
            speak("我可以一起，但别太晚。"),
            speak("那就简单吃点吧。"),
        ]
    )

    with make_client(
        model_port=port, analysis_enabled=True, injected_analysis_port=analysis_port
    ) as client:
        detail = client.post("/api/scenes/preset", json={"chat_policy_version": 1}).json()
        scene_id = detail["scene"]["scene_id"]
        agents = {agent["name"]: agent["agent_id"] for agent in detail["agents"]}
        assert list(agents) == ["安然", "许川", "陈禾"]

        # --- 三人依次发言（每个角色一次启动机会） ---
        for index in range(3):
            ack = client.post(
                f"/api/scenes/{scene_id}/commands",
                json={"request_id": f"step-{index}", "command": "STEP"},
            ).json()
            assert ack["accepted"] is True

        timeline = client.get(f"/api/scenes/{scene_id}/timeline").json()
        messages = [entry for entry in timeline["entries"] if entry["kind"] == "message"]
        assert [entry["author_name"] for entry in messages] == ["安然", "许川", "陈禾"]
        assert [entry["seq"] for entry in messages] == [1, 2, 3]
        assert messages[0]["message"]["requested_speaker_id"] == agents["许川"]

        # --- 定向事件：只给许川 ---
        event_ack = client.post(
            f"/api/scenes/{scene_id}/events",
            json={
                "request_id": "event-1",
                "body": "许川的手机响了：同事说明天要早到。",
                "visibility": "TARGETED",
                "target_agent_id": agents["许川"],
            },
        ).json()
        assert event_ack["event_status"] == "EFFECTIVE"

        # 定向事件对目标可见、对他人不可见（PRD 4.1）。
        for name, agent_id in agents.items():
            viewpoint = client.get(
                f"/api/scenes/{scene_id}/agents/{agent_id}/viewpoint"
            ).json()
            if name == "许川":
                assert "明天要早到" in viewpoint["prompt"]
            else:
                assert "明天要早到" not in viewpoint["prompt"]
            # 他人私有背景一律不可见。
            assert "今天工作很累" not in viewpoint["prompt"] or name == "许川"

        # --- 定向事件唤醒许川 ---
        # 定向事件（#4）对他可见而他只处理到 #1，因此他重新成为候选；
        # 但「候选」不等于「被选中」：轮转取最久未行动者，于是本轮由安然发言。
        status_before = {
            item["name"]: item
            for item in client.get(f"/api/scenes/{scene_id}/agents/status").json()["agents"]
        }
        assert status_before["许川"]["processed_seq"] < 4, "定向事件对他构成未处理的新信息"

        step = client.post(
            f"/api/scenes/{scene_id}/commands",
            json={"request_id": "step-3", "command": "STEP"},
        ).json()
        assert step["accepted"] is True
        after = client.get(f"/api/scenes/{scene_id}/timeline").json()
        # 时间线顺序 = 生效顺序：3 条发言 → 定向事件(#4) → 被唤醒的许川(#5)。
        assert [(entry["kind"], entry["seq"]) for entry in after["entries"]] == [
            ("message", 1),
            ("message", 2),
            ("message", 3),
            ("event", 4),
            ("message", 5),
        ]
        assert after["entries"][-1]["author_name"] == "安然", "轮转选择最久未行动的候选"
        assert after["entries"][3]["event"]["visibility"] == "TARGETED"

        # --- 行为分析（只读观察，不影响剧情） ---
        before_state = client.get(f"/api/scenes/{scene_id}/state").json()
        record = client.post(
            f"/api/scenes/{scene_id}/analyses",
            json={"agent_id": agents["安然"], "material_seqs": [1, 2, 3]},
        ).json()

        assert record["status"] == "NORMAL"
        assert record["provider_attempts"] == 1
        assert len(record["report"]["alternative_explanations"]) >= 2
        assert record["report"]["disclaimer"]
        assert record["materials"], "分析记录保留送出的材料原文"
        assert analyzer.requests and analyzer.requests[0].persist_profile is False

        after_state = client.get(f"/api/scenes/{scene_id}/state").json()
        for field in ("status", "pause_reason", "role_requests_used", "last_committed_seq"):
            assert after_state[field] == before_state[field], f"分析不得改变 {field}"

        # --- 预算与计数 ---
        summary = client.get(f"/api/scenes/{scene_id}/summary").json()
        assert summary["role_requests_used"] == 4
        assert summary["succeeded"] == 4
        assert summary["failed"] == 0
        analyses = client.get(f"/api/scenes/{scene_id}/analyses").json()
        assert analyses["operations_total"] == 1
        assert analyses["provider_attempts_total"] == 1

        # --- 历史（只读）不调用模型、不改变预算 ---
        client.get(f"/api/scenes/{scene_id}/timeline")
        client.get(f"/api/scenes/{scene_id}/agents/status")
        assert (
            client.get(f"/api/scenes/{scene_id}/summary").json()["role_requests_used"] == 4
        )

        # --- 结束会话后仍可查看历史与做只读分析 ---
        stop = client.post(
            f"/api/scenes/{scene_id}/commands", json={"request_id": "stop", "command": "STOP"}
        ).json()
        assert stop["run_state"] == "ENDED"
        assert (
            client.post(
                f"/api/scenes/{scene_id}/commands",
                json={"request_id": "step-after-end", "command": "STEP"},
            ).json()["accepted"]
            is False
        )
        assert len(client.get(f"/api/scenes/{scene_id}/timeline").json()["entries"]) == 5


def test_scene_sizes_two_three_five_eight_via_http(make_client) -> None:
    """硬验收：2／3／5／8 人配置都能创建工作流（PRD 10）。"""

    with make_client([ActionDraft(action=ActionType.PASS)]) as client:
        # 先把 8 个模板准备好。
        for index in range(8):
            response = client.post(
                "/api/templates",
                json={
                    "name": f"角色{index}",
                    "persona": "p",
                    "speech_style": "s",
                    "initial_goal": "g",
                    "private_background": "b",
                },
            )
            assert response.status_code == 201
        template_ids = [t["template_id"] for t in client.get("/api/templates").json()["templates"]]
        assert len(template_ids) == 8

        for count in (2, 3, 5, 8):
            created = client.post(
                "/api/scenes",
                json={
                    "title": f"{count} 人场景",
                    "background": "背景。",
                    "agents": [{"template_id": tid} for tid in template_ids[:count]],
                },
            )
            assert created.status_code == 201, created.text
            detail = created.json()
            assert len(detail["agents"]) == count

            # 每个场景都能独立单步（调度与预算互不干扰）。
            ack = client.post(
                f"/api/scenes/{detail['scene']['scene_id']}/commands",
                json={"request_id": f"step-{count}", "command": "STEP"},
            ).json()
            assert ack["accepted"] is True


def test_paused_scene_can_be_resumed_and_ended(make_client) -> None:
    """暂停／继续／结束在调用边界生效（硬验收：暂停／结束）。"""

    with make_client([speak("第一句。"), speak("第二句。"), speak("第三句。")]) as client:
        scene_id = client.post("/api/scenes/preset", json={"chat_policy_version": 1}).json()["scene"]["scene_id"]

        assert (
            client.post(
                f"/api/scenes/{scene_id}/commands",
                json={"request_id": "s1", "command": "STEP"},
            ).json()["run_state"]
            == "PAUSED"
        )
        resumed = client.post(
            f"/api/scenes/{scene_id}/commands", json={"request_id": "r1", "command": "RESUME"}
        ).json()
        assert resumed["run_state"] == "RUNNING"

        paused = client.post(
            f"/api/scenes/{scene_id}/commands", json={"request_id": "p1", "command": "PAUSE"}
        ).json()
        assert paused["run_state"] in ("PAUSING", "PAUSED")

        ended = client.post(
            f"/api/scenes/{scene_id}/commands", json={"request_id": "x1", "command": "STOP"}
        ).json()
        assert ended["run_state"] in ("STOPPING", "ENDED")

        final = client.get(f"/api/scenes/{scene_id}/state").json()
        assert final["status"] in ("PAUSED", "ENDED")
