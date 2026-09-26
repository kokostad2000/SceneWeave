"""领域错误与 HTTP 语义映射（PRD 3.2、5.3）。

- :class:`DomainNotFoundError` → 404
- :class:`ConflictError` 及其子类 → 409
- :class:`InvalidInputError` → 422

契约层（Pydantic）已拦截大部分格式与长度问题；领域层只负责业务规则
（数量、唯一性、锁定、引用存在性）。
"""

from __future__ import annotations


class DomainError(Exception):
    """领域错误基类。``code`` 会出现在 API 错误体中，便于前端区分。"""

    code = "domain_error"
    http_status = 400


class DomainNotFoundError(DomainError):
    code = "not_found"
    http_status = 404


class ConflictError(DomainError):
    code = "conflict"
    http_status = 409


class InvalidInputError(DomainError):
    code = "invalid_input"
    http_status = 422


class DuplicateNameError(ConflictError):
    """同一场景内角色重名，或模板重名（tasks/M01.md §3.6 I1）。"""

    code = "duplicate_name"


class AgentCountError(ConflictError):
    """本场角色数量必须在 2～8 之间（PRD 1.2）。"""

    code = "agent_count_out_of_range"


class SceneLockedError(ConflictError):
    """场景已锁定：不能删角色，也不能改写私有背景（PRD 3.2）。"""

    code = "scene_locked"


class UnknownTemplateError(ConflictError):
    """引用了不存在的角色模板。"""

    code = "unknown_template"
