"""FC-12: bounded old/new samples in both modes; live requests require --live."""
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
    calls, turns = record['calls'], record['requests']
    return bool(calls and record['snapshot_matches'] and record['budget_matches']
        and record['policy_matches'] and record['final_state']['status'] == 'ENDED'
        and not record['final_state']['in_flight'] and record['stop']['accepted']
        and all(c['response']['ok'] for c in calls)
        and all(t['status'] == 'SUCCEEDED' for t in turns)
        and all(s['accepted'] and s.get('pause_reason') in
                (None, 'MANUAL', 'NO_NEW_INFORMATION', 'COLLECTIVE_SILENCE') for s in record['steps'])
        and (not record['live'] or all(c['response']['usage']['input_tokens'] is not None
            and c['response']['usage']['output_tokens'] is not None
            and c['response']['usage']['input_tokens'] + c['response']['usage']['output_tokens'] <= 10_000_000
            for c in calls)))


def drive(output: Path, *, live: bool, mode: str, policy: int, turns: int) -> dict:
    from fastapi.testclient import TestClient
    from role_theater.config import Settings
    from role_theater.contracts import Usage
    from role_theater.main import create_app
    from role_theater.ports import MockModelPort, build_model_port

    if mode not in ('simulation', 'discussion') or policy not in (1, 2) or not 3 <= turns <= 8:
        raise ValueError('观察参数超出有限范围')
    if (output / 'sample.db').exists():
        raise RuntimeError('输出数据库已存在，请使用新目录')
    output.mkdir(parents=True, exist_ok=True)
    settings = Settings(**({} if live else {'_env_file': None, 'model_api_key': None}),
        model_force_mock=not live, analysis_enabled=False,
        database_url=f"sqlite:///{output / 'sample.db'}")
    if live and not settings.model_configured:
        raise RuntimeError('model_configured=false；真实观察未验证')
    inner = (build_model_port(provider=settings.resolved_provider,
        api_key=settings.model_api_key.get_secret_value() if settings.model_api_key_present else None,
        base_url=settings.model_base_url, include_response_format=settings.local_include_response_format)
        if live else MockModelPort(usage=Usage(input_tokens=1, output_tokens=1)))
    calls = []

    class CapturePort:
        async def generate_action(self, request):
            response = await inner.generate_action(request)
            # Contract response excludes authentication and reasoning_content.
            calls.append({'request': request.model_dump(mode='json'), 'response': response.model_dump(mode='json')})
            return response

    app = create_app(settings, model_port=CapturePort())
    with TestClient(app) as client:
        agents = []
        for name, perspective in [('甲', '更关心安静休息的空间'), ('乙', '更关心邻里交流的机会')]:
            template = client.post('/api/templates', json={'name': name}).json()
            agents.append({'template_id': template['template_id'], 'role_profile': {
                'public_profile': '社区居民', 'persona': f'普通成年人，{perspective}。',
                'speech_style': '自然表达，可以讲理由、举例或追问。',
                'initial_goal': '讨论周末公共空间如何兼顾安静与交流；表达当前想法，可以补充或沉默，无须给出共识。',
                'private_background': ''}})
        mode_config = ({'topic': '社区公共空间怎样兼顾休息与交流需求？',
                        'materials': '周末活动增多，居民需要休息，也希望邻里有交流机会。'}
                       if mode == 'discussion' else {'situation': '周末傍晚，两位社区居民在公共客厅碰面，聊起休息与邻里交流。'})
        response = client.post('/api/scenes', json={'title': f'FC {mode} policy {policy}',
            'configuration_version': 2, 'chat_policy_version': policy, 'mode': mode,
            'mode_config': mode_config, 'agents': agents, 'max_role_requests': turns})
        response.raise_for_status()
        detail = response.json()
        sid = detail['scene']['scene_id']
        steps = []
        for n in range(turns):
            response = client.post(f'/api/scenes/{sid}/commands', json={'request_id': f'fc-observe-{n}', 'command': 'STEP'})
            response.raise_for_status()
            ack = response.json()
            steps.append(ack)
            if not ack['accepted'] or ack['run_state'] == 'ENDED' or ack.get('pause_reason') not in (None, 'MANUAL'):
                break
        runtime = app.state.runtime_repository
        requests = runtime.list_turns(sid)
        before_stop = client.get(f'/api/scenes/{sid}/state').json()
        response = client.post(f'/api/scenes/{sid}/commands', json={'request_id': 'fc-observe-stop', 'command': 'STOP'})
        response.raise_for_status()
        stop = response.json()
        messages = [m.model_dump(mode='json') for m in runtime.list_messages(sid)]
        budget = runtime.budget_used(sid)
        expected_output = 4096 if policy == 2 else 1024
        expected_template = f'role_action@{mode}.fc.1' if policy == 2 else f'role_action@{mode}.sr.1'
        record = dict(live=live, provider=settings.resolved_provider, mode=mode, policy=policy,
            created_at=datetime.now(UTC).isoformat(), scene=detail, calls=calls, requests=requests,
            steps=steps, messages=messages, before_stop=before_stop, stop=stop,
            final_state=client.get(f'/api/scenes/{sid}/state').json(), budget=budget,
            snapshot_matches=len(requests) == len(calls) and all(
                json.loads(t['request_snapshot_json']) == c['request'] for t, c in zip(requests, calls)),
            budget_matches=budget['role_requests_used'] == sum(t['budget_consumed'] for t in requests)
                and budget['role_requests_used'] == sum(c['response']['sent'] is not False for c in calls),
            policy_matches=detail['scene']['chat_policy_version'] == policy and all(
                c['request']['chat_policy_version'] == policy
                and c['request']['params']['max_output_tokens'] == expected_output
                and c['request']['prompt_template_id'] == expected_template for c in calls),
            request_status_counts=dict(Counter(t['status'] for t in requests)),
            action_counts=dict(Counter(t['action'] for t in requests if t['status'] == 'SUCCEEDED')),
            longest_message_codepoints=max((len(m['text']) for m in messages), default=0),
            usage_total=sum((c['response']['usage']['input_tokens'] or 0) +
                            (c['response']['usage']['output_tokens'] or 0) for c in calls),
            largest_call_tokens=max(((c['response']['usage']['input_tokens'] or 0) +
                (c['response']['usage']['output_tokens'] or 0) for c in calls), default=0),
            unverified=['人工自然度评估', '长期容量', '真实讨论行为分析', '原M06 Q1/Q2']
                + ([] if live else ['真实供应商使用']),
            note='同一设定有限观察；无失败重试、无强制覆盖或共识要求。Mock用量为测试值。')
        record['observation_ok'] = observation_ok(record)
        (output / 'evidence.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
        return record


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--turns', type=int, choices=range(3, 9), default=6)
    parser.add_argument('--output', type=Path, default=BACKEND.parent / 'state/reports/free-chat/observation')
    args = parser.parse_args(argv)
    root = args.output / datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')
    results = []
    try:
        for mode in ('simulation', 'discussion'):
            for policy in (1, 2):
                record = drive(root / f'{mode}-policy-{policy}', live=args.live, mode=mode, policy=policy, turns=args.turns)
                summary = {key: record[key] for key in ('mode', 'policy', 'request_status_counts', 'action_counts',
                    'longest_message_codepoints', 'usage_total', 'largest_call_tokens', 'observation_ok')}
                summary['evidence'] = str(root / f'{mode}-policy-{policy}/evidence.json')
                results.append(summary)
                print(json.dumps(summary, ensure_ascii=False), flush=True)
    except RuntimeError as exc:
        print(str(exc))
        return 3
    return 0 if len(results) == 4 and all(r['observation_ok'] for r in results) else 4


if __name__ == '__main__':
    raise SystemExit(main())
