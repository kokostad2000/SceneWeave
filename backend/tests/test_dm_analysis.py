"""P1：同一分析器，两模式公开选材、整组拒绝与只读隔离。"""
import json

import pytest

from role_theater.analysis import ControlledAnalysisClient, ExternalAnalysisPort
from role_theater.contracts import ActionDraft, SceneMode
from role_theater.ports import DisabledAnalysisPort
from test_dm_runtime import create_http_scene
from test_m06_api import FakeAnalyzer


@pytest.mark.parametrize('mode', list(SceneMode))
def test_manual_analysis_and_private_mixed_selection(make_client, mode):
    analyzer = FakeAnalyzer()
    analysis_port = ExternalAnalysisPort(analyzer=analyzer, client=ControlledAnalysisClient())
    with make_client(injected_analysis_port=analysis_port) as client:
        detail = create_http_scene(client, mode)
        sid = detail['scene']['scene_id']
        a, b, c = [r['agent_id'] for r in detail['agents']]
        runtime = client.app.state.runtime_repository
        port = client.app.state.scene_runner._model
        port._script = [ActionDraft(action='PRIVATE', text='SECRET_ANALYSIS_UNIQUE', recipient_id=b),
                        ActionDraft(action='SPEAK', text='这是一条公开转述，只按这条新消息分析。'),
                        ActionDraft(action='PASS')]
        for n in range(3):
            ack = client.post(f'/api/scenes/{sid}/commands', json={'request_id': f's{n}', 'command': 'STEP'})
            assert ack.status_code == 200 and ack.json()['accepted']
        assert port.call_count == 3
        capability = client.get(f'/api/scenes/{sid}/analyses/capability').json()['capability']
        assert capability['analyzer_id'] == 'behavior'
        assert capability['supported_modes'] == ['simulation', 'discussion']
        assert capability['recommended_modes'] == ['simulation']
        assert capability['enabled'] is True  # 推荐不限制 discussion。
        before = (client.app.state.scene_runner.snapshot(sid), runtime.list_cursors(sid), runtime.requested_priority_streak(sid))
        for seqs in ([1, 2], [2, 3], [2, 999]):
            blocked = client.post(f'/api/scenes/{sid}/analyses', json={'agent_id': b, 'material_seqs': seqs})
            assert blocked.status_code == 201
            assert blocked.json()['status'] == 'BLOCKED'
            assert blocked.json()['provider_attempts'] == 0
            assert blocked.json()['materials'] == []
            assert not analyzer.requests
            assert runtime.budget_used(sid)['analysis_requests_used'] == 0
        response = client.post(f'/api/scenes/{sid}/analyses', json={'agent_id': b, 'material_seqs': [2]})
        assert response.status_code == 201 and response.json()['status'] == 'NORMAL'
        assert len(analyzer.requests) == 1
        request = analyzer.requests[0]
        assert request.persist_profile is False
        assert [m.text for m in request.materials] == ['这是一条公开转述，只按这条新消息分析。']
        captured = json.dumps(request.model_dump(mode='json'), ensure_ascii=False)
        for secret in ('SECRET_ANALYSIS_UNIQUE', 'PRIVATE_0', 'PRIVATE_1', 'FOCUS_0', 'FOCUS_1', 'POSITION_0', 'POSITION_1'):
            assert secret not in captured
        assert before == (client.app.state.scene_runner.snapshot(sid), runtime.list_cursors(sid), runtime.requested_priority_streak(sid))
        assert port.call_count == 3
        assert runtime.budget_used(sid)['analysis_requests_used'] == 1


@pytest.mark.parametrize('mode', list(SceneMode))
@pytest.mark.parametrize('reason', ['分析开关关闭', 'external_package_not_installed'])
def test_disabled_analysis_does_not_affect_role_runtime(make_client, mode, reason):
    with make_client(injected_analysis_port=DisabledAnalysisPort(reason=reason)) as client:
        detail = create_http_scene(client, mode)
        sid = detail['scene']['scene_id']
        agent_id = detail['agents'][0]['agent_id']
        port = client.app.state.scene_runner._model
        port._script = [ActionDraft(action='SPEAK', text='正常公开互动。'), ActionDraft(action='PASS')]
        for n in range(2):
            assert client.post(f'/api/scenes/{sid}/commands', json={'request_id': f's{n}', 'command': 'STEP'}).json()['accepted']
        result = client.post(f'/api/scenes/{sid}/analyses', json={'agent_id': agent_id, 'material_seqs': [1]}).json()
        assert result['status'] == 'DISABLED' and result['provider_attempts'] == 0
        assert reason in result['error']
        assert client.get(f'/api/scenes/{sid}/analyses/capability').json()['capability']['reason'] == reason
        assert port.call_count == 2
        assert client.app.state.runtime_repository.budget_used(sid)['analysis_requests_used'] == 0
