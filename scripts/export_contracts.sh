#!/usr/bin/env bash
#
# 从后端契约重新生成前端产物（PRD 第 8 节：后端是接口唯一来源）。
#
#   1. backend/openapi.json                         —— OpenAPI 文档
#   2. frontend/src/api/generated/contract-summary.json —— 枚举／上限／端口摘要
#   3. frontend/src/api/generated/schema.d.ts       —— TypeScript 类型
#
# 不需要任何模型密钥，也不发起外部调用。
#
# 用法（仓库根目录）:  scripts/export_contracts.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -z "${UV_CACHE_DIR:-}" ]]; then
  export UV_CACHE_DIR="$ROOT_DIR/.cache/uv"
fi

echo "==> 后端：导出 OpenAPI 与契约摘要"
cd "$ROOT_DIR/backend"
if [[ -x .venv/bin/python ]]; then
  .venv/bin/python scripts/export_contracts.py
else
  uv run python scripts/export_contracts.py
fi

echo "==> 前端：由 OpenAPI 生成 TypeScript 类型"
cd "$ROOT_DIR/frontend"
pnpm run gen:api

echo "==> 完成"
