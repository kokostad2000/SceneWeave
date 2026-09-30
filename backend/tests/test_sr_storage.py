import sqlite3
import pytest

from role_theater.storage import Database
from role_theater.storage import migrator


def identity(client,name):
    r=client.post('/api/templates',json={'name':name,'persona':'旧露营人设',
        'speech_style':'旧表达','initial_goal':'旧营地目标','private_background':'旧私人背景','public_profile':'旧公开身份'})
    assert r.status_code==201
    return r.json()['template_id']


def create(client,ids,mode='discussion',version=2,profile=None):
    agents=[{'template_id':tid} for tid in ids]
    if profile is not None: agents[0]['role_profile']=profile
    r=client.post('/api/scenes',json=dict(title='本场',mode=mode,configuration_version=version,chat_policy_version=1,
        mode_config={'topic':'新议题'} if mode=='discussion' else {'situation':'新情境'},agents=agents))
    assert r.status_code==201,r.text
    return r.json()


@pytest.mark.parametrize('mode',['simulation','discussion'])
@pytest.mark.parametrize('count',[2,3,5,8])
def test_scene_local_profiles_are_empty_or_explicit(api_client,mode,count):
    ids=[identity(api_client,f'人物{i}') for i in range(count)]
    clean=create(api_client,ids,mode)
    fields=('persona','speech_style','initial_goal','private_background','public_profile')
    assert all(not a['snapshot'][f] for a in clean['agents'] for f in fields)
    b=create(api_client,ids,mode,profile={'initial_goal':'本场目标','persona':'本场人设'})
    assert b['agents'][0]['snapshot']['initial_goal']=='本场目标'
    assert b['agents'][0]['snapshot']['private_background']==''
    assert clean['agents'][0]['agent_id'] != b['agents'][0]['agent_id']
    assert api_client.get('/api/scenes/'+clean['scene']['scene_id']).json()==clean
    legacy=create(api_client,ids,mode,version=1)
    assert legacy['agents'][0]['snapshot']['initial_goal']=='旧营地目标'


def test_edit_local_profile_persists_without_changing_identity_or_other_scene(api_client):
    ids=[identity(api_client,n) for n in ['甲','乙']]
    a=create(api_client,ids); b=create(api_client,ids)
    aid=a['agents'][0]['agent_id']; sid=a['scene']['scene_id']; path=f'/api/scenes/{sid}/agents/{aid}/profile'
    r=api_client.patch(path,json={'role_profile':{'private_background':'只有本场甲知道'},
                                 'discussion_config':{'initial_position':'本场想法'}})
    assert r.status_code==200,r.text
    assert r.json()['snapshot']['persona']==''
    assert api_client.get('/api/templates/'+ids[0]).json()['private_background']=='旧私人背景'
    assert api_client.get('/api/scenes/'+b['scene']['scene_id']).json()==b
    r=api_client.patch(path,json={'role_profile':{}})
    assert r.json()['discussion_config']['initial_position']=='本场想法'
    r=api_client.patch(path,json={'role_profile':{},'discussion_config':{}})
    assert r.json()['discussion_config']['initial_position'] is None
    assert api_client.get('/api/scenes/'+sid).json()['agents'][0]['snapshot']==r.json()['snapshot']
    api_client.delete('/api/templates/'+ids[0])
    assert api_client.get('/api/scenes/'+sid).status_code==200


def test_old_scene_cannot_be_silently_reconfigured(api_client):
    ids=[identity(api_client,n) for n in ['甲','乙']]
    a=create(api_client,ids,version=1); sid=a['scene']['scene_id'];aid=a['agents'][0]['agent_id']
    r=api_client.patch(f'/api/scenes/{sid}/agents/{aid}/profile',json={'role_profile':{}})
    assert r.status_code==422
    assert api_client.get('/api/scenes/'+sid).json()==a


@pytest.mark.parametrize('mode', ['simulation', 'discussion'])
def test_adding_actor_preserves_configuration_version_rules(api_client, mode):
    ids = [identity(api_client, name) for name in ['甲', '乙', '丙']]
    old = create(api_client, ids[:2], mode, version=1)
    sid = old['scene']['scene_id']
    for profile in (None, {}):
        response = api_client.post(f'/api/scenes/{sid}/agents',
                                   json={'template_id': ids[2], 'role_profile': profile})
        assert response.status_code == 422
        assert api_client.get('/api/scenes/' + sid).json() == old
    # 原旧请求不带新字段，仍复制原设定。
    legacy = api_client.post(f'/api/scenes/{sid}/agents', json={'template_id': ids[2]})
    assert legacy.status_code == 201
    assert legacy.json()['snapshot']['persona'] == '旧露营人设'
    current = create(api_client, ids[:2], mode)
    response = api_client.post(f'/api/scenes/{current["scene"]["scene_id"]}/agents',
                               json={'template_id': ids[2], 'role_profile': {'persona': '本场新增'}})
    assert response.status_code == 201
    assert response.json()['snapshot']['persona'] == '本场新增'
    assert response.json()['snapshot']['initial_goal'] == ''


