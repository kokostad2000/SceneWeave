"""FC-01/02: independent scene policy and both Unicode length boundaries."""
import pytest
from pydantic import ValidationError
from role_theater.contracts import ActionDraft, SceneCreateRequest, ModelParams, ReferenceScope


def test_new_scene_defaults_to_free_chat_independent_of_profile_version():
    request = SceneCreateRequest(title="测试", agents=[{"template_id": "a"}, {"template_id": "b"}])
    assert request.chat_policy_version == 2
    assert request.configuration_version == 1
    assert ModelParams().max_output_tokens == 4096
    assert ModelParams(max_output_tokens=1024).max_output_tokens == 1024


@pytest.mark.parametrize("bad", [True, False, "2", 2.0, 0, 3, None])
def test_policy_rejects_non_integer_and_unknown_versions(bad):
    with pytest.raises(ValidationError):
        SceneCreateRequest(title="测试", agents=[{"template_id": "a"}, {"template_id": "b"}], chat_policy_version=bad)


@pytest.mark.parametrize("action", ["SPEAK", "PRIVATE"])
@pytest.mark.parametrize("version,limit", [(1, 200), (2, 1000)])
@pytest.mark.parametrize("char", ["字", "😀"])
def test_policy_codepoint_boundaries_after_trimming(action, version, limit, char):
    fields = {"action": action, "text": " \n" + char * limit + "\t "}
    if action == "PRIVATE":
        fields["recipient_id"] = "b"
    context = {"chat_policy_version": version}
    assert len(ActionDraft.model_validate(fields, context=context).text) == limit
    with pytest.raises(ValidationError):
        ActionDraft.model_validate({**fields, "text": char * (limit + 1)}, context=context)
    assert ReferenceScope(actor_id="a", chat_policy_version=version).chat_policy_version == version
