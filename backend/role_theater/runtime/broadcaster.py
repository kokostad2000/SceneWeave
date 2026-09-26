"""提交后通知（PRD 第 8 节）。

数据库是事实来源；本模块只做“有新提交了”的**通知**，不承载数据、不是广播队列：
订阅者被唤醒后**重新按 `seq` 从数据库读取**，因此不会因为漏掉一次通知而丢数据，
也不会把多消费者 Queue 误当成广播。
"""

from __future__ import annotations

import asyncio
from collections import defaultdict


class Broadcaster:
    """按场景维护“有新提交”的信号。"""

    def __init__(self) -> None:
        self._events: dict[str, asyncio.Event] = defaultdict(asyncio.Event)

    def notify(self, scene_id: str) -> None:
        """提交落盘后调用；唤醒所有等待者。"""

        self._events[scene_id].set()

    def waiter(self, scene_id: str) -> asyncio.Event:
        """取得（或创建）该场景的等待句柄。"""

        return self._events[scene_id]

    async def wait(self, scene_id: str, timeout: float | None = None) -> bool:
        """等待下一次提交；超时返回 False（供 SSE 心跳使用）。"""

        event = self._events[scene_id]
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except (TimeoutError, asyncio.TimeoutError):
            return False
        finally:
            event.clear()
        return True

    def clear(self, scene_id: str) -> None:
        self._events[scene_id].clear()
