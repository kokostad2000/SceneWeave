"""pytest 根配置。

把 ``backend/`` 加入 ``sys.path``，使测试可以导入开发脚本
（``scripts.export_contracts``），从而对导出的契约产物做漂移检测。
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
