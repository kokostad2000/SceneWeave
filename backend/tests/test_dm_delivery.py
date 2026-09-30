import copy
import json

import pytest

from dual_mode_observation import drive, observation_ok, main
from role_theater.contracts import ActionDraft, SceneMode


@pytest.mark.parametrize('mode', list(SceneMode))
@pytest.mark.parametrize('count', [2, 3, 5, 8])
def test_both_modes_capacity_and_200_codepoints(make_client, mode, count):
    with make_client([ActionDraft(action='SPEAK', text='😀' * 200)]) as client:
        specs = []
        for i in range(count):
            r = client.post('/api/templates', json=dict(name=f'角色{i}', public_profile='公开', persona='私人', speech_style='', initial_goal='', private_background=''))
            assert r.status_code == 201
            specs.append({'template_id': r.json()['template_id']})
        response = client.post('/api/scenes', json=dict(title='容量', mode=mode, mode_config={'topic': '议题'} if mode == 'discussion' else {'situation': '情境'}, agents=specs))
        assert response.status_code == 201
        sid = response.json()['scene']['scene_id']
        assert len(response.json()['agents']) == count
        assert client.post(f'/api/scenes/{sid}/commands', json=dict(request_id='s1', command='STEP')).json()['accepted']
        assert client.get(f'/api/scenes/{sid}/timeline').json()['entries'][0]['message']['text'] == '😀' * 200
        assert client.app.state.scene_runner._model.call_count == 1
        assert client.get(f'/api/scenes/{sid}').json()['scene']['mode'] == mode


@pytest.mark.parametrize('mode', list(SceneMode))
def test_observation_mock_and_failures_remain_failures(tmp_path, mode):
    record = drive(tmp_path / mode, live=False, mode=mode, guided=False, turns=6)
    assert record['observation_ok'] is True
    assert record['snapshot_matches'] and record['budget_matches']
    assert record['private_count'] == 0  # 不需要为了覆盖而强迫私聊。
    assert record['final_state']['status'] == 'ENDED'
    for failure in ['TIMEOUT', 'UNKNOWN_REQUEST']:
        broken = copy.deepcopy(record)
        broken['calls'][-1]['response']['ok'] = False
        broken['requests'][-1]['failure_kind'] = failure
        broken['requests'][-1]['status'] = 'FAILED' if failure == 'TIMEOUT' else 'UNKNOWN'
        assert not observation_ok(broken)
    live = copy.deepcopy(record)
    live['live'] = True
    for usage in [dict(input_tokens=None, output_tokens=None), dict(input_tokens=9_999_999, output_tokens=2)]:
        live['calls'][-1]['response']['usage'].update(usage)
        assert not observation_ok(live)
    assert json.loads((tmp_path / mode / 'evidence.json').read_text())['observation_ok'] is True


def test_observation_cli_mock_and_missing_live_no_database(tmp_path, monkeypatch):
    assert main(['--turns', '3', '--output', str(tmp_path / 'mock')]) == 0
    from role_theater.config import Settings
    monkeypatch.setattr(Settings, 'model_configured', property(lambda _: False))
    assert main(['--live', '--output', str(tmp_path / 'live')]) == 3
    assert not list((tmp_path / 'live').glob('**/sample.db'))


@pytest.mark.parametrize('kind', ['TIMEOUT', 'UNKNOWN_REQUEST'])
def test_observation_cli_late_failure_is_nonzero(tmp_path, monkeypatch, kind):
    from role_theater.ports import MockModelPort
    from role_theater.contracts import ModelActionResponse, ModelFailure
    original = MockModelPort.generate_action
    async def fail_after_success(port, request):
        if port.call_count == 1:
            port.calls.append(request)
            return ModelActionResponse(ok=False, sent=kind != 'UNKNOWN_REQUEST', failure=ModelFailure(kind=kind),
                                       prompt_template_id=request.prompt_template_id)
        return await original(port, request)
    monkeypatch.setattr(MockModelPort, 'generate_action', fail_after_success)
    assert main(['--turns', '3', '--output', str(tmp_path)]) == 4
    records = [json.loads(p.read_text()) for p in tmp_path.glob('*/**/evidence.json')]
    assert len(records) == 3
    assert all(not r['observation_ok'] and r['requests'][0]['status'] == 'SUCCEEDED'
               and r['requests'][-1]['failure_kind'] == kind for r in records)
