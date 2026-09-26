# role_theater（SceneWeave 后端）

SceneWeave（角色互动沙盒）后端。M00 只提供工程基础与公共契约：健康检查、契约模型、外部端口协议与无密钥测试。

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

## 导出 OpenAPI（前端类型的唯一来源）

```bash
cd backend
uv run python scripts/export_openapi.py
```

输出 `backend/openapi.json`，供前端生成 TypeScript 类型。