def test_locked_profile_rejected_and_snapshot_unchanged(api_client):
    ids=[identity(api_client,n) for n in ['甲','乙']]
    a=create(api_client,ids);sid=a['scene']['scene_id'];aid=a['agents'][0]['agent_id']
    api_client.app.state.scene_service.lock(sid)
    r=api_client.patch(f'/api/scenes/{sid}/agents/{aid}/profile',json={'role_profile':{'persona':'不应生效'}})
    assert r.status_code==409
    assert api_client.get('/api/scenes/'+sid).json()['agents']==a['agents']


def test_first_request_lock_race_is_rechecked_inside_write(api_client, monkeypatch):
    ids = [identity(api_client, name) for name in ['甲', '乙']]
    detail = create(api_client, ids)
    sid = detail['scene']['scene_id']
    aid = detail['agents'][0]['agent_id']
    repository = api_client.app.state.scene_service._scenes
    original = repository.update_agent_profile

    def lock_before_write(agent):
        api_client.app.state.scene_service.lock(sid)
        return original(agent)

    monkeypatch.setattr(repository, 'update_agent_profile', lock_before_write)
    response = api_client.patch(f'/api/scenes/{sid}/agents/{aid}/profile',
                                json={'role_profile': {'persona': '迟到的修改'}})
    assert response.status_code == 409
    assert api_client.get('/api/scenes/' + sid).json()['agents'] == detail['agents']


def test_preset_uses_scene_definition_not_identity_data(api_client):
    tid=identity(api_client,'何澜')
    r=api_client.post('/api/scenes/preset',json={'preset_key':'campsite','configuration_version':2})
    assert r.status_code==201,r.text
    a=next(a for a in r.json()['agents'] if a['name']=='何澜')
    assert a['snapshot']['source_template_id']==tid
    assert a['snapshot']['initial_goal']=='想在天黑前把营地安顿好。'
    assert api_client.get('/api/templates/'+tid).json()['initial_goal']=='旧营地目标'
    templates=api_client.get('/api/templates').json()['templates']
    assert {t['name'] for t in templates}=={'何澜','苏木','涂山'}
    assert all(t['persona']=='' for t in templates if t['name']!='何澜')


def test_upgrade_preserves_old_fields_and_rollback(tmp_path,monkeypatch):
    migrations=migrator.discover_migrations()[:8]; assert migrations[-1].version==8
    db=Database(tmp_path/'old.db')
    with monkeypatch.context() as m:
        m.setattr(migrator,'discover_migrations',lambda:migrations[:7]);db.migrate()
    with db.transaction() as c:
        c.execute("INSERT INTO scenes(scene_id,title,background,status,schema_version,max_role_requests,max_analysis_requests,created_at) VALUES ('old','旧场','旧情境','READY',1,200,4,'2026-09-29T00:00:00+00:00')")
    with db.connection() as c:
        tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        before={t:[dict(r) for r in c.execute(f'SELECT * FROM "{t}"')] for t in tables}
    broken=migrator.Migration(8,'scene_role_profile',migrations[-1].sql+'\nSELECT * FROM missing_sr_table;')
    with monkeypatch.context() as m:
        m.setattr(migrator,'discover_migrations',lambda:[*migrations[:7],broken])
        with pytest.raises(sqlite3.OperationalError): db.migrate()
    with db.connection() as c:
        assert 'configuration_version' not in [r['name'] for r in c.execute('PRAGMA table_info(scenes)')]
    with monkeypatch.context() as m:
        m.setattr(migrator,'discover_migrations',lambda:migrations)
        assert db.migrate()==[8];assert db.migrate()==[]
    with db.connection() as c:
        assert c.execute('SELECT configuration_version FROM scenes').fetchone()[0]==1
        for t,rows in before.items():
            columns=[r['name'] for r in c.execute(f'PRAGMA table_info("{t}")') if r['name']!='configuration_version']
            projection=','.join('"'+x+'"' for x in columns)
            after=[dict(r) for r in c.execute(f'SELECT {projection} FROM "{t}"'+(' WHERE version<=7' if t=='schema_migrations' else ''))]
            assert after==rows
