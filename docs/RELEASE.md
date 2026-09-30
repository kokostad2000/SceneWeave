# SceneWeave 发布资料

适用范围：**v0.1.0 本机单用户试用版**（M00～M07）。需求来源 `PRD.md`，验收对照见 `docs/ACCEPTANCE.md`，架构见 `docs/ARCHITECTURE.md`。

**当前交付结论：本机可试用；正式质量验收尚未完成。** 实际真实调用和剩余观察项见下文及第 7 节。

**2026-09-28 交付收尾**：应用提交 `48a63eb86c89b7332d7e3080402f0ac2b6cdaf1b`，
迁移 001～004；后端出站阻断 **459 passed**、可选上游假 SDK **7 passed**、前端 **49 passed**，
类型检查与构建退出 0。新增七项为交付／观察脚本检查，产品代码保持该提交内容。
三场景各两会话的真实观察共 84 次角色请求、6 次分析请求，95,490 tokens；两份室友分析标签与目标行为矛盾，
已列 P1 反馈，六次 NORMAL 不代表语义验收通过。
见 [首版报告](../state/reports/FIRST-RELEASE-2026-09-28.md)、[使用观察](USAGE_OBSERVATION.md)、[基线与恢复](BASELINE.md)。
同期另一项真实分析定位发现 Q1/Q2，**M06 已退回进行中**；本基线是带已知限制的试用快照，
不能据本轮工程回归宣称所有模块当前均已验收，见 [定位报告](../state/reports/ANALYSIS-LOCALIZATION-2026-09-28.md)。

---

## 本机试用入口与历史运行记录

2026-09-27～28 已在本机启动并核对真实 DeepSeek 后端 `http://127.0.0.1:8002` 与前端
`http://127.0.0.1:5175`，仅监听回环地址。可打开前端，使用已有的三个室友
会话继续单步，也可创建新的预置会话。当前浏览器会话已有三次成功角色行动，
分析抽屉已有两次真实调用记录；详见
[`LIVE-TRIAL-2026-09-27.md`](../state/reports/LIVE-TRIAL-2026-09-27.md)。
服务由本机开发进程维持，进程可能已经退出，使用前检查健康接口；关闭终端或重启电脑后需依下文重新启动。数据库
`backend/sceneweave-live-trial.db` 保留会话；本轮独立备份已记录迁移 004 和实际表计数。**人工质量验收仍待完成**，
九份真实样本见 [`QUALITY_REVIEW.md`](QUALITY_REVIEW.md)。

## 1. 环境要求与依赖锁

| 组件 | 实测版本 | 锁定位置 |
|---|---|---|
| Python | 3.12.14 | `backend/pyproject.toml`（`requires-python = ">=3.12,<3.13"`） |
| uv | 0.12.9 | — |
| Node.js | 24.2.0 | — |
| pnpm | 11.19.0 | `frontend/pnpm-lock.yaml` |
| 后端依赖 | fastapi 0.141.1、starlette 1.7.0、pydantic 2.13.5、pydantic-settings 2.15.0、uvicorn 0.54.0、pytest 8.4.2、pytest-asyncio 1.4.0、httpx 0.28.1 | `backend/uv.lock`（37 个包，含可选分析依赖） |
| 前端依赖 | react／react-dom 19.3.0、vite 7.3.6、vitest 3.2.7、typescript 5.9.3、openapi-typescript 7.13.0、@testing-library/react 16.3.3 | `frontend/pnpm-lock.yaml` |
| 可选外部分析依赖 | `behavior-psychology` 2.1.0（提交 `bd1e8fa…`）已在本机项目虚拟环境安装，离线及真实调用均已执行 | `backend/uv.lock` 的 `analysis` extra；语义质量仍需人工观察 |

## 2. 安装

```bash
cd backend && uv sync --dev --locked  # 受限沙箱下可先 export UV_CACHE_DIR=<repo>/.cache/uv
uv sync --extra analysis --dev --locked  # 需要真实行为分析时，在 backend 目录执行
cd ../frontend && pnpm install --frozen-lockfile  # 受限沙箱下可加 --store-dir <repo>/.cache/pnpm-store
```

安装**不需要**任何模型密钥；分析能力默认关闭，也不要求外部包存在。

## 3. 启动

```bash
# 终端 1：后端（默认仅监听本机）
cd backend && uv run uvicorn role_theater.main:app --host 127.0.0.1 --port 8000

# 启用真实行为分析时，在另一次启动中使用可选依赖：
export SCENEWEAVE_ANALYSIS_ENABLED=true
uv run --extra analysis uvicorn role_theater.main:app --host 127.0.0.1 --port 8000

# 终端 2：前端（默认把 /api 代理到 127.0.0.1:8000）
cd frontend && pnpm run dev          # 打开 http://127.0.0.1:5173
```

