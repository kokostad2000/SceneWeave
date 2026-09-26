# SceneWeave（角色互动沙盒）

多个具有不同人设、当下目标和独立信息的虚构角色，在共同文字情境下交流；操作者可观察、暂停、插入事件，并按需调用独立的行为分析。

- 需求来源：[PRD.md](PRD.md)
- 开发规则：[AGENTS.md](AGENTS.md)
- 架构说明：[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **验收矩阵**：[docs/ACCEPTANCE.md](docs/ACCEPTANCE.md)
- **发布资料 / 已知限制**：[docs/RELEASE.md](docs/RELEASE.md)
- 开发状态：[state/STATUS.md](state/STATUS.md)
- 各模块任务书与报告：[tasks/](tasks/)、[state/reports/](state/reports/)

## 当前进度

**M00～M07 全部已验收。** 工程与契约、角色与场景、可见性与调度、模型适配、运行与事件、
操作界面、行为分析、集成与交付均已实现，并有确定性 Mock 证据。

**交付结论：未达到「可试用」**——服务未部署、外部分析仓库未安装、聊天质量与界面的人工观察未做。
真实模型**已接通并跑过真实会话**（2026-09-26／27 两场 `deepseek-flash`；第二场 22 次调用全部成功，22 条消息中 21 条带
`reply_to_message_id`）。期间在真实调用中发现的引用缺陷已修复并回归，见
[state/reports/FIX-reply-reference.md](state/reports/FIX-reply-reference.md)；
每场角色请求上限默认值经人工裁决由 24 上调为 200，见 [state/reports/CHANGE-role-request-limit.md](state/reports/CHANGE-role-request-limit.md)。
详见 [docs/RELEASE.md](docs/RELEASE.md) §7 与 [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md) §8。

## 目录

```
backend/    FastAPI 后端，Python 包名 role_theater
  role_theater/contracts/   公共契约（接口唯一来源）
  role_theater/storage/     SQLite 连接、迁移与仓储
  role_theater/domain/      领域服务（模板、场景）
  role_theater/api/         HTTP 路由
frontend/   React + TypeScript + Vite 前端
docs/       架构文档
tasks/      模块任务书（需求／目标／规范）
state/      开发状态与模块报告
scripts/    契约产物导出脚本
```

## 环境要求

| 组件 | 版本 |
|---|---|
| Python | 3.12 |
| uv | 0.12+ |
| Node.js | 24 |
| pnpm | 11 |

后端与前端都不需要模型密钥即可安装、启动与测试。

## 配置凭证（可选）

不需要密钥即可安装、启动与测试（未配置时使用确定性 Mock）。要用真实 DeepSeek：

```bash
cp .env.example .env      # 填入 SCENEWEAVE_MODEL_API_KEY=...
curl -sS http://127.0.0.1:8000/api/health | python3 -m json.tool   # 应显示 model_credential_source: dotenv
```

`.env` 已被 `.gitignore` 忽略，不会进入仓库、日志或 API 响应；环境变量优先于 `.env`。
只保留一处 `.env`（推荐仓库根）：若 `backend/.env` 也存在，它会**覆盖**仓库根那份（已实测）。

## 安装

```bash
# 后端
cd backend && uv sync --dev

# 前端
cd frontend && pnpm install
```

## 启动（仅监听本机）

```bash
# 终端 1：后端
cd backend && uv run uvicorn role_theater.main:app --host 127.0.0.1 --port 8000

# 终端 2：前端（默认把 /api 代理到 127.0.0.1:8000）
cd frontend && pnpm run dev
```

打开 <http://127.0.0.1:5173>。

## 测试

```bash
# 后端（423 项）
cd backend && uv run pytest

# 前端（49 项）
cd frontend && pnpm run test
cd frontend && pnpm run typecheck && pnpm run build

# 证明不发起真实外部调用：阻断出站网络后仍全部通过
cd backend && PYTHONPATH=/tmp uv run pytest -p no_net_plugin
```

## 快速核对 M01（配置期接口）

```bash
# 列出三个预置场景
curl -sS http://127.0.0.1:8000/api/scenes/presets | python3 -m json.tool

# 用某个预置场景创建（roommates / convenience_store / campsite；不调用模型）
curl -sS -X POST http://127.0.0.1:8000/api/scenes/preset \
     -H 'Content-Type: application/json' -d '{"preset_key": "campsite"}' | python3 -m json.tool

# 查看场景列表与角色数
curl -sS http://127.0.0.1:8000/api/scenes | python3 -m json.tool
```

SQLite 文件默认在 `backend/sceneweave.db`；启动时自动执行迁移（幂等），可用
`SCENEWEAVE_DATABASE_URL` 指定其他路径。备份与恢复见 [docs/RELEASE.md](docs/RELEASE.md) §5。

## 行为分析（默认关闭）

分析能力默认关闭，且**不要求**外部分析仓库已安装；开启后若外部包不可用，会明确报告原因
而不是崩溃。真实模型冒烟需要显式开关与密钥：

```bash
cd backend && SCENEWEAVE_MODEL_API_KEY=... uv run python scripts/live_smoke.py --live --confirm-spend
```

## 契约产物

后端契约是接口唯一来源。修改 `backend/role_theater/contracts/` 后必须重新导出：

```bash
scripts/export_contracts.sh
```

该脚本重新生成 `backend/openapi.json`、`frontend/src/api/generated/contract-summary.json`
与 `frontend/src/api/generated/schema.d.ts`；后端测试会检测产物漂移。

## 配置

全部配置通过环境变量提供，前缀 `SCENEWEAVE_`（例如 `SCENEWEAVE_MODEL_API_KEY`、
`SCENEWEAVE_DATABASE_URL`）。密钥**只**从环境变量读取，不写入代码或记录。
未配置密钥时健康检查仍返回 200，仅 `model_configured=false`。

本版本的真实模型调用需要显式 `live` 开关与密钥（见上）；行为分析的外部依赖仍未安装，分析能力默认关闭。
每场预算默认「角色请求 200 / 分析请求 4」，创建会话时可在 [1, 200] 内下调，开始后锁定；单步一次只发一次调用，
自动运行按原有暂停条件停下。
