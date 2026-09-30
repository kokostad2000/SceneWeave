import pytest
from pydantic import ValidationError

from role_theater.contracts import SceneRoleProfile, CONTRACT_MODELS
from role_theater.contracts.api import SceneCreateRequest, TemplateCreateRequest, AgentProfileUpdateRequest


def payload(**extra):
    return dict(title="讨论", mode="discussion", mode_config={"topic": "议题"},
                agents=[{"template_id": "tpl-a"}, {"template_id": "tpl-b"}], **extra)


def test_empty_profile_and_name_only_identity():
    assert set(SceneRoleProfile().model_dump().values()) == {""}
    assert TemplateCreateRequest(name="人物").initial_goal == ""
    assert SceneCreateRequest(**payload()).configuration_version == 1
    assert SceneCreateRequest(**payload(configuration_version=2)).agents[0].role_profile is None
    assert "SceneRoleProfile" in CONTRACT_MODELS and "AgentProfileUpdateRequest" in CONTRACT_MODELS


@pytest.mark.parametrize("version", [0, 3, True, "2", 2.0, None])
def test_invalid_configuration_versions(version):
    with pytest.raises(ValidationError):
        SceneCreateRequest(**payload(configuration_version=version))


def test_profile_must_be_explicitly_new_version():
    data=payload()
    data["agents"][0]["role_profile"]={"initial_goal": "本场目标"}
    with pytest.raises(ValidationError): SceneCreateRequest(**data)
    data["configuration_version"]=2
    assert SceneCreateRequest(**data).agents[0].role_profile.initial_goal == "本场目标"


@pytest.mark.parametrize("field,limit", [("persona",1000),("speech_style",300),("initial_goal",500),
                                        ("private_background",1000),("public_profile",1000)])
def test_profile_codepoints_and_trim(field,limit):
    assert getattr(SceneRoleProfile(**{field:"  "+"😀"*limit+"  "}),field)=="😀"*limit
    with pytest.raises(ValidationError): SceneRoleProfile(**{field:"😀"*(limit+1)})
    with pytest.raises(ValidationError): SceneRoleProfile(**{field:None})


def test_update_is_complete_and_discussion_presence_is_preserved():
    request=AgentProfileUpdateRequest(role_profile={"persona":"认真"})
    assert request.role_profile.initial_goal==""
    assert "discussion_config" not in request.model_fields_set
    assert "discussion_config" in AgentProfileUpdateRequest(role_profile={},discussion_config={}).model_fields_set
    with pytest.raises(ValidationError): SceneRoleProfile(tool_permission="allow")


def test_legacy_explicit_null_profile_is_rejected():
    data = payload()
    data["agents"][0]["role_profile"] = None
    with pytest.raises(ValidationError):
        SceneCreateRequest(**data)