若已有服务占用默认端口，可让新版本在独立端口试跑。例如后端用 `--port 8001`，
前端用 `SCENEWEAVE_DEV_API_PORT=8001 pnpm exec vite --host 127.0.0.1 --port 5174`；前端仍只向
`127.0.0.1` 的指定端口代理 `/api`。启动隔离的 Mock 会话时显式设置
`SCENEWEAVE_MODEL_PROVIDER=mock` 和 `SCENEWEAVE_MODEL_FORCE_MOCK=true`，
并使用独立的 `SCENEWEAVE_DATABASE_URL`，不要把模拟结果当成真实模型验收。

服务默认只监听 `127.0.0.1`；**不**提供鉴权，因此不要把无认证服务暴露到公网（PRD 1.3）。

## 4. 配置项

全部通过环境变量提供，前缀 `SCENEWEAVE_`：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `SCENEWEAVE_HOST` / `SCENEWEAVE_PORT` | `127.0.0.1` / `8000` | 监听地址与端口 |
| `SCENEWEAVE_DATABASE_URL` | `sqlite:///./sceneweave.db` | SQLite 路径（支持 `sqlite:///` 前缀） |
| `SCENEWEAVE_MODEL_NAME` | `deepseek-flash` | 运行模型名（与开发模型分离） |
| `SCENEWEAVE_MODEL_BASE_URL` | 官方默认 | Chat Completions 基地址 |
| `SCENEWEAVE_MODEL_API_KEY` | 无 | **唯一**密钥入口；未配置时使用确定性 Mock |
| `SCENEWEAVE_MODEL_FORCE_MOCK` | `false` | 强制 Mock（演示／测试），即使配置了密钥也不联网 |
| `SCENEWEAVE_ANALYSIS_ENABLED` | `false` | 是否开启行为分析能力 |
| `SCENEWEAVE_CORS_ALLOW_ORIGINS` | 本机 5173 | 前端开发来源 |

模型密钥可从项目 `.env` 或环境变量读取（环境变量优先），**不写入代码、日志或业务记录**；
健康检查只返回 `model_configured` 布尔值与凭证来源标记，不返回密钥内容。

## 5. 数据库迁移与备份恢复

### 迁移

- 迁移文件：`backend/role_theater/storage/migrations/00N_*.sql`（当前 001_initial、002_runtime、003_analysis、004_scene_scheduler、005_private_chat、006_request_snapshot）。
- 启动时自动应用缺失迁移；已应用迁移记录 **checksum**，内容被改写会**拒绝启动**（必须新增迁移文件）。
- 重复启动是幂等的：第二次应用返回空列表。

### 备份

```bash
scripts/backup_db.sh                      # 默认备份 backend/sceneweave.db → state/backups/
scripts/backup_db.sh <源库> <目标文件>      # 指定路径
```

脚本优先用 `sqlite3 .backup`（事务一致快照），没有 `sqlite3` CLI 时退回「WAL 检查点 + 文件复制」，并打印各表行数。

### 恢复

1. 停止服务（避免并发写）；
2. 把备份文件复制回 `SCENEWEAVE_DATABASE_URL` 指向的路径；
3. 重新启动：迁移自动执行且幂等，数据即为备份时点。

已实际验证：备份后恢复，场景数、时间线条目与事件正文完整，`applied_migrations` 为空（未重复应用）。

## 6. 接入 DeepSeek 真实 API

接口契约已按官方文档核对（结论与来源见 `docs/SOURCES.md` §1.1）：`POST {base_url}/chat/completions`、
`model=deepseek-flash`、`thinking: {"type": "disabled"}`（该字段默认 `enabled`，必须显式关闭）、
`response_format={"type": "json_object"}`（**必须同时在提示词里指示模型输出 JSON**，本项目 ContextBuilder 已包含该指示）。

### 6.1 启用真实调用

密钥可来自两处（**环境变量优先于 .env**）：

**方式 A：`.env` 文件（推荐，便于本地长期使用）**

```bash
cp .env.example .env        # 推荐放在仓库根目录
# 编辑 .env，填入 SCENEWEAVE_MODEL_API_KEY=...
```

读取位置与优先级（**实测结论，不是推测**）：

