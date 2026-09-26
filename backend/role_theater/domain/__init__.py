"""领域层：角色模板与场景的业务规则。

领域层不依赖 FastAPI；HTTP 映射在 ``role_theater.api`` 中完成。
"""

from __future__ import annotations

from .errors import (
    AgentCountError,
    ConflictError,
    DomainError,
    DomainNotFoundError,
    DuplicateNameError,
    SceneLockedError,
    UnknownTemplateError,
)
from .scenes import AgentSpec, SceneDetail, SceneService, SceneSummary
from .templates import TemplateService

__all__ = [
    "AgentCountError",
    "AgentSpec",
    "ConflictError",
    "DomainError",
    "DomainNotFoundError",
    "DuplicateNameError",
    "SceneDetail",
    "SceneLockedError",
    "SceneService",
    "SceneSummary",
    "TemplateService",
    "UnknownTemplateError",
]
