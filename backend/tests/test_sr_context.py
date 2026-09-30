from dataclasses import replace
import pytest
from role_theater.context import ContextBuilder
from role_theater.contracts import SceneMode, DiscussionConfig, SimulationConfig, RoleCursor
from role_theater.scheduling import Scheduler, SchedulerState
from test_m02_context import _scene, _message


@pytest.mark.parametrize('mode',list(SceneMode))
def test_local_fields_and_public_roster_are_filtered_before_render(mode):
    old=_scene()
    agents=[]
    for i,a in enumerate(old.agents):
        p=a.snapshot.model_dump()
        for key in ['persona','speech_style','initial_goal','private_background']:
            p[key]=f'SCENE_PRIVATE_{i}_{key}'
        p['public_profile']=f'SCENE_PUBLIC_{i}'
        agents.append(replace(a,snapshot=type(a.snapshot).model_validate(p)))
    config=DiscussionConfig(topic='议题') if mode==SceneMode.DISCUSSION else SimulationConfig(situation='情境')
    s=replace(old,mode=mode,background=config.background_text(),mode_config=config,
              configuration_version=2,agents=tuple(agents))
    for i,a in enumerate(agents):
        ctx=ContextBuilder().build(s,a.agent_id)
        assert ctx.prompt_template_id==f'role_action@{mode.value}.sr.1'
        assert f'SCENE_PRIVATE_{i}_' in ctx.prompt
        for j in range(len(agents)):
            assert f'SCENE_PUBLIC_{j}' in ctx.prompt
            if i!=j: assert f'SCENE_PRIVATE_{j}_' not in ctx.prompt
    assert ContextBuilder().build(replace(s,configuration_version=1),agents[0].agent_id).prompt_template_id==f'role_action@{mode.value}.p1.1'


def test_configuration_version_and_profile_text_do_not_change_scheduler():
    base=_scene((_message(1,'agt-an','安然','新信息',requested_speaker_id='agt-xu'),))
    cursors=tuple(RoleCursor(scene_id=base.scene_id,agent_id=a.agent_id) for a in base.agents)
    original=SchedulerState(base,cursors,0); scheduler=Scheduler()
    version_only=replace(original,scene=replace(base,configuration_version=2))
    assert scheduler.select(version_only)==scheduler.select(original)
    assert scheduler.candidates(version_only)==scheduler.candidates(original)
    profiles=tuple(replace(a,snapshot=a.snapshot.model_copy(update={'persona':'本场新角色','initial_goal':''})) for a in base.agents)
    new=replace(original,scene=replace(base,configuration_version=2,agents=profiles))
    assert scheduler.select(new)==scheduler.select(original)
    expected=scheduler.candidates(original)
    actual=scheduler.candidates(new)
    assert [(c.agent.agent_id,c.reason,c.based_on_seq) for c in actual]==[(c.agent.agent_id,c.reason,c.based_on_seq) for c in expected]