| 位置 | 行为 |
|---|---|
| `<仓库根>/.env` | 先读取；**推荐只保留这一处** |
| `<仓库根>/backend/.env` | 后加载，**两者同时存在时会覆盖仓库根那份**（容易踩坑，因此建议只用一处） |
| 环境变量 | 优先于任何 `.env` |
| 代码显式传入（脚本／测试） | 优先级最高 |

- `.env` 已被 `.gitignore` 忽略（`.env`／`.env.*`），只有 `.env.example` 模板入库；
- `.env` 只含变量名与值，**不会**被写入日志、业务记录或 API 响应；
- 健康检查会报告**来源**（不含内容）：

```bash
curl -sS http://127.0.0.1:8000/api/health | python3 -m json.tool
# 期望看到 "model_configured": true, "model_credential_source": "dotenv"
```

**方式 B：环境变量**

```bash
export SCENEWEAVE_MODEL_API_KEY=...        # 可选：export SCENEWEAVE_MODEL_NAME=deepseek-flash
curl -sS https://api.deepseek.com/models -H "Authorization: Bearer $SCENEWEAVE_MODEL_API_KEY"   # 可选：先验证凭证
```

**优先级（高 → 低）**：代码显式传入 > 环境变量 > `.env` > 默认值。测试一律以 `_env_file=None`
构造 `Settings`，**因此真实 `.env` 永远不会被测试读取**，不会因跑测试而产生费用（有专门用例固定该行为）。

然后任选一条：

```bash
cd backend

# A) 单次调用冒烟（最省钱）：验证鉴权、模型名、thinking 开关、JSON 输出
uv run python scripts/live_smoke.py --live

# B) 端到端联调：真实三人聊天 + 定向事件，证据与独立数据库写入 state/reports/live/
.venv/bin/python scripts/live_integration.py --live --turns 3

# 需要额外执行一次真实行为分析时，显式开启分析并增加一次供应商调用
.venv/bin/python scripts/live_integration.py --live --turns 3 --with-analysis

# 质量观察留样：对每个预置场景分别运行三次；每次只执行 3 次角色请求
.venv/bin/python scripts/live_integration.py --live --quality-only --preset roommates
.venv/bin/python scripts/live_integration.py --live --quality-only --preset convenience_store
.venv/bin/python scripts/live_integration.py --live --quality-only --preset campsite

# C) 直接启动服务，用真实模型跑场景（未配置密钥时会自动回落到确定性 Mock）
uv run uvicorn role_theater.main:app --host 127.0.0.1 --port 8000
```

质量留样命令对每个预置场景需各执行 **3 次**，共 9 份样本。专项验收最多执行
3 次初始角色请求、6 次事件后请求和 1 次分析请求；连同 9 份质量样本，计划上限为
**36 次角色请求 + 1 次分析请求**。所有证据与独立 SQLite 数据库写入 `state/reports/live/`。
按 `AGENTS.md` 当前规则，真实调用无需逐次人工授权；每次供应商请求的输入与输出
合计上限为 **10,000,000 tokens**，角色与行为分析发送前都做保守上界检查。
真实调用仍会产生费用，脚本退出码 0 也不替代对样本的人工质量观察。

`SCENEWEAVE_MODEL_NAME` 现在会真正注入运行器（**此前只读配置、未生效，已修复并测试**）。

### 6.3 接入本地模型（不需要密钥、不产生费用）

`SCENEWEAVE_MODEL_PROVIDER=local` 可把运行模型换成**本机或局域网内**的 OpenAI 兼容推理服务：

| 本地服务 | `SCENEWEAVE_MODEL_BASE_URL` |
|---|---|
| Ollama | `http://127.0.0.1:11434/v1` |
| LM Studio | `http://127.0.0.1:1234/v1` |
| vLLM | `http://127.0.0.1:8000/v1` |
| llama.cpp（`llama-server`） | `http://127.0.0.1:8080/v1` |

```bash
# .env
SCENEWEAVE_MODEL_PROVIDER=local
SCENEWEAVE_MODEL_BASE_URL=http://127.0.0.1:11434/v1
SCENEWEAVE_MODEL_NAME=qwen2.5:7b          # 换成你实际拉取的模型
# SCENEWEAVE_MODEL_API_KEY=               # 本地服务留空即可
```

与云服务的三点差异（本地服务常见的坑，本项目已分别处理）：

1. **不需要凭证** → 本地提供方不被「无密钥回落 Mock」规则拦住；健康检查会显示
   `"model_provider": "local"`、`"model_configured": true`、`"model_credential_source": "none"`；
