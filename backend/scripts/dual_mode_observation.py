"""P1 有限观察：普通两模式与明确私聊目标分开；真实调用必须 --live。"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def observation_ok(record: dict) -> bool:
    """接口成功与用量证据完整性；不把偶然私聊或共识当成通过条件。"""
    return bool(record['calls'] and record['snapshot_matches'] and record['budget_matches']
                and record['final_state']['status'] == 'ENDED' and not record['final_state']['in_flight']
                and all(c['response']['ok'] for c in record['calls'])
                and all(t['status'] == 'SUCCEEDED' for t in record['requests'])
                and all(s['accepted'] and s.get('pause_reason') in (None, 'MANUAL', 'NO_NEW_INFORMATION')
                        for s in record['steps'])
                and (not record['live'] or all(
                    c['response']['usage']['input_tokens'] is not None
                    and c['response']['usage']['output_tokens'] is not None
                    and c['response']['usage']['input_tokens'] + c['response']['usage']['output_tokens'] <= 10_000_000
                    for c in record['calls'])))


def drive(output: Path, *, live: bool, mode: str, guided: bool, turns: int) -> dict:
    from fastapi.testclient import TestClient
    from role_theater.config import Settings
    from role_theater.main import create_app
    from role_theater.ports import build_model_port, MockModelPort
    from role_theater.contracts import Usage

    if (output / 'sample.db').exists():
        raise RuntimeError('输出数据库已存在，请使用新的目录')
    output.mkdir(parents=True, exist_ok=True)
    settings = Settings(**({} if live else {'_env_file': None, 'model_api_key': None}),
                        model_force_mock=not live, analysis_enabled=False,
                        database_url=f"sqlite:///{output / 'sample.db'}")
    if live and not settings.model_configured:
        raise RuntimeError('model_configured=false；真实观察未验证')
    inner = (build_model_port(provider=settings.resolved_provider,
                            api_key=settings.model_api_key.get_secret_value() if settings.model_api_key_present else None,
                            base_url=settings.model_base_url,
                            include_response_format=settings.local_include_response_format)
             if live else MockModelPort(usage=Usage(input_tokens=1, output_tokens=1)))
    calls = []

    class CapturePort:
        async def generate_action(self, request):
            result = await inner.generate_action(request)
            calls.append({'request': request.model_dump(mode='json'), 'response': result.model_dump(mode='json')})
            return result

    app = create_app(settings, model_port=CapturePort())
    with TestClient(app) as client:
        agents = []
        for index, name in enumerate(['甲', '乙', '丙']):
            goal = ('希望先私下邀请乙参加周末活动，并听听乙的想法。行动仍自由选择。' if index == 0
                    else '如收到甲的邀请，想私下告诉甲自己的想法。行动仍自由选择。' if index == 1
                    else '听听大家公开交流的想法。') if guided else '理解别人提出的问题，表达自己当下的想法，也可以不发言。'
            profile = dict(name=name, public_profile='社区活动参与者' if mode == 'discussion' else '虚构室友',
                           persona='普通成年人，无预设观点或结论。', speech_style='自然简短',
                           initial_goal=goal, private_background='')
            response = client.post('/api/templates', json=profile)
            response.raise_for_status()
            agents.append({'template_id': response.json()['template_id'], **({'discussion_config': {'initial_position': None}} if mode == 'discussion' else {})})
        response = client.post('/api/scenes', json=dict(title=f'P1 {mode} {"明确私聊目标" if guided else "普通设定"}',
            chat_policy_version=1,
            mode=mode, mode_config=({'topic': '社区公共空间怎样兼顾休息与交流需求？', 'materials': '周末活动增多。请自由交流，不预设最终决定。'}
                                    if mode == 'discussion' else {'situation': '周末傍晚，三位室友在客厅相遇，尚未决定做什么。'}),
            agents=agents, max_role_requests=turns))
        response.raise_for_status()
        detail = response.json()
        sid = detail['scene']['scene_id']
        steps = []
        for n in range(turns):
            response = client.post(f'/api/scenes/{sid}/commands', json={'request_id': f'observe-{n}', 'command': 'STEP'})
            response.raise_for_status()
            ack = response.json()
            steps.append(ack)
            if not ack['accepted'] or ack['run_state'] == 'ENDED' or ack.get('pause_reason') not in (None, 'MANUAL'):
                break
        runtime = app.state.runtime_repository
        requests = runtime.list_turns(sid)
        before_stop = client.get(f'/api/scenes/{sid}/state').json()
        response = client.post(f'/api/scenes/{sid}/commands', json={'request_id': 'observe-stop', 'command': 'STOP'})
        response.raise_for_status()
        messages = [m.model_dump(mode='json') for m in runtime.list_messages(sid)]
        budget = runtime.budget_used(sid)
        record = dict(live=live, provider=settings.resolved_provider, mode=mode,
            sample_kind='guided_private_goal' if guided else 'ordinary', created_at=datetime.now(UTC).isoformat(),
            scene=detail, calls=calls, requests=requests, steps=steps, messages=messages,
            before_stop=before_stop, final_state=client.get(f'/api/scenes/{sid}/state').json(), budget=budget,
            snapshot_matches=len(requests) == len(calls) and all(json.loads(t['request_snapshot_json']) == c['request']
                for t, c in zip(requests, calls)),
            budget_matches=budget['role_requests_used'] == sum(t['budget_consumed'] for t in requests),
            request_status_counts=dict(Counter(t['status'] for t in requests)),
            action_counts=dict(Counter(t['action'] for t in requests if t['status'] == 'SUCCEEDED')),
            private_count=sum(m['visibility'] == 'PRIVATE' for m in messages),
            private_reply_count=sum(m['visibility'] == 'PRIVATE' and bool(m['reply_to_message_id']) for m in messages),
            unverified=['人工行为质量', '真实长期容量', '原M06 Q1/Q2'] + ([] if live else ['真实供应商使用']),
            note='普通设定与明确私聊目标分开；不重试补齐行为覆盖。Mock用量为明确的测试值。')
        record['observation_ok'] = observation_ok(record)
        (output / 'evidence.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
        return record


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--turns', type=int, choices=range(3, 9), default=6)
    parser.add_argument('--output', type=Path, default=BACKEND.parent / 'state/reports/dual-mode/observation')
    args = parser.parse_args(argv)
    root = args.output / datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')
    result = []
    try:
        for name, mode, guided in [('ordinary-simulation', 'simulation', False), ('ordinary-discussion', 'discussion', False), ('guided-discussion', 'discussion', True)]:
            record = drive(root / name, live=args.live, mode=mode, guided=guided, turns=args.turns)
            summary = {key: record[key] for key in ['mode', 'sample_kind', 'private_count', 'private_reply_count', 'request_status_counts', 'action_counts', 'observation_ok']}
            summary['evidence'] = str(root / name / 'evidence.json')
            result.append(summary)
            print(json.dumps(summary, ensure_ascii=False), flush=True)
    except RuntimeError as exc:
        print(str(exc))
        return 3
    return 0 if all(r['observation_ok'] for r in result) else 4


if __name__ == '__main__':
    raise SystemExit(main())
