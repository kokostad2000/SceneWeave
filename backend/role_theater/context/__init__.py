"""M02 上下文与可见性：纯函数式构建角色输入。"""

from __future__ import annotations

from .builder import PROMPT_TEMPLATE_ID, ContextBuilder, ContextLimitExceeded
from .models import (
    AgentProfileView,
    RoleContext,
    SceneSnapshot,
    TimelineItem,
    TimelineKind,
    agent_profile_views,
)
from .visibility import cutoff_seq, is_visible_to, newest_external_seq, visible_items

__all__ = [
    "AgentProfileView",
    "ContextBuilder",
    "ContextLimitExceeded",
    "PROMPT_TEMPLATE_ID",
    "RoleContext",
    "SceneSnapshot",
    "TimelineItem",
    "TimelineKind",
    "agent_profile_views",
    "cutoff_seq",
    "is_visible_to",
    "newest_external_seq",
    "visible_items",
]
