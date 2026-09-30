"""角色模板服务（PRD 3.2、3.3）。

职责：模板的创建、编辑、复制、列表与移除，以及预置模板的按需补齐。
长度与字段校验由契约层（:class:`AgentProfileFields`）完成；本层负责唯一性、
引用与副本命名等业务规则。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from ..contracts import MAX_AGENT_NAME_CODEPOINTS, AgentProfileFields, AgentTemplate
from ..presets import PresetScene, get_preset
from ..storage import TemplateRepository
from .errors import DomainNotFoundError, DuplicateNameError

COPY_SUFFIXES = 1000


def utcnow() -> datetime:
    """统一的当前时间（UTC，带时区）。"""

    return datetime.now(UTC)


def _default_template_id() -> str:
    return f"tpl_{uuid4().hex}"


class TemplateService:
    """模板业务规则。"""

    def __init__(
        self,
        repo: TemplateRepository,
        *,
        clock: Callable[[], datetime] = utcnow,
        id_factory: Callable[[], str] = _default_template_id,
    ) -> None:
        self._repo = repo
        self._clock = clock
        self._id_factory = id_factory

    # --- 查询 ---

    def list_all(self) -> list[AgentTemplate]:
        return self._repo.list_all()

    def get(self, template_id: str) -> AgentTemplate:
        template = self._repo.get(template_id)
        if template is None:
            raise DomainNotFoundError(f"角色模板不存在：{template_id}")
        return template

    def require_unique_name(self, name: str, *, exclude_template_id: str | None = None) -> None:
        existing = self._repo.find_by_name(name)
        if existing is not None and existing.template_id != exclude_template_id:
            raise DuplicateNameError(f"角色模板名称已存在：{name}")

    # --- 写入 ---

    def create(self, profile: AgentProfileFields) -> AgentTemplate:
        self.require_unique_name(profile.name)
        now = self._clock()
        template = AgentTemplate(
            template_id=self._id_factory(),
            created_at=now,
            updated_at=now,
            **profile.model_dump(),
        )
        self._repo.insert(template)
        return template

    def update(
        self,
        template_id: str,
        *,
        name: str | None = None,
        persona: str | None = None,
        speech_style: str | None = None,
        initial_goal: str | None = None,
        private_background: str | None = None,
        public_profile: str | None = None,
    ) -> AgentTemplate:
        current = self.get(template_id)

        merged = AgentProfileFields(
            public_profile=public_profile if public_profile is not None else current.public_profile,
            name=name if name is not None else current.name,
            persona=persona if persona is not None else current.persona,
            speech_style=speech_style if speech_style is not None else current.speech_style,
            initial_goal=initial_goal if initial_goal is not None else current.initial_goal,
            private_background=(
                private_background
                if private_background is not None
                else current.private_background
            ),
        )
        self.require_unique_name(merged.name, exclude_template_id=template_id)

        updated = AgentTemplate(
            template_id=template_id,
            created_at=current.created_at,
            updated_at=self._clock(),
            **merged.model_dump(),
        )
        self._repo.update(updated)
        return updated

    def copy(self, template_id: str, *, new_name: str | None = None) -> AgentTemplate:
        """复制模板；未给出名称时自动取第一个可用的不重复名称。"""

        source = self.get(template_id)
        resolved_name = new_name if new_name is not None else self._next_copy_name(source.name)
        if new_name is not None:
            self.require_unique_name(new_name)

        profile = AgentProfileFields(
            public_profile=source.public_profile,
            name=resolved_name,
            persona=source.persona,
            speech_style=source.speech_style,
            initial_goal=source.initial_goal,
            private_background=source.private_background,
        )
        return self.create(profile)

    def remove(self, template_id: str) -> None:
        self.get(template_id)
        self._repo.delete(template_id)

    # --- 预置模板 ---

    def ensure_preset_templates(self, preset_key: str, *, identity_only: bool = False) -> dict[str, AgentTemplate]:
        """按需补齐**指定预置场景**的模板，返回 名称 → 模板 的映射。

        预置模板被移除后仍可通过预置场景重新获得，保证预置流程可重复使用；
        只补齐该场景需要的角色，避免创建 A 场景时顺带写入 B 场景的模板。
        """

        preset: PresetScene = get_preset(preset_key)
        resolved: dict[str, AgentTemplate] = {}
        for preset in preset.agents:
            existing = self._repo.find_by_name(preset.name)
            if existing is None:
                now = self._clock()
                existing = AgentTemplate(
                    template_id=self._id_factory(),
                    created_at=now,
                    updated_at=now,
                    **(AgentProfileFields(name=preset.name) if identity_only else preset.to_profile()).model_dump(),
                )
                self._repo.insert(existing, is_preset=True)
            resolved[preset.name] = existing
        return resolved

    # --- 内部 ---

    def _next_copy_name(self, base: str) -> str:
        """生成第一个可用且不超过长度上限的副本名称。"""

        for index in range(1, COPY_SUFFIXES + 1):
            suffix = "（副本）" if index == 1 else f"（副本{index}）"
            allowed = MAX_AGENT_NAME_CODEPOINTS - len(suffix)
            if allowed <= 0:  # pragma: no cover - 名称上限远大于后缀长度
                raise DuplicateNameError("名称长度上限不足以生成副本名称")
            candidate = f"{base[:allowed].strip()}{suffix}"
            if self._repo.find_by_name(candidate) is None:
                return candidate
        raise DuplicateNameError(  # pragma: no cover - 需要上千个同名副本才会触发
            f"无法为 {base} 生成不重复的副本名称"
        )
