"""角色模板路由（PRD 3.2）。

错误语义：未找到 404；重名 409；校验失败 422。业务异常由
:mod:`role_theater.api.errors` 统一映射。
"""

from __future__ import annotations

from fastapi import APIRouter, status

from ..contracts import AgentTemplate
from ..contracts.api import (
    IdentityCreateRequest,
    TemplateCopyRequest,
    TemplateCreateRequest,
    TemplateListView,
    TemplateUpdateRequest,
)
from ..domain import TemplateService
from .deps import TemplateServiceDep

router = APIRouter(prefix="/api/templates", tags=["m01-templates"])


@router.post("", response_model=AgentTemplate, status_code=status.HTTP_201_CREATED)
def create_template(payload: TemplateCreateRequest | IdentityCreateRequest, service: TemplateServiceDep) -> AgentTemplate:
    from ..contracts import AgentProfileFields
    return service.create(AgentProfileFields(**payload.model_dump()))


@router.get("", response_model=TemplateListView)
def list_templates(service: TemplateServiceDep) -> TemplateListView:
    return TemplateListView(templates=service.list_all())


@router.get("/{template_id}", response_model=AgentTemplate)
def get_template(template_id: str, service: TemplateServiceDep) -> AgentTemplate:
    return service.get(template_id)


@router.patch("/{template_id}", response_model=AgentTemplate)
def update_template(
    template_id: str,
    payload: TemplateUpdateRequest,
    service: TemplateServiceDep,
) -> AgentTemplate:
    return service.update(
        template_id,
        name=payload.name,
        persona=payload.persona,
        speech_style=payload.speech_style,
        initial_goal=payload.initial_goal,
        private_background=payload.private_background,
        public_profile=payload.public_profile,
    )


@router.post("/{template_id}/copy", response_model=AgentTemplate, status_code=status.HTTP_201_CREATED)
def copy_template(
    template_id: str,
    payload: TemplateCopyRequest,
    service: TemplateServiceDep,
) -> AgentTemplate:
    return service.copy(template_id, new_name=payload.name)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(template_id: str, service: TemplateServiceDep) -> None:
    service.remove(template_id)
