"""可见性判定的唯一实现（PRD 4.1）。

**只有这里**决定一条剧情事实对某个角色是否可见。ContextBuilder（模型输入）、
角色视角接口与 Scheduler（候选判定）都必须调用本模块，从而不可能出现
“界面看到一套、调用器用另一套”的情况（PRD 7.2）。

本模块是纯函数：不读写数据库、不依赖时间、不导入 FastAPI。
"""

from __future__ import annotations

from ..contracts import EventVisibility
from .models import SceneSnapshot, TimelineItem, TimelineKind


def is_visible_to(item: TimelineItem, agent_id: str) -> bool:
    """一条剧情事实对指定角色是否可见。"""

    if item.kind is TimelineKind.MESSAGE:
        # 公开发言对全体可见；“回复谁”“希望谁接话”不改变公开范围（PRD 4.2）。
        return True
    # 事件：ALL 全体可见，TARGETED 仅指定角色可见（PRD 4.3）。
    return item.visibility is EventVisibility.ALL or item.target_agent_id == agent_id


def visible_items(scene: SceneSnapshot, agent_id: str) -> tuple[TimelineItem, ...]:
    """按 ``seq`` 升序返回该角色可见的全部剧情事实。"""

    return tuple(
        item for item in sorted(scene.timeline, key=lambda entry: entry.seq)
        if is_visible_to(item, agent_id)
    )


def cutoff_seq(scene: SceneSnapshot, agent_id: str) -> int:
    """该角色可见的最大 ``seq``（无则 0）：行动依据的输入快照截止序号。"""

    return max((item.seq for item in scene.timeline if is_visible_to(item, agent_id)), default=0)


def newest_external_seq(scene: SceneSnapshot, agent_id: str) -> int:
    """该角色可见、且**不是自己产出**的最新序号。

    自己说的话进入自己的历史，但不能仅凭自己的发言再次唤醒自己（PRD 5.1）；
    事件由操作者注入，因此对可获得该事件的角色都算外部信息。
    """

    return max(
        (
            item.seq
            for item in scene.timeline
            if is_visible_to(item, agent_id) and item.author_agent_id != agent_id
        ),
        default=0,
    )


__all__ = ["cutoff_seq", "is_visible_to", "newest_external_seq", "visible_items"]
