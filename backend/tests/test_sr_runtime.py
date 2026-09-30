import json
import pytest
from role_theater.contracts import ActionDraft
from test_sr_storage import identity, create


@pytest.mark.parametrize('mode',['simulation','discussion'])
def test_sent_snapshot_uses_scene_profile_and_locks_updates(make_client,mode):
    with make_client(script=[ActionDraft(action='SPEAK',text='本場发言')]) as client:
        ids=[identity(client,n) for n in ['甲','乙']]
        scene=create(client,ids,mode,profile={'persona':'SCENE_A_PRIVATE','public_profile':'SCENE_A_PUBLIC'})
        sid=scene['scene']['scene_id']; aid=scene['agents'][0]['agent_id']
        runner=client.app.state.scene_runner; port=runner._model
        request_body={'request_id':'sr-step','command':'STEP'}
        r=client.post(f'/api/scenes/{sid}/commands',json=request_body)
        assert r.status_code==200 and r.json()['accepted']
        assert len(port.calls)==1
        req=port.calls[0]
        assert req.prompt_template_id==f'role_action@{mode}.sr.1'
        assert 'SCENE_A_PRIVATE' in req.prompt and '旧露营人设' not in req.prompt and '旧营地目标' not in req.prompt
        with client.app.state.database.connection() as c:
            row=c.execute('SELECT request_snapshot_json FROM scene_turns WHERE scene_id=?',(sid,)).fetchone()
        assert json.loads(row[0])==req.model_dump(mode='json')
        saved=client.get(f'/api/scenes/{sid}').json()['agents']
        update=client.patch(f'/api/scenes/{sid}/agents/{aid}/profile',json={'role_profile':{'persona':'拒绝修改'}})
        assert update.status_code==409
        assert client.get(f'/api/scenes/{sid}').json()['agents']==saved
        assert client.post(f'/api/scenes/{sid}/commands',json=request_body).json()==(r.json() | {'deduplicated':True})
        assert len(port.calls)==1
        assert client.get(f'/api/scenes/{sid}/agents/{scene["agents"][1]["agent_id"]}/viewpoint').status_code==200
        assert len(port.calls)==1
        runner.recover_after_restart()
        assert runner.snapshot(sid).configuration_version==2
        assert len(port.calls)==1


@pytest.mark.parametrize('mode',['simulation','discussion'])
@pytest.mark.parametrize('name',[
    'single_step_makes_exactly_one_call_and_pauses',
    'start_runs_until_budget_exhausted_then_ends',
    'events_injected_during_a_call_activate_after_it_in_order',
    'repeated_command_returns_existing_result_without_new_call',
    'restart_marks_pending_unknown_and_pauses_without_replay',
    'missing_config_pauses_without_consuming_budget',
    'requested_priority_streak_survives_runner_restart',
    'model_wait_does_not_hold_sqlite_write_transaction',
])
async def test_scene_profile_version_keeps_runtime_baselines(database,monkeypatch,mode,name):
    import test_m04_runner as base
    build=base.build_env
    def local(db,**kw):
        env=build(db,mode=mode,**kw)
        with db.transaction() as c:
            c.execute('UPDATE scenes SET configuration_version=2 WHERE scene_id=?',(env.scene_id,))
        return env
    monkeypatch.setattr(base,'build_env',local)
    await getattr(base,'test_'+name)(database)


@pytest.mark.parametrize('mode', ['simulation', 'discussion'])
def test_new_app_reopens_exact_scene_profile_and_saved_request(make_client, tmp_path, mode):
    database_url = f'sqlite:///{tmp_path / "reopen.db"}'
    with make_client(database_url=database_url) as client:
        ids = [identity(client, name) for name in ['甲', '乙']]
        detail = create(client, ids, mode)
        sid = detail['scene']['scene_id']
        aid = detail['agents'][0]['agent_id']
        body = {'role_profile': {'public_profile': '本场介绍', 'private_background': '本场背景'}}
        if mode == 'discussion':
            body['discussion_config'] = {'focus': '本场关注', 'initial_position': '初始想法'}
        assert client.patch(f'/api/scenes/{sid}/agents/{aid}/profile', json=body).status_code == 200
        # 后续目录编辑不能改变本场快照。
        assert client.patch(f'/api/templates/{ids[0]}', json={'persona': '目录后改设定'}).status_code == 200
        command = {'request_id': 'reopen-step', 'command': 'STEP'}
        assert client.post(f'/api/scenes/{sid}/commands', json=command).json()['accepted']
        saved_detail = client.get(f'/api/scenes/{sid}').json()
        saved_turns = client.app.state.runtime_repository.list_turns(sid)
        assert '本场背景' in saved_turns[0]['request_snapshot_json']
        assert '目录后改设定' not in saved_turns[0]['request_snapshot_json']
    with make_client(database_url=database_url) as reopened:
        assert reopened.get(f'/api/scenes/{sid}').json() == saved_detail
        assert reopened.app.state.runtime_repository.list_turns(sid) == saved_turns
        assert reopened.post(f'/api/scenes/{sid}/commands', json=command).json()['deduplicated']
        assert reopened.app.state.scene_runner._model.call_count == 0
        assert reopened.patch(f'/api/scenes/{sid}/agents/{aid}/profile', json=body).status_code == 409
