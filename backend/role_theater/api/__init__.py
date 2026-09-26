"""HTTP 路由包。

M00 提供健康检查与契约自检；M01 增加角色模板与场景配置接口；
M04 增加控制命令、事件注入、时间线、角色视角与 SSE；M06 增加只读行为分析。
"""

from __future__ import annotations

from .analysis import router as analysis_router
from .health import router as m00_router
from .runtime import router as runtime_router
from .scenes import router as scenes_router
from .templates import router as templates_router

__all__ = [
    "analysis_router",
    "m00_router",
    "runtime_router",
    "scenes_router",
    "templates_router",
]
