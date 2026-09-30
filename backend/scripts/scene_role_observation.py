"""SR 有限观察：旧露营人物在空设定讨论与显式场景预设中分别运行。"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from dual_mode_observation import observation_ok as runtime_observation_ok


def observation_ok(record: dict) -> bool:
    return bool(runtime_observation_ok(record) and record['profile_matches']
                and record['new_prompt_matches'] and record['no_legacy_profile_in_input'])


def drive(output: Path, *, live: bool, case: str, turns: int) -> dict:
    from fastapi.testclient import TestClient
    from role_theater.config import Settings
    from role_theater.contracts import SceneRoleProfile, Usage
    from role_theater.main import create_app
    from role_theater.ports import MockModelPort, build_model_port
    from role_theater.presets import CAMPSITE

    if case not in ('empty-discussion', 'preset-simulation'):
        raise ValueError('未知观察类别')
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
            response = await inner.generate_action(request)
            calls.append({'request': request.model_dump(mode='json'), 'response': response.model_dump(mode='json')})
            return response

    app = create_app(settings, model_port=CapturePort())
    with TestClient(app) as client:
        specs, legacy_texts, expected = [], [], {}
        for actor in CAMPSITE.agents:
            legacy = actor.to_profile().model_dump()
            if case == 'preset-simulation':
                # 故意让同名目录内容与预设不同，验证预设的真实来源。
                for field in SceneRoleProfile.model_fields:
                    legacy[field] = f'旧目录-{field}-{actor.name}'
            legacy_texts.extend(v for k, v in legacy.items() if k != 'name' and v)
            response = client.post('/api/templates', json=legacy)
            response.raise_for_status()
            specs.append({'template_id': response.json()['template_id']})
            expected[actor.name] = (SceneRoleProfile().model_dump() if case == 'empty-discussion'
                                    else actor.to_profile().model_dump(exclude={'name'}))
        if case == 'empty-discussion':
            response = client.post('/api/scenes', json={
                'configuration_version': 2, 'chat_policy_version': 1, 'title': 'SR 空设定讨论', 'mode': 'discussion',
                'mode_config': {'topic': '社区公共空间怎样兼顾休息与交流需求？'},
                'agents': specs, 'max_role_requests': turns})
        else:
            response = client.post('/api/scenes/preset', json={'preset_key': 'campsite', 'configuration_version': 2, 'chat_policy_version': 1})
        response.raise_for_status()
        detail = response.json()
        sid = detail['scene']['scene_id']
        steps = []
        for n in range(turns):
            response = client.post(f'/api/scenes/{sid}/commands', json={'request_id': f'sr-observe-{n}', 'command': 'STEP'})
            response.raise_for_status()
            ack = response.json()
            steps.append(ack)
            if not ack['accepted'] or ack['run_state'] == 'ENDED' or ack.get('pause_reason') not in (None, 'MANUAL'):
                break
        runtime = app.state.runtime_repository
        requests = runtime.list_turns(sid)
        before_stop = client.get(f'/api/scenes/{sid}/state').json()
        client.post(f'/api/scenes/{sid}/commands', json={'request_id': 'sr-observe-stop', 'command': 'STOP'}).raise_for_status()
        messages = [m.model_dump(mode='json') for m in runtime.list_messages(sid)]
        budget = runtime.budget_used(sid)
        profile_matches = detail['scene']['configuration_version'] == 2 and all(
            {f: a['snapshot'][f] for f in SceneRoleProfile.model_fields} == expected[a['name']]
            for a in detail['agents'])
        mode = detail['scene']['mode']
        record = dict(live=live, provider=settings.resolved_provider, mode=mode, case=case,
            created_at=datetime.now(UTC).isoformat(), scene=detail, calls=calls,
            requests=requests, steps=steps, messages=messages, before_stop=before_stop,
            final_state=client.get(f'/api/scenes/{sid}/state').json(), budget=budget,
            snapshot_matches=len(requests) == len(calls) and all(
                json.loads(t['request_snapshot_json']) == c['request'] for t, c in zip(requests, calls)),
            budget_matches=budget['role_requests_used'] == sum(t['budget_consumed'] for t in requests),
            profile_matches=profile_matches,
            new_prompt_matches=bool(calls) and all(c['request']['prompt_template_id'] == f'role_action@{mode}.sr.1' for c in calls),
            no_legacy_profile_in_input=all(v not in json.dumps(c['request'], ensure_ascii=False)
                                           for c in calls for v in legacy_texts),
            request_status_counts=dict(Counter(t['status'] for t in requests)),
            action_counts=dict(Counter(t['action'] for t in requests if t['status'] == 'SUCCEEDED')),
            unverified=['人工对话质量', '真实长期容量', '原 M06 Q1/Q2', '真实讨论行为分析']
                       + ([] if live else ['真实供应商使用']),
            note='显式 --live 才调用真实供应商；不重试补齐行为覆盖；Mock用量为测试值。')
        record['observation_ok'] = observation_ok(record)
        (output / 'evidence.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
        return record


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--turns', type=int, choices=range(3, 9), default=3)
    parser.add_argument('--output', type=Path, default=BACKEND.parent / 'state/reports/scene-role-profile/observation')
    args = parser.parse_args(argv)
    root = args.output / datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')
    results = []
    try:
        for case in ('empty-discussion', 'preset-simulation'):
            record = drive(root / case, live=args.live, case=case, turns=args.turns)
            summary = {key: record[key] for key in ('case', 'mode', 'request_status_counts', 'action_counts', 'observation_ok')}
            summary['evidence'] = str(root / case / 'evidence.json')
            results.append(summary)
            print(json.dumps(summary, ensure_ascii=False), flush=True)
    except RuntimeError as exc:
        print(str(exc))
        return 3
    return 0 if all(r['observation_ok'] for r in results) else 4


if __name__ == '__main__':
    raise SystemExit(main())
