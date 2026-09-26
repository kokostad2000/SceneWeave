"""SceneWeave（角色互动沙盒）后端应用包。

包名固定为 ``role_theater``：显式避开外部分析仓库的顶层 ``src`` 命名
（PRD 6.2）。产品显示名称是 SceneWeave。
"""

from __future__ import annotations

from .contracts import APP_NAME, APP_VERSION, CONTRACT_VERSION

__all__ = ["APP_NAME", "APP_VERSION", "CONTRACT_VERSION"]
