# role_theater（SceneWeave 后端）

SceneWeave（角色互动沙盒）后端：M00 工程基础与公共契约（健康检查、契约模型、外部端口协议、无密钥测试），
M01 模板／场景／存储，M02 可见性与调度，M03 模型适配，M04 运行与事件（HTTP＋SSE），M06 只读行为分析。

- 运行环境：Python 3.12
- 依赖管理：`uv`（`pyproject.toml` + `uv.lock`）
- 接口唯一来源：`role_theater/contracts/`

## 安装

```bash
cd backend
uv sync --dev
```

`uv sync` 不需要任何模型密钥；M00 不安装任何外部分析包。

## 启动（仅监听本机）

```bash
cd backend
uv run uvicorn role_theater.main:app --host 127.0.0.1 --port 8000
```

## 测试

```bash
cd backend
uv run pytest
```

测试默认使用 Mock 端口，不发起真实外部请求，不需要密钥。

## 导出契约产物（前端类型的唯一来源）

```bash
cd backend
uv run python scripts/export_contracts.py   # 生成 openapi.json 与契约摘要
```

输出 `backend/openapi.json` 与前端 `src/api/generated/` 下的产物；仓库根目录的
`scripts/export_contracts.sh` 会再跑一次前端 TypeScript 生成，一次重建全部产物。
后端测试 `tests/test_contract_export.py` 会检测产物漂移。