2. **不发送 `thinking`** → 该字段是 DeepSeek 专有，严格的本地服务会因未知字段直接 400；
3. **`response_format` 可关闭**（`SCENEWEAVE_LOCAL_INCLUDE_RESPONSE_FORMAT=false`）→ 部分实现的
   JSON 模式支持不完整；关闭后仍由提示词约束「只返回 JSON」，**解析与失败分类不变**。

**没有安装本地模型时的验证方式**（离线、不花钱）：项目自带一个严格模式的假本地服务：

```bash
cd backend
uv run python scripts/fake_local_model.py --port 11434 --model qwen2.5:7b   # 终端 1
# 终端 2：按上面的 .env 启动 uvicorn，然后建场景并单步
```

它是**回放固定脚本**的假服务，只用于验证链路（含「不发送云服务专有字段」），
**不代表本地模型的对话质量**。

**仍未验证**：真实本地模型（Ollama／LM Studio／vLLM／llama.cpp）的输出质量与稳定性——
本机未安装任何本地推理服务，因此只验证了协议与链路层。

### 6.2 真实性要求

- `live_smoke.py` 与 `live_integration.py` 都需要 `--live` 与有效密钥，缺任一即**拒绝运行**（退出码 2／3），**绝不回退成 Mock 后宣称通过**；前者要求环境变量，后者可从项目 `.env` 读取；
- 证据文件写入 `state/reports/live/`，只包含模型名、草稿／失败分类、用量、延迟，**不含密钥**；
- **未执行真实调用前，真实验收一律记为「未验证」**（见 `docs/ACCEPTANCE.md` §4）。

当前拒绝路径：无 `--live` → 2；无密钥 → 3，均不发起任何调用。旧版还要求
`--confirm-spend`；该门槛已按当前人工指令移除，旧版验证记录保留在历史报告中。

## 7. 已知限制与缺项

| # | 限制／缺项 | 影响 |
|---|---|---|
| 1 | **真实模型已接通** | 新版两次专项、九份真实样本和一次浏览器三人会话已执行；定向事件的可见性与一次语义效果已验证。九份样本的人工质量观察待完成，见最新试用报告 |
| 2 | **仅本机服务** | 试用入口 `127.0.0.1:8002`／`5175`；进程需核对或重启。异机与公网部署未验证，超出本次本机目标 |
| 3 | **真实行为分析已联调，语义问题未关闭** | 历史专项与浏览器共 3 次，本轮真实使用另 6 次 NORMAL；室友两份标签与安然主动行为矛盾（F1/P1），长期语义质量待人工复核，见 `docs/USAGE_OBSERVATION.md` |
| 4 | ~~`thinking` 字段名待核对~~ **已关闭** | 官方文档确认 `thinking: {"type": "disabled"}`（默认 `enabled`）；见 `docs/SOURCES.md` §1.1。真实响应的 `finish_reason=stop`、`usage`（含 `cached_tokens`）与 `id` 语义已在 2026-09-27 的 22 次调用中观察到，`U-M03-2` 由此可关闭；90 秒期限（U-M03-3）仍未触发观察 |
| 5 | 聊天质量**人工观察**未做 | 三预置场景各三份真实样本已留档；`docs/QUALITY_REVIEW.md` 人工结论待填写，便利店全员沉默样本需重点判断 |
| 6 | 界面人工视觉验收未做 | 组件行为有 49 项测试，但没有人工视觉与键盘可达性验收 |
| 7 | 单进程单 worker | 多用户鉴权、多 worker 并发、多场景并行属后续设计（PRD 1.3） |
| 8 | 远端 CI 未接入 | 当前是本地脚本 + 契约漂移检测 |
| 9 | `docs/SOURCES.md` 已建立，但 PRD 的 `[S1]`～`[S9]` 仍缺失 | 已记录本项目**实际核对过**的来源（DeepSeek API 文档）；`[S1]`～`[S9]` 原始地址不在 PRD 内，**未编造**，保持未验证 |
| 10 | 浏览器 EventSource 自动重连未验证 | 实际 HTTP 按序补发已检查；代理中断测试中前端重启引起整页刷新，不能证明 EventSource 自动重连 |
| 11 | 已知非致命警告 | `starlette 1.7.0` 对 `httpx 0.28.1` 的 `StarletteDeprecationWarning` |
| 12 | 短时观察不代表长期稳定性 | 本轮六会话连续采集约两分钟；沉默收束、事件语义效果与生成额外事实见 F2～F4 |

## 8. 模块证据索引

