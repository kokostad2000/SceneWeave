"""FC-11: long chat preserves 4000-codepoint analysis and read-only state."""
from role_theater.analysis import ControlledAnalysisClient, ExternalAnalysisPort
from role_theater.contracts import ActionDraft
from test_m06_api import FakeAnalyzer


def test_long_messages_require_smaller_selection_without_truncating_or_changing_chat(make_client):
    analyzer = FakeAnalyzer()
    port = ExternalAnalysisPort(analyzer=analyzer, client=ControlledAnalysisClient())
    # 4 own long messages exceed 4000 after source annotations; 3 still fit.
    script = [ActionDraft(action='SPEAK', text='字' * 1000) if i % 3 == 0
              else ActionDraft(action='PASS') for i in range(10)]
    script.extend([ActionDraft(action='PASS')] * 3)
    with make_client(script, analysis_enabled=True, injected_analysis_port=port) as client:
        detail = client.post('/api/scenes/preset', json={}).json()
        scene = detail['scene']['scene_id']
        actor = detail['agents'][0]['agent_id']
        path = f'/api/scenes/{scene}'
        for i in range(13):
            ack = client.post(f'{path}/commands', json={'request_id': f's{i}', 'command': 'STEP'}).json()
            assert ack['accepted']
        state_before = client.get(f'{path}/state').json()
        assert state_before['pause_reason'] == 'COLLECTIVE_SILENCE'
        messages = client.get(f'{path}/timeline').json()['entries']
        assert len(messages) == 4
        assert all(len(item['message']['text']) == 1000 for item in messages)
        seqs = [item['seq'] for item in messages]
        blocked = client.post(f'{path}/analyses', json={'agent_id': actor, 'material_seqs': seqs}).json()
        assert blocked['status'] == 'BLOCKED'
        assert '缩小选择' in blocked['error']
        assert blocked['provider_attempts'] == 0 and not analyzer.requests
        assert client.get(f'{path}/state').json() == state_before
        allowed = client.post(f'{path}/analyses', json={'agent_id': actor, 'material_seqs': seqs[:3]}).json()
        assert allowed['status'] == 'NORMAL'
        assert len(analyzer.requests) == 1
        request = analyzer.requests[0]
        assert len(request.behavior_description) <= 4000
        assert request.behavior_description.count('字') == 3000
        after = client.get(f'{path}/state').json()
        assert after['status'] == state_before['status'] and after['pause_reason'] == state_before['pause_reason']
        assert after['role_requests_used'] == state_before['role_requests_used']
        assert client.app.state.analysis_service.scene_state_unchanged(scene)


def test_long_private_content_remains_blocked_without_analysis_request(make_client):
    analyzer = FakeAnalyzer()
    port = ExternalAnalysisPort(analyzer=analyzer, client=ControlledAnalysisClient())
    with make_client(analysis_enabled=True, injected_analysis_port=port) as client:
        detail = client.post('/api/scenes/preset', json={}).json()
        scene = detail['scene']['scene_id']
        a, b, _ = [agent['agent_id'] for agent in detail['agents']]
        runner = client.app.state.scene_runner
        runner._model._script = [ActionDraft(action='PRIVATE', recipient_id=b, text='私' * 1000)]
        path = f'/api/scenes/{scene}'
        client.post(f'{path}/commands', json={'request_id': 'private', 'command': 'STEP'})
        before = client.get(f'{path}/state').json()
        blocked = client.post(f'{path}/analyses', json={'agent_id': a, 'material_seqs': [1]}).json()
        assert blocked['status'] == 'BLOCKED' and '私聊' in blocked['error']
        assert blocked['provider_attempts'] == 0 and not analyzer.requests
        assert client.get(f'{path}/state').json() == before
