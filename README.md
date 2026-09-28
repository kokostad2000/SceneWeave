# SceneWeave（角色互动沙盒）

多个具有不同人设、当下目标和独立信息的虚构角色，在共同文字情境下交流；操作者可观察、暂停、插入事件，并按需调用独立的行为分析。

- 需求来源：[PRD.md](PRD.md)
- 开发规则：[AGENTS.md](AGENTS.md)
- 架构说明：[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **验收矩阵**：[docs/ACCEPTANCE.md](docs/ACCEPTANCE.md)
- **发布资料 / 已知限制**：[docs/RELEASE.md](docs/RELEASE.md)
- **v0.1.0 基线与恢复**：[docs/BASELINE.md](docs/BASELINE.md)
- 开发状态：[state/STATUS.md](state/STATUS.md)
- 各模块任务书与报告：[tasks/](tasks/)、[state/reports/](state/reports/)

## 当前进度

**M00～M07 已交付工程实现与确定性核验证据。M06 当前进行中。** 2026-09-28 真实分析定位发现
材料不足仍贴趋势标签、无依据附加标签，M06 已退回进行中；历史工程验收记录保留。
详见 [分析定位报告](state/reports/ANALYSIS-LOCALIZATION-2026-09-28.md)。

**交付结论：v0.1.0 本机可试用，人工质量验收尚未完成。** 已有真实三人聊天、
定向事件与行为分析证据，可选分析依赖已在项目虚拟环境安装；分析默认仍关闭。
当前应用代码基线为 `48a63eb86c89b7332d7e3080402f0ac2b6cdaf1b`，数据库迁移至 004。
本轮交付核验与真实使用观察见 [首版报告](state/reports/FIRST-RELEASE-2026-09-28.md)。
代理样本观察与人工验收分开记录；浏览器自动重连、长期运行及异机部署仍未验证。
运行进程可能已退出，使用前按下文启动并检查健康接口；历史启动记录不代表服务当前在线。

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
cd backend && uv sync --dev --locked

# 需要真实行为分析时，在 backend 目录安装可选依赖
uv sync --extra analysis --dev --locked

# 前端
cd frontend && pnpm install --frozen-lockfile
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
# 后端（459 项，含本轮 7 项交付／观察脚本检查）
cd backend && uv run --no-sync pytest

# 外部分析包已安装时：可选上游适配检查（7 项，使用假 SDK）
cd backend && uv run --no-sync pytest tests_optional/test_external_upstream.py

# 前端（49 项）
cd frontend && pnpm run test
cd frontend && pnpm run typecheck && pnpm run build

# 证明不发起真实外部调用：阻断出站网络后仍全部通过
cd backend && uv run --no-sync pytest -p scripts.block_outbound_plugin -r a
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
而不是崩溃。上游锁定到 `bd1e8fa97b395223d629539022fbd92e1a5429d7`，安装见上文。
真实模型冒烟使用已有凭证配置并需要显式开关：

```bash
cd backend && uv run --no-sync python scripts/live_smoke.py --live
```

## 契约产物

后端契约是接口唯一来源。修改 `backend/role_theater/contracts/` 后必须重新导出：

```bash
scripts/export_contracts.sh
```

该脚本重新生成 `backend/openapi.json`、`frontend/src/api/generated/contract-summary.json`
与 `frontend/src/api/generated/schema.d.ts`；后端测试会检测产物漂移。

## 配置

配置通过环境变量或项目 `.env` 提供，前缀 `SCENEWEAVE_`（例如 `SCENEWEAVE_MODEL_API_KEY`、
`SCENEWEAVE_DATABASE_URL`）。密钥由应用配置层加载，不写入代码、业务记录或日志。
未配置密钥时健康检查仍返回 200，仅 `model_configured=false`。

真实验收／观察脚本需要显式 `--live` 与有效配置；日常服务按供应商配置运行。
行为分析默认关闭，启用时设置 `SCENEWEAVE_ANALYSIS_ENABLED=true` 并安装 `analysis` extra。
每场预算默认「角色请求 200 / 分析请求 4」，创建会话时可在 [1, 200] 内下调，开始后锁定；单步一次只发一次调用，
自动运行按原有暂停条件停下。

## 持续使用观察

```bash
# 项目内新的证据目录；三个场景各两会话，上限 84 次角色请求和 6 次分析请求
cd backend && uv run --no-sync python scripts/observe_usage.py --live --rounds 2 \
  --out ../state/reports/usage-new-run
```

脚本使用完整应用 API 链路及独立数据库，保留原文、合法沉默、耗时与实际 token；
供应商失败停止采集且返回非零，不覆盖旧证据。该脚本不验证浏览器操作或长期稳定性。