| 模块 | 报告 | 核验 |
|---|---|---|
| M00 工程与契约 | `state/reports/M00.md` | V1–V16 |
| M01 角色与场景 | `state/reports/M01.md` | V1–V12 |
| M02 可见性与调度 | `state/reports/M02.md` | V1–V7 |
| M03 模型适配 | `state/reports/M03.md` | V1–V6 |
| M04 运行与事件 | `state/reports/M04.md`、`state/reports/FIX-runtime-consistency.md` | V1–V10；维护修复 R1–R7 |
| M05 操作界面 | `state/reports/M05.md` | V1–V6 |
| M06 行为分析 | `state/reports/M06.md`、`state/reports/ANALYSIS-LOCALIZATION-2026-09-28.md` | 历史工程 V1–V7；当前进行中，Q1/Q2 待修复 |
| M07 集成与交付 | `state/reports/M07.md` | V1–V8 |
| 硬验收矩阵 | `docs/ACCEPTANCE.md` | 14 项硬验收 |
| 质量观察样本（Mock） | `state/reports/quality-observation-mock.json` | 唯一预置场景 ×3 |

## 8.1 预置场景

| key | 标题 | 角色 | 来源 |
|---|---|---|---|
| `roommates` | 三个室友的客厅 | 安然、许川、陈禾 | PRD 3.1 |
| `convenience_store` | 深夜便利店的三个顾客 | 林小满、周远、郑好 | **人工裁决新增**（B6），项目自撰虚构内容 |
| `campsite` | 周末露营地的三个人 | 何澜、苏木、涂山 | **人工裁决新增**（B6），项目自撰虚构内容 |

后两个场景的角色与情境**不是** PRD 的规定内容；撰写时遵守 PRD 3.1 的约束（角色目标与私有背景互不相同，且不预设争吵、和解或最终决定）。

```bash
# 三个预置场景各运行三次，输出可自动判定的质量信号（Mock）
cd backend && uv run python scripts/quality_observation.py --out ../state/reports/quality-observation-mock.json
```

## 9. 常用命令速查

```bash
# 契约产物（后端是唯一来源）
scripts/export_contracts.sh

# 测试
cd backend && uv run --no-sync pytest            # 459 项
cd backend && uv run --no-sync pytest tests_optional/test_external_upstream.py  # 7 项，假 SDK
cd frontend && pnpm run test                     # 49 项
cd frontend && pnpm run typecheck && pnpm run build

# 出站网络阻断下跑测试（证明无真实外部调用）
cd backend && uv run --no-sync pytest -p scripts.block_outbound_plugin -r a

# 备份 / 恢复
scripts/backup_db.sh
```


## 8. 私聊增量升级与回退（当前工作区 pc.1）

本轮代码尚未提交。契约 pc.1／提示模板 role_action@pc.1；配套部署构建后的前端与后端，不能保留将 PRIVATE 当作公开消息的旧客户端。005 新增频道／对象／会话字段，006 保存新请求完整输入快照；001～004 未修改。旧消息为 PUBLIC、版本 1、recipient_id=null；旧场景原预算与已结束状态保留，新消息版本 2，事件版本仍 1。

1. 使用 `scripts/backup_db.sh <源库> <升级前备份>` 取得一致备份，备份路径需为本项目专用目录。
2. 将备份复制成独立升级副本，设置该副本的 SCENEWEAVE_DATABASE_URL，在项目环境用 `Database(path).migrate()` 验证 005／006；核对 PRAGMA integrity_check、各表原列、预算、游标、幂等记录与已结束状态，第二次迁移应为空。
3. 本机实际切换时停止旧服务，保留升级前备份，将新应用指向验证后的副本，再启动后端与配套前端。PENDING 请求按原规则转 UNKNOWN 并暂停，不自动重放。
4. 需要回退时停止新服务，使用升级前备份与配套旧应用，保留新库供取证；不得直接让旧程序读取新增私聊数据，也不对新库做删除列或历史改写。

本轮已在合成 004 库的 SQLite backup 副本验证逐表原字段保留、005／006 幂等和完整性，并验证 005 失败整体回滚；全新库与旧 003 升级也有独立用例。原试用库和运行服务未改动。全量离线回归 538／前端 53，独立删除生成产物后两次重建一致；真实私聊样本 8 次请求、6 条私聊、5 次回复、6812 tokens，最大单次 1034。详细证据见 `state/reports/M07.md` PC 增量段。

私聊为剧中信息权限，本机操作者仍可读全场，不增加多用户鉴权。人数仍 2～8、正文仍 200 码点、提示仍 32000 码点、公私预算共享；多人私聊、自动冷场开口、摘要／长期记忆未加入。真实长期容量、人工对话质量、浏览器 EventSource 自动重连和异机部署未验证；原 M06 Q1／Q2 保持进行中。
