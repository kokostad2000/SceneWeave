"""记录 2/3/5/8 人全部私聊会话的 Mock 结构与时延，不能证明真实容量。"""
import json
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from role_theater.config import Settings
from role_theater.main import create_app
from role_theater.ports import MockModelPort
from role_theater.contracts import ActionDraft

class PairPort(MockModelPort):
    def __init__(self): super().__init__(); self.pairs=set()
    async def generate_action(self,request):
        recipient = next((a for a in request.references.allowed_speaker_ids if tuple(sorted((a,request.actor_id))) not in self.pairs),None)
        if recipient:
            self.pairs.add(tuple(sorted((recipient,request.actor_id))))
            self._script=[ActionDraft(action="PRIVATE",text="Mock pair sample",recipient_id=recipient)]
        return await super().generate_action(request)

def measure():
    results=[]
    with TemporaryDirectory(prefix="sceneweave-pc-capacity-") as temp:
        for n in (2,3,5,8):
            port=PairPort()
            app=create_app(Settings(_env_file=None,model_api_key=None,model_force_mock=True,analysis_enabled=False,database_url=f"sqlite:///{temp}/{n}.db"),model_port=port)
            started=time.perf_counter(); waits=[]; wakeups=0
            with TestClient(app) as client:
                templates=[]
                for i in range(n):
                    r=client.post("/api/templates",json=dict(name=f"角色{i}",persona="虚构人物",speech_style="",initial_goal="",private_background="")); r.raise_for_status(); templates.append(r.json()["template_id"])
                r=client.post("/api/scenes",json=dict(title=f"{n}人Mock容量",background="自由交谈",agents=[dict(template_id=t) for t in templates])); r.raise_for_status(); sid=r.json()["scene"]["scene_id"]
                for i in range(200):
                    before=time.perf_counter(); r=client.post(f"/api/scenes/{sid}/commands",json=dict(request_id=f"s{i}",command="STEP")); r.raise_for_status(); waits.append(time.perf_counter()-before)
                    if r.json().get("pause_reason") == "NO_NEW_INFORMATION":
                        client.post(f"/api/scenes/{sid}/events",json=dict(request_id=f"wake{i}",body="操作者新增容量测试机会",visibility="ALL")).raise_for_status()
                        wakeups += 1
                    if len(port.pairs)==n*(n-1)//2: break
                timeline=client.get(f"/api/scenes/{sid}/timeline").json()
                assert len(timeline["conversations"])==n*(n-1)//2
                results.append(dict(roles=n,conversations=len(timeline["conversations"]),messages=sum(e["kind"]=="message" for e in timeline["entries"]),operator_wakeups=wakeups,calls=port.call_count,
                    prompt_codepoints=[len(r.prompt) for r in port.calls],step_seconds=waits,elapsed_seconds=time.perf_counter()-started,usage="unknown: Mock does not invent tokens",engine="Mock"))
    return results

if __name__ == "__main__":
    results=measure()
    dest=Path(__file__).resolve().parents[2]/"state/reports/private-chat/capacity.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(results,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps([{k:r[k] for k in ("roles","conversations","messages","calls","elapsed_seconds")} for r in results]))
