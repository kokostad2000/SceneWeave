"""FC-10: actual prompt counts, read-only API and private visibility."""
from role_theater.contracts import ActionDraft


def test_context_metadata_is_actual_read_only_and_private_to_the_viewer(make_client):
    with make_client() as client:
        detail = client.post('/api/scenes/preset', json={}).json()
        scene = detail['scene']['scene_id']
        a, b, c = [agent['agent_id'] for agent in detail['agents']]
        runner = client.app.state.scene_runner
        port = runner._model
        path = f'/api/scenes/{scene}'
        third_before = client.get(f'{path}/agents/status', params={'viewer_id': c}).json()
        viewpoint_before = client.get(f'{path}/agents/{c}/viewpoint').json()
        port._script = [ActionDraft(action='PRIVATE', recipient_id=b, text='PRIVATE_COUNT_MARKER')]
        ack = client.post(f'{path}/commands', json={'request_id': 'private', 'command': 'STEP'})
        assert ack.status_code == 200
        third_after = client.get(f'{path}/agents/status', params={'viewer_id': c}).json()
        viewpoint_after = client.get(f'{path}/agents/{c}/viewpoint').json()
        assert third_before == third_after
        assert viewpoint_before == viewpoint_after
        assert len(third_after['agents']) == 1
        assert third_after['agents'][0]['agent_id'] == c
        assert 'PRIVATE_COUNT_MARKER' not in str(third_after)
        observer = client.get(f'{path}/agents/status').json()
        assert len(observer['agents']) == 3
        for item in observer['agents']:
            assert item['prompt_codepoints'] == len(runner.viewpoint(scene, item['agent_id'])[1].prompt)
            assert item['max_prompt_codepoints'] == 32000
        assert observer['agents'][1]['prompt_codepoints'] > third_after['agents'][0]['prompt_codepoints']
        assert viewpoint_after['prompt_codepoints'] == len(runner.viewpoint(scene, c)[1].prompt)
        assert port.call_count == 1
