"""M02 纯数据模型：场景快照、时间线条目与角色上下文。

这些类型是 ContextBuilder 与 Scheduler 的**唯一输入／输出**：

- 它们是冻结数据类，只承载剧情事实；
- **没有**任何字段用来承载分析报告、错误、使用量、运行状态或 SSE 心跳
  （PRD 4.1：这些不属于剧情，不得进入角色上下文或唤醒角色）——因此“误把
  非剧情内容喂给角色”在类型层面就不可能发生。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from ..contracts import AgentSnapshot, Event, EventVisibility, Message


class TimelineKind(StrEnum):
    """时间线条目种类：只允许公开发言与已生效事件。"""

    MESSAGE = "message"
    EVENT = "event"


@dataclass(frozen=True, slots=True)
class TimelineItem:
    """一条剧情事实。

    操作者时间线与角色视角都从**同一组** TimelineItem 派生，可见性由
    :mod:`role_theater.context.visibility` 统一判定。
    """

    kind: TimelineKind
    seq: int
    body: str
    #: 发言作者；事件由操作者注入，因此为 None。
    author_agent_id: str | None = None
    author_name: str | None = None
    #: 仅事件使用。
    visibility: EventVisibility | None = None
    target_agent_id: str | None = None
    #: 仅发言使用：服务端分配的消息 ID。模型要能引用它，必须先在提示词里看到它
    #: （PRD 4.2 的 ``reply_to_message_id``），否则引用永远无法落在合法范围内。
    message_id: str | None = None
    #: 仅发言使用。
    reply_to_message_id: str | None = None
    requested_speaker_id: str | None = None

    @staticmethod
    def from_message(message: Message, *, author_name: str | None = None) -> TimelineItem:
        return TimelineItem(
            kind=TimelineKind.MESSAGE,
            seq=message.seq,
            body=message.text,
            author_agent_id=message.actor_id,
            author_name=author_name,
            message_id=message.message_id,
            reply_to_message_id=message.reply_to_message_id,
            requested_speaker_id=message.requested_speaker_id,
        )

    @staticmethod
    def from_event(event: Event, *, author_name: str | None = None) -> TimelineItem:
        return TimelineItem(
            kind=TimelineKind.EVENT,
            seq=event.seq,
            body=event.body,
            author_agent_id=None,
            author_name=author_name,
            visibility=event.visibility,
            target_agent_id=event.target_agent_id,
        )


@dataclass(frozen=True, slots=True)
class AgentProfileView:
    """本场角色 + 模板快照（只读视图）。"""

    agent_id: str
    name: str
    order_index: int
    snapshot: AgentSnapshot


@dataclass(frozen=True, slots=True)
class SceneSnapshot:
    """构建上下文与调度所需的全部剧情事实（纯数据，无 I/O）。"""

    scene_id: str
    background: str
    agents: tuple[AgentProfileView, ...]
    timeline: tuple[TimelineItem, ...] = ()

    def agent(self, agent_id: str) -> AgentProfileView:
        for candidate in self.agents:
            if candidate.agent_id == agent_id:
                return candidate
        raise KeyError(agent_id)

    @property
    def ordered_agents(self) -> tuple[AgentProfileView, ...]:
        """固定角色顺序（PRD 5.1 的平局判定依据）。"""

        return tuple(sorted(self.agents, key=lambda item: item.order_index))

    @property
    def public_roster(self) -> tuple[str, ...]:
        """公开名册：只有名称，不含任何私有内容（PRD 4.1）。"""

        return tuple(item.name for item in self.ordered_agents)

    @property
    def last_seq(self) -> int:
        return max((item.seq for item in self.timeline), default=0)


@dataclass(frozen=True, slots=True)
class RoleContext:
    """某个角色的**实际模型输入**。

    该结构被调用器与角色视角共用，保证两者一致（PRD 7.2）。
    """

    actor_id: str
    actor_name: str
    common_background: str
    public_roster: tuple[str, ...]
    #: 仅本人完整资料（PRD 4.1）。
    private_persona: str
    private_speech_style: str
    private_initial_goal: str
    private_background: str
    visible_items: tuple[TimelineItem, ...]
    cutoff_seq: int
    prompt_template_id: str
    prompt: str = field(repr=False)


def agent_profile_views(agents) -> tuple[AgentProfileView, ...]:
    """由 M01 的本场角色（契约模型）构造只读视图。"""

    return tuple(
        AgentProfileView(
            agent_id=agent.agent_id,
            name=agent.name,
            order_index=agent.order_index,
            snapshot=agent.snapshot,
        )
        for agent in agents
    )


__all__ = [
    "AgentProfileView",
    "RoleContext",
    "SceneSnapshot",
    "TimelineItem",
    "TimelineKind",
    "agent_profile_views",
]
