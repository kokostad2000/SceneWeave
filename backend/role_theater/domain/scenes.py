"""场景与本场角色服务（PRD 1.2、3.1、3.2、5.3）。

关键规则：

- 本场角色数量 2～8，由**数据**驱动，代码中不写死具体人数（PRD 1.2）；
- 创建本场角色时保存模板快照 + 来源模板 ID + 新的 ``agent_id``（PRD 3.2）；
- 同一场景内名称不可重复；锁定后不得新增／重命名／移除角色（PRD 3.2）；
- 模板后续改动或删除都不影响已创建场景（快照隔离，PRD 3.2）。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from ..contracts import (
    MAX_AGENTS_PER_SCENE,
    MIN_AGENTS_PER_SCENE,
    AgentProfileFields,
    AgentSnapshot,
    Budget,
    RunState,
    Scene,
    SceneAgent,
    validate_agent_count,
    SceneMode,
    SimulationConfig,
    DiscussionConfig,
    DiscussionParticipantConfig,
    SceneRoleProfile,
)
from ..presets import DEFAULT_PRESET_KEY, PresetScene, get_preset
from ..storage import SceneRepository
from .errors import (
    AgentCountError,
    DomainNotFoundError,
    DuplicateNameError,
    SceneLockedError,
    UnknownTemplateError,
    InvalidInputError,
)
from .templates import TemplateService, utcnow


def _default_scene_id() -> str:
    return f"scn_{uuid4().hex}"


def _default_agent_id() -> str:
    return f"agt_{uuid4().hex}"


@dataclass(frozen=True)
class AgentSpec:
    """创建场景时对本场角色的要求。"""

    template_id: str
    name: str | None = None
    discussion_config: DiscussionParticipantConfig | None = None
    role_profile: SceneRoleProfile | None = None


@dataclass(frozen=True)
class SceneSummary:
    """场景列表项。"""

    scene: Scene
    agent_count: int


@dataclass(frozen=True)
class SceneDetail:
    """场景详情：场景 + 本场角色集合。"""

    scene: Scene
    agents: tuple[SceneAgent, ...]

    @property
    def locked(self) -> bool:
        """预算与人物设定是否已锁定（PRD 3.2、5.3）。"""

        return self.scene.budget.locked_at is not None


class SceneService:
    """场景业务规则。"""

    def __init__(
        self,
        scenes: SceneRepository,
        templates: TemplateService,
        *,
        clock: Callable[[], datetime] = utcnow,
        scene_id_factory: Callable[[], str] = _default_scene_id,
        agent_id_factory: Callable[[], str] = _default_agent_id,
    ) -> None:
        self._scenes = scenes
        self._templates = templates
        self._clock = clock
        self._scene_id_factory = scene_id_factory
        self._agent_id_factory = agent_id_factory

    # --- 查询 ---

    def list_summaries(self, mode: SceneMode | None = None) -> list[SceneSummary]:
        counts = self._scenes.agent_counts()
        return [
            SceneSummary(scene=scene, agent_count=counts.get(scene.scene_id, 0))
            for scene in self._scenes.list_scenes(mode)
        ]

    def get_detail(self, scene_id: str) -> SceneDetail:
        scene = self._require_scene(scene_id)
        agents = tuple(self._scenes.list_agents(scene_id))
        return SceneDetail(scene=scene, agents=agents)

    # --- 创建 ---

    def create(
        self,
        *,
        title: str,
        background: str,
        agent_specs: Sequence[AgentSpec],
        max_role_requests: int | None = None,
        max_analysis_requests: int | None = None,
        preset_key: str | None = None,
        mode: SceneMode = SceneMode.SIMULATION,
        mode_config: SimulationConfig | DiscussionConfig | None = None,
        configuration_version: int = 1,
        chat_policy_version: int = 2,
    ) -> SceneDetail:
        # 数量由契约常量驱动：三人增至五人不改代码（PRD 1.2、M01 通过条件）。
        validate_agent_count(len(agent_specs))

        budget_defaults = Budget()
        budget = Budget(
            max_role_requests=(
                max_role_requests if max_role_requests is not None else budget_defaults.max_role_requests
            ),
            max_analysis_requests=(
                max_analysis_requests
                if max_analysis_requests is not None
                else budget_defaults.max_analysis_requests
            ),
        )

        now = self._clock()
        scene = Scene(
            scene_id=self._scene_id_factory(),
            title=title,
            background=background,
            mode=mode,
            mode_config=mode_config,
            configuration_version=configuration_version,
            chat_policy_version=chat_policy_version,
            status=RunState.READY,
            budget=budget,
            created_at=now,
        )
        agents = self._build_agents(scene, agent_specs, now)
        self._scenes.insert_scene_with_agents(scene, agents, preset_key=preset_key)
        return SceneDetail(scene=scene, agents=tuple(agents))

    def create_preset(self, preset_key: str = DEFAULT_PRESET_KEY, *, configuration_version: int = 1, chat_policy_version: int = 2) -> SceneDetail:
        """用预置场景创建会话；缺失的预置模板会被补齐。"""

        try:
            preset: PresetScene = get_preset(preset_key)
        except KeyError as exc:
            raise DomainNotFoundError(f"未知的预置场景：{preset_key}") from exc

        templates_by_name = self._templates.ensure_preset_templates(preset.key, identity_only=configuration_version == 2)
        specs = [
            AgentSpec(template_id=templates_by_name[agent.name].template_id, name=agent.name,
                      role_profile=SceneRoleProfile(**agent.to_profile().model_dump(exclude={"name"})) if configuration_version == 2 else None)
            for agent in preset.agents
        ]
        return self.create(
            title=preset.title,
            background=preset.background,
            agent_specs=specs,
            preset_key=preset.key,
            configuration_version=configuration_version,
            chat_policy_version=chat_policy_version,
        )

    # --- 本场角色维护 ---

    def add_agent(
        self,
        scene_id: str,
        *,
        template_id: str,
        name: str | None = None,
        discussion_config: DiscussionParticipantConfig | None = None,
        role_profile: SceneRoleProfile | None = None,
        role_profile_provided: bool = False,
    ) -> SceneAgent:
        scene = self._require_scene(scene_id)
        self._require_unlocked(scene)
        if scene.configuration_version == 1 and role_profile_provided:
            raise InvalidInputError("本场 role_profile 需要 configuration_version=2")

        count = self._scenes.count_agents(scene_id)
        if count >= MAX_AGENTS_PER_SCENE:
            raise AgentCountError(
                f"本场角色最多 {MAX_AGENTS_PER_SCENE} 名，当前 {count} 名"
            )

        try:
            template = self._templates.get(template_id)
        except DomainNotFoundError as exc:
            raise UnknownTemplateError(f"角色模板不存在：{template_id}") from exc

        resolved_name = (name if name is not None else template.name).strip()
        self._require_name_free(scene_id, resolved_name)

        now = self._clock()
        agent = SceneAgent(
            agent_id=self._agent_id_factory(),
            scene_id=scene_id,
            name=resolved_name,
            order_index=self._scenes.next_order_index(scene_id),
            snapshot=self._snapshot(template, now, scene.configuration_version, role_profile),
            discussion_config=self._participant_config(scene, discussion_config),
            created_at=now,
        )
        self._scenes.insert_agent(agent)
        return agent

    def update_agent_profile(self, scene_id: str, agent_id: str, role_profile: SceneRoleProfile,
                             *, discussion_config: DiscussionParticipantConfig | None = None,
                             replace_discussion: bool = False) -> SceneAgent:
        scene = self._require_scene(scene_id)
        self._require_unlocked(scene)
        if scene.configuration_version != 2:
            raise InvalidInputError("旧版场景保留原快照；请新建场景配置")
        if scene.status is not RunState.READY:
            raise SceneLockedError("场景不在配置阶段，不能修改本场设定")
        current = self._require_agent(scene_id, agent_id)
        profile = SceneRoleProfile.model_validate(role_profile)
        discussion = self._participant_config(scene, discussion_config) if replace_discussion else current.discussion_config
        snapshot = AgentSnapshot(source_template_id=current.snapshot.source_template_id,
                                 name=current.snapshot.name, captured_at=self._clock(), **profile.model_dump())
        updated = current.model_copy(update={"snapshot":snapshot,"discussion_config":discussion})
        self._scenes.update_agent_profile(updated)
        return updated

    def rename_agent(self, scene_id: str, agent_id: str, new_name: str) -> SceneAgent:
        scene = self._require_scene(scene_id)
        self._require_unlocked(scene)
        agent = self._require_agent(scene_id, agent_id)

        resolved_name = new_name.strip()
        if resolved_name != agent.name:
            self._require_name_free(scene_id, resolved_name)
            self._scenes.rename_agent(scene_id, agent_id, resolved_name)

        renamed = self._scenes.get_agent(scene_id, agent_id)
        if renamed is None:  # pragma: no cover - 刚更新过的行不会消失
            raise DomainNotFoundError(f"本场角色不存在：{agent_id}")
        return renamed

    def remove_agent(self, scene_id: str, agent_id: str) -> None:
        scene = self._require_scene(scene_id)
        self._require_unlocked(scene)
        self._require_agent(scene_id, agent_id)

        count = self._scenes.count_agents(scene_id)
        if count <= MIN_AGENTS_PER_SCENE:
            raise AgentCountError(
                f"本场角色不能少于 {MIN_AGENTS_PER_SCENE} 名，当前 {count} 名"
            )
        self._scenes.delete_agent(scene_id, agent_id)

    # --- 锁定 ---

    def lock(self, scene_id: str) -> Scene:
        """锁定预算与人物设定；由 M04 在首次角色请求开始时调用（PRD 3.2）。"""

        self._require_scene(scene_id)
        if self._scenes.lock_scene(scene_id, self._clock()):
            return self._require_scene(scene_id)
        # 已经锁定：保持首次锁定时间不变（幂等）。
        return self._require_scene(scene_id)

    # --- 内部 ---

    def _build_agents(
        self, scene: Scene, specs: Sequence[AgentSpec], captured_at: datetime
    ) -> list[SceneAgent]:
        agents: list[SceneAgent] = []
        seen_names: set[str] = set()

        for index, spec in enumerate(specs):
            try:
                template = self._templates.get(spec.template_id)
            except DomainNotFoundError as exc:
                raise UnknownTemplateError(
                    f"角色模板不存在：{spec.template_id}"
                ) from exc

            resolved_name = (spec.name if spec.name is not None else template.name).strip()
            if resolved_name in seen_names:
                raise DuplicateNameError(f"同一场景内角色名称不可重复：{resolved_name}")
            seen_names.add(resolved_name)

            agents.append(
                SceneAgent(
                    agent_id=self._agent_id_factory(),
                    scene_id=scene.scene_id,
                    name=resolved_name,
                    order_index=index,
                    snapshot=self._snapshot(template, captured_at, scene.configuration_version, spec.role_profile),
                    discussion_config=self._participant_config(scene, spec.discussion_config),
                    created_at=captured_at,
                )
            )
        return agents

    @staticmethod
    def _participant_config(scene: Scene, config):
        if scene.mode is SceneMode.SIMULATION:
            if config is not None:
                raise InvalidInputError("simulation 不接受讨论参与者配置")
            return None
        return config or DiscussionParticipantConfig()

    @staticmethod
    def _snapshot(template, captured_at: datetime, configuration_version: int = 1,
                  role_profile: SceneRoleProfile | None = None) -> AgentSnapshot:
        if configuration_version == 1 and role_profile is not None:
            raise InvalidInputError("本场 role_profile 需要 configuration_version=2")
        profile = (role_profile or SceneRoleProfile()) if configuration_version == 2 else SceneRoleProfile(
            **template.model_dump(include=set(SceneRoleProfile.model_fields)))
        return AgentSnapshot(source_template_id=template.template_id, captured_at=captured_at,
                             name=template.name, **profile.model_dump())

    def _require_scene(self, scene_id: str) -> Scene:
        scene = self._scenes.get_scene(scene_id)
        if scene is None:
            raise DomainNotFoundError(f"场景不存在：{scene_id}")
        return scene

    def _require_agent(self, scene_id: str, agent_id: str) -> SceneAgent:
        agent = self._scenes.get_agent(scene_id, agent_id)
        if agent is None:
            raise DomainNotFoundError(f"本场角色不存在：{agent_id}")
        return agent

    @staticmethod
    def _require_unlocked(scene: Scene) -> None:
        if scene.budget.locked_at is not None:
            raise SceneLockedError(
                "本场背景与人物设定已锁定，不能再新增、重命名或移除角色"
                "（变化应通过事件表达）"
            )

    def _require_name_free(self, scene_id: str, name: str) -> None:
        if self._scenes.find_agent_by_name(scene_id, name) is not None:
            raise DuplicateNameError(f"同一场景内角色名称不可重复：{name}")
