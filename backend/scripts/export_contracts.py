"""导出契约产物（后端是接口唯一来源，PRD 第 8 节）。

生成两个可复现的前端消费产物：

1. ``backend/openapi.json`` —— 完整 OpenAPI 文档，供 ``openapi-typescript`` 生成类型；
2. ``frontend/src/api/generated/contract-summary.json`` —— 契约自检摘要（枚举取值、
   长度上限、预算、运行参数、端口），供前端在运行时读取，避免手写重复常量。

本脚本**不需要任何模型密钥**，也不发起任何外部调用。

用法（在 ``backend/`` 目录下）::

    uv run python scripts/export_contracts.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from role_theater.config import Settings  # noqa: E402
from role_theater.contracts import build_contract_summary  # noqa: E402
from role_theater.main import create_app  # noqa: E402

OPENAPI_PATH = BACKEND_DIR / "openapi.json"
CONTRACT_SUMMARY_PATH = (
    REPO_ROOT / "frontend" / "src" / "api" / "generated" / "contract-summary.json"
)


def _dump(payload: object) -> str:
    # 稳定排序，保证重复执行产生完全相同的字节。
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_openapi() -> str:
    """渲染 OpenAPI JSON 文本（纯函数，可复现）。"""

    return _dump(create_app(Settings()).openapi())


def render_contract_summary() -> str:
    """渲染契约摘要 JSON 文本（纯函数，可复现）。"""

    return _dump(build_contract_summary().model_dump(mode="json"))


def write_artifacts() -> list[Path]:
    """写出全部契约产物，返回写出的路径列表。"""

    CONTRACT_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    OPENAPI_PATH.write_text(render_openapi(), encoding="utf-8")
    CONTRACT_SUMMARY_PATH.write_text(render_contract_summary(), encoding="utf-8")
    return [OPENAPI_PATH, CONTRACT_SUMMARY_PATH]


def main() -> int:
    for path in write_artifacts():
        print(f"wrote {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
