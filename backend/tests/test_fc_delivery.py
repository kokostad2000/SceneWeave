import copy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from free_chat_observation import drive, main, observation_ok


@pytest.mark.parametrize('mode', ['simulation', 'discussion'])
@pytest.mark.parametrize('policy', [1, 2])
def test_finite_observation_records_actual_snapshots_and_rejects_failed_evidence(tmp_path, mode, policy):
    record = drive(tmp_path / f'{mode}-{policy}', live=False, mode=mode, policy=policy, turns=3)
    assert record['observation_ok']
    assert len(record['calls']) == 2
    assert record['before_stop']['pause_reason'] == ('COLLECTIVE_SILENCE' if policy == 2 else 'NO_NEW_INFORMATION')
    assert json.loads((tmp_path / f'{mode}-{policy}' / 'evidence.json').read_text())['observation_ok']
    for status in ['FAILED', 'UNKNOWN', 'PENDING']:
        broken = copy.deepcopy(record)
        broken['requests'][-1]['status'] = status
        assert not observation_ok(broken)
    for field in ['snapshot_matches', 'budget_matches', 'policy_matches']:
        broken = copy.deepcopy(record)
        broken[field] = False
        assert not observation_ok(broken)
    for pause in ['PROVIDER_ERROR', 'CONTEXT_LIMIT', 'PROCESS_INTERRUPT']:
        broken = copy.deepcopy(record)
        broken['steps'][-1]['pause_reason'] = pause
        assert not observation_ok(broken)
    broken = copy.deepcopy(record)
    broken['steps'][-1]['accepted'] = False
    assert not observation_ok(broken)
    for usage in [None, 10_000_001]:
        broken = copy.deepcopy(record)
        broken['live'] = True
        broken['calls'][-1]['response']['usage']['input_tokens'] = usage
        assert not observation_ok(broken)


def test_cli_late_failure_remains_nonzero(tmp_path, monkeypatch):
    import free_chat_observation as observation
    original = observation.drive
    def broken(*args, **kwargs):
        result = original(*args, **kwargs)
        if kwargs['mode'] == 'discussion' and kwargs['policy'] == 2:
            result['observation_ok'] = False
        return result
    monkeypatch.setattr(observation, 'drive', broken)
    assert main(['--output', str(tmp_path), '--turns', '3']) == 4
