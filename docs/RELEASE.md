# SceneWeave 发布资料

适用范围：首版（M00～M07）。需求来源 `PRD.md`，验收对照见 `docs/ACCEPTANCE.md`，架构见 `docs/ARCHITECTURE.md`。

**当前交付结论：未达到「可试用」**（缺项见第 7 节）。已完成的部分是**工程与确定性验收**，不是真实模型验收。

---

## 1. 环境要求与依赖锁

| 组件 | 实测版本 | 锁定位置 |
|---|---|---|
| Python | 3.12.14 | `backend/pyproject.toml`（`requires-python = ">=3.12,<3.13"`） |
| uv | 0.12.9 | — |
| Node.js | 24.2.0 | — |
| pnpm | 11.19.0 | `frontend/pnpm-lock.yaml` |
| 后端依赖 | fastapi 0.141.1、starlette 1.7.0、pydantic 2.13.5、pydantic-settings 2.15.0、uvicorn 0.54.0、pytest 8.4.2、pytest-asyncio 1.4.0、httpx 0.28.1 | `backend/uv.lock`（31 个包） |
| 前端依赖 | react／react-dom 19.3.0、vite 7.3.6、vitest 3.2.7、typescript 5.9.3、openapi-typescript 7.13.0、@testing-library/react 16.3.3 | `frontend/pnpm-lock.yaml` |
| 可选外部分析依赖 | **未安装**（`behavior-psychology-v2.0`，基线 `bd1e8fa…`） | 计划以可选依赖锁定（M06 未完成真实安装） |

## 2. 安装

```bash
cd backend && uv sync --dev          # 受限沙箱下可先 export UV_CACHE_DIR=<repo>/.cache/uv
cd ../frontend && pnpm install       # 受限沙箱下可加 --store-dir <repo>/.cache/pnpm-store
```

安装**不需要**任何模型密钥；分析能力默认关闭，也不要求外部包存在。

## 3. 启动

```bash
# 终端 1：后端（默认仅监听本机）
cd backend && uv run uvicorn role_theater.main:app --host 127.0.0.1 --port 8000

# 终端 2：前端（默认把 /api 代理到 127.0.0.1:8000）
cd frontend && pnpm run dev          # 打开 http://127.0.0.1:5173
```

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

密钥只从环境变量读取，**不写入代码、日志或业务记录**；健康检查只返回布尔值 `model_configured`。

## 5. 数据库迁移与备份恢复

### 迁移

- 迁移文件：`backend/role_theater/storage/migrations/00N_*.sql`（当前 `001_initial`、`002_runtime`、`003_analysis`）。
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
uv run python scripts/live_smoke.py --live --confirm-spend

# B) 端到端联调：真实三人聊天 + 定向事件 + 只读分析，证据写入 state/reports/live/
uv run python scripts/live_integration.py --live --confirm-spend --turns 3

# C) 直接启动服务，用真实模型跑场景（未配置密钥时会自动回落到确定性 Mock）
uv run uvicorn role_theater.main:app --host 127.0.0.1 --port 8000
```

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

- `live_smoke.py` 与 `live_integration.py` 都需要 `--live` **且** `--confirm-spend` **且** 有效密钥，缺任一即**拒绝运行**（退出码 2／3），**绝不回退成 Mock 后宣称通过**；
- 证据文件写入 `state/reports/live/`，只包含模型名、草稿／失败分类、用量、延迟，**不含密钥**；
- **未执行真实调用前，真实验收一律记为「未验证」**（见 `docs/ACCEPTANCE.md` §4）。

已实际验证的拒绝路径：无 `--live` → 2；无 `--confirm-spend` → 2；无密钥 → 3，且不发起任何调用。

## 7. 已知限制与缺项

| # | 限制／缺项 | 影响 |
|---|---|---|
| 1 | **真实模型未接通**（当前环境无密钥） | 三人真实聊天、定向事件、真实分析均未验证；`live_integration.py` 已就绪，导出 `SCENEWEAVE_MODEL_API_KEY` 后即可执行；不得据 Mock 结果宣称真实验收完成 |
| 2 | **服务未部署** | 仅在本机 `127.0.0.1` 运行过；无公网／隧道部署验证 |
| 3 | **外部分析仓库未安装** | 分析能力默认 `DISABLED`；模块路径与响应字段名待联调核对（`tasks/M06.md` U-M06-1/2） |
| 4 | ~~`thinking` 字段名待核对~~ **已关闭** | 官方文档确认 `thinking: {"type": "disabled"}`（默认 `enabled`）；见 `docs/SOURCES.md` §1.1。仍待真实调用观察的是响应组合（U-M03-2）与 90 秒期限（U-M03-3） |
| 5 | 聊天质量**人工观察**未做 | PRD 10 要求人工判断；三个预置场景已按人工裁决补齐（B6），Mock 样本已留档，但 Mock 不代表真实模型质量 |
| 6 | 界面人工视觉验收未做 | 组件行为有 48 项测试，但没有人工视觉与键盘可达性验收 |
| 7 | 单进程单 worker | 多用户鉴权、多 worker 并发、多场景并行属后续设计（PRD 1.3） |
| 8 | 远端 CI 未接入 | 当前是本地脚本 + 契约漂移检测 |
| 9 | `docs/SOURCES.md` 已建立，但 PRD 的 `[S1]`～`[S9]` 仍缺失 | 已记录本项目**实际核对过**的来源（DeepSeek API 文档）；`[S1]`～`[S9]` 原始地址不在 PRD 内，**未编造**，保持未验证 |
| 10 | SSE 在真实代理／浏览器下的时序未验证 | `U-M04-3`、`U-M05-2` |
| 11 | 已知非致命警告 | `starlette 1.7.0` 对 `httpx 0.28.1` 的 `StarletteDeprecationWarning` |

## 8. 模块证据索引

| 模块 | 报告 | 核验 |
|---|---|---|
| M00 工程与契约 | `state/reports/M00.md` | V1–V16 |
| M01 角色与场景 | `state/reports/M01.md` | V1–V12 |
| M02 可见性与调度 | `state/reports/M02.md` | V1–V7 |
| M03 模型适配 | `state/reports/M03.md` | V1–V6 |
| M04 运行与事件 | `state/reports/M04.md` | V1–V10 |
| M05 操作界面 | `state/reports/M05.md` | V1–V6 |
| M06 行为分析 | `state/reports/M06.md` | V1–V7 |
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
cd backend && uv run pytest                      # 347 项
cd frontend && pnpm run test                     # 48 项
cd frontend && pnpm run typecheck && pnpm run build

# 出站网络阻断下跑测试（证明无真实外部调用）
cd backend && PYTHONPATH=/tmp uv run pytest -p no_net_plugin

# 备份 / 恢复
scripts/backup_db.sh
```
