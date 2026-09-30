import asyncio
import json

import pytest

from role_theater.contracts import SceneMode, ActionDraft, ModelFailure, ControlCommandType
from test_m04_runner import build_env
import test_m04_runner as base
import test_pc_runtime as pc
from test_m04_sse import read_sse


@pytest.mark.parametrize("mode",list(SceneMode))
@pytest.mark.parametrize("name",[
    "single_step_makes_exactly_one_call_and_pauses", "start_runs_until_no_new_information",
    "start_runs_until_budget_exhausted_then_ends", "events_injected_during_a_call_activate_after_it_in_order",
    "repeated_command_returns_existing_result_without_new_call", "restart_marks_pending_unknown_and_pauses_without_replay",
    "missing_config_pauses_without_consuming_budget", "context_limit_pauses_without_consuming_budget",
    "requested_priority_streak_survives_runner_restart", "pass_counts_priority_and_normal_pass_resets_streak",
    "success_commit_failure_exposes_no_partial_action", "model_wait_does_not_hold_sqlite_write_transaction",
])
async def test_both_modes_existing_runtime_contracts(database,monkeypatch,mode,name):
    monkeypatch.setattr(base,"build_env",lambda db,**kw:build_env(db,mode=mode,**kw))
    if name == "success_commit_failure_exposes_no_partial_action":
        await base.test_success_commit_failure_exposes_no_partial_action(database,"turn")
    else:
        await getattr(base,"test_"+name)(database)


@pytest.mark.parametrize("mode",list(SceneMode))
@pytest.mark.parametrize("stage",["cursor","scheduler"])
async def test_both_modes_additional_commit_faults(database,monkeypatch,mode,stage):
    monkeypatch.setattr(base,"build_env",lambda db,**kw:build_env(db,mode=mode,**kw))
    await base.test_success_commit_failure_exposes_no_partial_action(database,stage)


@pytest.mark.parametrize("mode",list(SceneMode))
@pytest.mark.parametrize("choice",["public","initiate","reply","silence"])
@pytest.mark.parametrize("control",["PAUSE","STOP"])
async def test_both_modes_control_and_event_boundary(database,monkeypatch,mode,choice,control):
    monkeypatch.setattr(pc,"build_env",lambda db,**kw:build_env(db,mode=mode,**kw))
    await pc.test_pc_four_actions_control_event_boundary(database,choice,control)


@pytest.mark.parametrize("mode",list(SceneMode))
@pytest.mark.parametrize("table,operation",[("messages","INSERT"),("scene_turns","UPDATE"),("role_cursors","INSERT"),("scene_scheduler_state","INSERT")])
async def test_both_modes_private_atomic_fault(database,monkeypatch,mode,table,operation):
    monkeypatch.setattr(pc,"build_env",lambda db,**kw:build_env(db,mode=mode,**kw))
    await pc.test_pc_private_atomic_fault(database,table,operation)


@pytest.mark.parametrize("mode",list(SceneMode))
async def test_actual_private_snapshot_and_relay(database,monkeypatch,mode):
    monkeypatch.setattr(pc,"build_env",lambda db,**kw:build_env(db,mode=mode,**kw))
    await pc.test_pc_actual_requests_silence_old_reply_relay(database)


def create_http_scene(client,mode):
    agents=[]
    for i in range(3):
        t=client.post('/api/templates',json=dict(name=f"角色{i}",public_profile=f"PUBLIC_{i}",persona=f"PRIVATE_{i}",speech_style='',initial_goal='',private_background='')).json()
        agents.append(dict(template_id=t['template_id'],**({'discussion_config':{'focus':f'FOCUS_{i}', 'initial_position': f'POSITION_{i}' if i < 2 else None}} if mode=='discussion' else {})))
    r=client.post('/api/scenes',json=dict(title=f'{mode} 场景',mode=mode,chat_policy_version=1,
        mode_config={'topic':'议题'} if mode=='discussion' else {'situation':'情境'},agents=agents))
    assert r.status_code==201
    return r.json()


