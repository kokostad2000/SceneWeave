# SceneWeave（角色互动沙盒）

当前版本已支持双模式聊天室、私聊及自由续聊：新建场景可在无新消息时轮流行动，全部角色沉默后暂停；旧会话保留原规则。工程核验为后端851项、可选分析11项、前端78项通过，20次真实请求是有限观察；人工自然度和长期容量尚未验收。详见 [实施与验收报告](state/reports/CHANGE-free-chat.md)。原始运行证据仅保留在本地。下文PC／DM／SR数字与服务状态是各开发阶段记录，2026-09-29旧版本地提交复核（原始记录仅本地留存）不代表本轮结果。


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
历史试用基线为 `48a63eb86c89b7332d7e3080402f0ac2b6cdaf1b`、迁移 004；当前版本包含私聊、双模式 P1、人物／本场设定分离与自由续聊，契约 `fc.p1.1`、迁移至 009。
本轮交付核验与真实使用观察见 [首版报告](state/reports/FIRST-RELEASE-2026-09-28.md)。
代理样本观察与人工验收分开记录；浏览器自动重连、长期运行及异机部署仍未验证。
运行进程可能已退出，使用前按下文启动并检查健康接口；历史启动记录不代表服务当前在线。

2026-09-29 双模式 P1 工程完成：配置首页的“角色互动沙盒”和“议题聊天室”为平级入口，后者必填议题、可空材料与初始观点；公开身份只使用明确填写的内容。两模式共用聊天、私聊、运行控制和历史，创建后模式固定。后端709／前端65项检查通过；真实观察12次请求，普通两模式均全员PASS，独立引导样本5条私聊／4次关联回复。人工质量和原M06 Q1/Q2继续未关闭，详见[双模式实施报告](state/reports/CHANGE-dual-mode-P1.md)。P1开发轮未切换原试用服务。随后已按用户授权启动当前双模式版本：前端 [127.0.0.1:5175](http://127.0.0.1:5175/)、后端 [127.0.0.1:8002](http://127.0.0.1:8002/api/health)，DeepSeek真实API配置已启用，行为分析仍关闭。启动核验见服务记录（原始记录仅本地留存）；启动记录不保证服务持续在线。

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
# 后端（当前 538 项）
cd backend && uv run --no-sync pytest

# 外部分析包已安装时：可选上游适配检查（7 项，使用假 SDK）
cd backend && uv run --no-sync pytest tests_optional/test_external_upstream.py

# 前端（当前 53 项）
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


## 一对一私聊（当前工作区）

角色可选择公共发言、主动私聊、回复私聊或沉默。私聊双方共享一项双向会话，公私聊使用同一场景调度与预算；新建场景正文最多 1000 个 Unicode 码点，已保存的旧场景沿用 200 码点规则。进入聊天页，在左侧选择公共频道、私聊对象或全场时间线；点击右侧角色切换到其可见材料，观察者按钮恢复全场。刷新会恢复页面、场景和频道，历史页只读，不新增模型请求。

当前独立核验为后端 538 passed、前端 53 passed，类型检查和构建通过。有限真实样本 8 次请求产生 6 条私聊、5 次关联回复，第三方实际输入检查通过；人工质量、真实长期容量及原分析 Q1／Q2 仍未完成。见 [私聊报告](state/reports/CHANGE-private-chat.md) 与 [新增验收矩阵](docs/ACCEPTANCE.md)。

```bash
# 默认 Mock，使用独立数据库和证据目录
cd backend
.venv/bin/python scripts/private_chat_acceptance.py
.venv/bin/python scripts/private_chat_capacity.py
# 已配置模型时显式执行有限真实验收，3～12 次，默认 8 次
.venv/bin/python scripts/private_chat_acceptance.py --live --turns 8
```

升级前后端时先按 [发布资料](docs/RELEASE.md) 备份数据库；旧客户端不支持 PRIVATE，应同时更新。既有试用数据库与服务未由本轮自动升级或重启。


## 人物与本场设定分离

新建会话时选择人物只复用名称；公开身份、人设、表达习惯、目标与私有背景在本场填写，均可留空。使用预置场景会显式复制该场景的配置。创建后可在聊天页编辑本场设定，首次角色请求后锁定。旧会话保留原模板快照并显示旧版提示；要使用新的空配置流程，请新建会话。

前端在 http://127.0.0.1:5175/，后端在 http://127.0.0.1:8002，当前保持真实 DeepSeek 配置，分析仍默认关闭。新接口提交 configuration_version=2；省略版本的旧客户端继续复制旧模板。升级前后的数据库一致性与有限真实观察见 [SR 报告](state/reports/CHANGE-scene-role-profile.md)。

```bash
cd backend
# 默认 Mock：独立数据库、两个类别各最多 3 次
.venv/bin/python scripts/scene_role_observation.py --turns 3
# 真实取证必须显式 --live，沿用已有项目配置
.venv/bin/python scripts/scene_role_observation.py --live --turns 3
```

空设定不保证角色主动发言。当前有限真实讨论样本三次均 PASS；显式露营预设三次 SPEAK。工程边界通过不等于人工对话质量、长期容量或原分析语义问题已经验收。


## 自由续聊（2026-09-29）

新建会话默认保存 `chat_policy_version=2`：每条正文最多1000 Unicode码点，角色模型输出预算4096 tokens。角色即使没有新信息，也能轮流补充、追问、私聊或选择沉默；全员最后一次成功行动均为PASS且没有待处理可见信息时暂停。点击继续／单步可重新给予机会；请求总预算200、上下文32000、私聊可见性和失败即暂停沿用。角色卡显示本人上下文使用量及接近上限提示。分析材料正文和情境各限4000，超限请缩小选择。

旧会话自动保存为策略1，继续使用200码点／1024输出及原调度，不改写旧快照。新建可由API显式指定1作对照，人物配置版本与聊天规则版本彼此独立。实施和实际验收见 [自由续聊报告](state/reports/CHANGE-free-chat.md)。有限样本不能替代人工自然度评估。

```bash
cd backend
# 独立数据库，默认Mock；加 --live 才使用应用已有配置
.venv/bin/python scripts/free_chat_observation.py --turns 6
.venv/bin/python scripts/free_chat_observation.py --live --turns 6
```
