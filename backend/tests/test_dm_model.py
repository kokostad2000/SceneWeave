import pytest

from role_theater.context import ContextBuilder
from role_theater.contracts import SceneMode, ActionDraft, ModelActionRequest, ModelParams, ReferenceScope
from role_theater.ports import DeepSeekModelClient
from test_dm_context import mode_scene
from test_m03_model_adapter import RecordingTransport, _completion


def request(mode, **kwargs):
    ctx=ContextBuilder().build(mode_scene(mode),"agt-xu")
    kwargs.setdefault('params', ModelParams(max_output_tokens=1024))
    return ModelActionRequest(scene_id="scn-1",actor_id="agt-xu",prompt_template_id=ctx.prompt_template_id,
        prompt=ctx.prompt,cursor_seq=ctx.cutoff_seq,**kwargs)


@pytest.mark.parametrize("mode",list(SceneMode))
@pytest.mark.parametrize("choice",["public","initiate","reply","silence"])
async def test_same_port_four_actions_and_actual_prompt(mode,choice):
    drafts={"public":ActionDraft(action="SPEAK",text="公开观点"),
        "initiate":ActionDraft(action="PRIVATE",text="私人询问",recipient_id="agt-ch"),
        "reply":ActionDraft(action="PRIVATE",text="回应",recipient_id="agt-an",reply_to_message_id="received"),
        "silence":ActionDraft(action="PASS")}
    scope=ReferenceScope(actor_id="agt-xu",allowed_speaker_ids=["agt-an","agt-ch"],received_private_messages={"received":"agt-an"})
    req=request(mode,references=scope)
    transport=RecordingTransport([_completion("stop",drafts[choice].model_dump_json())])
    result=await DeepSeekModelClient(api_key="placeholder-key",transport=transport).generate_action(req)
    assert result.ok and result.draft==drafts[choice]
    assert len(transport.requests)==1
    payload=transport.payloads[0]
    assert payload["messages"][0]["content"]==req.prompt
    assert payload["max_tokens"]==1024 and payload["stream"] is False and "tools" not in payload
    assert payload["thinking"]=={"type":"disabled"}
    assert result.prompt_template_id==req.prompt_template_id


@pytest.mark.parametrize("mode",list(SceneMode))
@pytest.mark.parametrize("finish,content,kind",[
    ("stop","","EMPTY_CONTENT"),("length",'{"action":"PASS"}',"TRUNCATED"),
    ("stop","{invalid","INVALID_JSON"),("stop",'{"action":"PASS","actor_id":"fake"}',"SCHEMA_INVALID"),
    ("stop",'{"action":"SPEAK","text":"'+"x"*201+'"}',"SCHEMA_INVALID"),
    ("stop",'{"action":"PRIVATE","text":"x","recipient_id":"outside"}',"REFERENCE_INVALID"),
])
async def test_both_modes_failure_classification(mode,finish,content,kind):
    transport=RecordingTransport([_completion(finish,content)])
    result=await DeepSeekModelClient(api_key="placeholder-key",transport=transport).generate_action(
        request(mode,references=ReferenceScope(actor_id="agt-xu",allowed_speaker_ids=["agt-an","agt-ch"])))
    assert not result.ok and result.failure.kind==kind and len(transport.requests)==1


@pytest.mark.parametrize("mode",list(SceneMode))
@pytest.mark.parametrize("key",[None,"","placeholder"])
async def test_credentials_and_token_guard(mode,key):
    transport=RecordingTransport()
    client=DeepSeekModelClient(api_key=key,transport=transport)
    result=await client.generate_action(request(mode))
    assert result.ok is bool(key)
    assert len(transport.requests)==int(bool(key))
    transport.requests.clear()
    excessive=await client.generate_action(request(mode,params=ModelParams(max_output_tokens=10_000_000)))
    assert not excessive.ok and not excessive.sent and transport.requests==[]
