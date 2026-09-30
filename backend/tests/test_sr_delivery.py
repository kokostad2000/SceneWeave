import copy
import json

import pytest

from scene_role_observation import drive, main, observation_ok


@pytest.mark.parametrize('case', ['empty-discussion', 'preset-simulation'])
def test_observation_checks_actual_input_and_failures(tmp_path, case):
    record = drive(tmp_path / case, live=False, case=case, turns=3)
    assert record['observation_ok']
    assert record['profile_matches'] and record['no_legacy_profile_in_input']
    assert len(record['calls']) == 3
    for key in ('profile_matches', 'new_prompt_matches', 'snapshot_matches', 'budget_matches'):
        broken = copy.deepcopy(record)
        broken[key] = False
        assert not observation_ok(broken)
    for usage in ({'input_tokens': None, 'output_tokens': None}, {'input_tokens': 10_000_000, 'output_tokens': 1}):
        broken = copy.deepcopy(record)
        broken['live'] = True
        broken['calls'][-1]['response']['usage'].update(usage)
        assert not observation_ok(broken)
    assert json.loads((tmp_path / case / 'evidence.json').read_text())['observation_ok']


def test_cli_mock_and_missing_live_config(tmp_path, monkeypatch):
    assert main(['--output', str(tmp_path / 'mock')]) == 0
    from role_theater.config import Settings
    monkeypatch.setattr(Settings, 'model_configured', property(lambda _: False))
    assert main(['--live', '--output', str(tmp_path / 'live')]) == 3
    assert not list((tmp_path / 'live').glob('**/sample.db'))


@pytest.mark.parametrize('kind', ['TIMEOUT', 'UNKNOWN_REQUEST'])
def test_cli_late_failure_stays_nonzero(tmp_path, monkeypatch, kind):
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
    assert main(['--output', str(tmp_path)]) == 4
    records = [json.loads(p.read_text()) for p in tmp_path.glob('*/**/evidence.json')]
    assert len(records) == 2
    assert all(not r['observation_ok'] and r['requests'][0]['status'] == 'SUCCEEDED'
               and r['requests'][-1]['failure_kind'] == kind for r in records)