@pytest.mark.parametrize("mode",list(SceneMode))
def test_statistics_viewpoint_sse_and_snapshot_do_not_dispatch(make_client,mode):
    with make_client() as client:
        scene=create_http_scene(client,mode); sid=scene['scene']['scene_id']; a,b,c=[x['agent_id'] for x in scene['agents']]
        port=client.app.state.scene_runner._model
        def step(n):
            r=client.post(f'/api/scenes/{sid}/commands',json=dict(request_id=f's{n}',command='STEP'))
            assert r.status_code==200 and r.json()['accepted']
        port._script=[ActionDraft(action='PRIVATE',text='HIDDEN_UNIQUE',recipient_id=b)]
        step(0)
        msg=client.get(f'/api/scenes/{sid}/timeline').json()['entries'][0]['message']
        port._script=[ActionDraft(action='PRIVATE',text='reply',recipient_id=a,reply_to_message_id=msg['message_id']),ActionDraft(action='SPEAK',text='观点改变，初始快照不改写'),ActionDraft(action='PASS'),ModelFailure(kind='TIMEOUT')]
        for n in range(1,5): step(n)
        turns=client.app.state.runtime_repository.list_turns(sid)
        for turn,call in zip(turns,port.calls,strict=True):
            assert json.loads(turn['request_snapshot_json'])==call.model_dump(mode='json')
            assert turn['prompt_template_id']==f'role_action@{mode}.p1.1'
        calls=port.call_count
        observer=client.get(f'/api/scenes/{sid}/statistics').json()
        assert observer['public_messages']==1 and observer['private_messages']==2
        assert len(observer['reply_relations'])==1
        assert sum(r['succeeded'] for r in observer['role_actions'])==4
        assert sum(r['passes'] for r in observer['role_actions'])==1
        assert sum(r['failed'] for r in observer['role_actions'])==1
        legal=client.get(f'/api/scenes/{sid}/statistics?viewer_id={c}').json()
        assert legal['private_messages']==0 and legal['reply_relations']==[]
        assert [r['agent_id'] for r in legal['role_actions']]==[c]
        assert msg['message_id'] not in json.dumps(legal)
        assert client.get(f'/api/scenes/{sid}/statistics?viewer_id=outside').status_code==404
        view=client.get(f'/api/scenes/{sid}/agents/{c}/viewpoint').text
        assert 'HIDDEN_UNIQUE' not in view and msg['message_id'] not in view and 'PRIVATE_0' not in view
        if mode=='discussion': assert 'FOCUS_0' not in view
        if mode=='discussion':
            assert 'POSITION_0' not in view and 'POSITION_1' not in view
            assert client.get(f'/api/scenes/{sid}').json()['agents'] == scene['agents']
            assert scene['agents'][0]['discussion_config']['initial_position'] == 'POSITION_0'
        first=read_sse(client,sid,since_seq=0,replay_limit=10)
        second=read_sse(client,sid,since_seq=0,replay_limit=10)
        assert first==second and len(first)==3
        assert read_sse(client,sid,since_seq=first[-1]['seq'],replay_limit=10)==[]
        assert client.get(f'/api/scenes/{sid}').json()==dict(scene,locked=True,scene=client.get(f'/api/scenes/{sid}').json()['scene'])
        assert port.call_count==calls==5


async def test_runtime_decisions_counts_and_recovery_equal_across_modes(tmp_path):
    from role_theater.storage import Database
    traces=[]
    for mode in SceneMode:
        db=Database(tmp_path/f'{mode}.db');db.migrate();env=build_env(db,mode=mode)
        a,b,c=env.agent_ids
        env.port._script=[ActionDraft(action='SPEAK',text='public',requested_speaker_id=b),ActionDraft(action='PRIVATE',text='private',recipient_id=a),ActionDraft(action='PASS'),ActionDraft(action='PASS'),ModelFailure(kind='TIMEOUT')]
        trace=[]
        for n in range(6):
            await env.runner.run_command(env.scene_id,request_id=f's{n}',command=ControlCommandType.STEP)
            trace.append(([(r.agent_id,r.processed_seq,r.startup_opportunity_consumed) for r in env.runtime.list_cursors(env.scene_id)],
                [(t['actor_id'],t['status'],t['input_cursor_seq']) for t in env.runtime.list_turns(env.scene_id)],
                env.runtime.requested_priority_streak(env.scene_id),env.runtime.budget_used(env.scene_id),env.port.call_count))
        before=env.port.call_count;env.runner.recover_after_restart();assert env.port.call_count==before
        traces.append(trace)
    assert traces[0]==traces[1]
