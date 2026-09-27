# 本机可试用推进记录（2026-09-27）

范围：M00–M07 之后的本机试用准备。依据 `PRD.md` 第 10 节与人工选择的“本机可试用”目标。
本轮没有发起 SceneWeave 真实模型调用，没有读取或打印模型密钥，也没有修改上游仓库、提交或推送 Git。

## 1. 已完成的改动

- 在 `backend/pyproject.toml` 与 `backend/uv.lock` 将 `behavior-psychology` 锁定到只读上游提交
  `bd1e8fa97b395223d629539022fbd92e1a5429d7`；项目虚拟环境按锁文件安装。
- 修正项目内分析适配：实际导入 `src.analyzer.DefaultBehaviorAnalyzer` 与
  `src.schemas.AnalysisRequest`；把供应商配置显式注入，不读取上游自己的凭证配置；
  请求始终 `persist_profile=false`。SDK 关闭隐式重试，DeepSeek 请求显式关闭思考，
  不发送工具；分析前的安全边界拦截不占用分析请求预算。
- 改进真实联调脚本：使用独立 SQLite 库保存证据；记录三人发言、定向事件对目标可见且
  不泄露给其他角色，并核对目标角色确实处理事件序号。分析需另加 `--with-analysis`；
  九份质量观察样本可用 `--quality-only` 分别生成，每份只发起三次角色请求。
  计划上限为 36 次角色请求与 1 次分析请求，尚未执行。
- 修复契约重建脚本在受限环境中的项目内缓存兜底，并避免重建时卸载已安装的可选依赖；
  补充 SQLite WAL/SHM 忽略规则，增强假本地服务测试的命令受理断言。
- 修正页面页脚已过时的模块说明；更新架构、安装、验收与状态文档。
- 建立 `docs/QUALITY_REVIEW.md`，供人工逐份记录九份真实样本的五项质量观察与异常。

## 2. 本轮实际执行的检查

| 检查 | 退出码 | 结果 |
|---|---:|---|
| `uv add --optional analysis --no-sync ...@bd1e8fa` | 0 | 锁定上游提交；未修改上游仓库 |
| `uv sync --extra analysis --dev --locked` | 0 | 从 Git 提交安装 `behavior-psychology` 2.1.0 |
| `uv lock --check` | 0 | 锁文件与项目依赖声明一致 |
| `PYTHONPATH=/private/tmp .venv/bin/python -m pytest -p no_net_plugin -p no:cacheprovider --tb=short` | 0 | **429 passed**；出站 DNS／连接由插件阻断，1 条既有弃用警告 |
| 同一阻断插件下单跑 `tests_optional/test_external_upstream.py` | 0 | **5 passed**；真实上游对象、SDK 参数、配置矩阵、完整应用假 SDK 链路 |
| `pnpm run test -- --run` | 0 | **49 passed** |
| `pnpm run typecheck`、`pnpm run build` | 0／0 | 类型检查和生产构建通过 |
| `scripts/export_contracts.sh` | 0 | 三项契约产物重建成功，生成物与 Git 版本无差异 |
| `git diff --check`、`uv lock --check` | 0／0 | 补丁格式与锁文件检查通过 |
| 本机浏览器只读检查 | 已观察 | 配置、聊天、历史、分析抽屉可打开；页脚新文案已在页面呈现 |
| 上游仓库 `git status --short --branch` | 0 | `main...origin/main`，工作区未被本轮改动 |

另一次未提升端口权限的后端回归有 6 项假本地服务测试因沙箱拒绝绑定 `127.0.0.1`
而失败；在允许本机回环端口后，完整回归通过。该失败不计为产品通过证据。

## 3. 核验边界和仍未完成的工作

1. **真实定向事件效果**：新脚本已有可控 Mock 检查，但还没有真实 DeepSeek 会话执行；
   不得把“目标视角含事件”或 Mock 成功写成真实效果验收。
2. **真实行为分析**：上游包安装与离线适配已验证，真实供应商请求及分析质量未验证。
3. **人工聊天质量观察**：三个预置场景各三次的真实样本尚未生成，也未由人工按
   “具体回应、角色差异、私有事实泄露、套话、允许沉默”逐项观察。
4. **当前运行进程**：浏览器显示分析能力关闭；这轮未中断用户当前的本机服务，
   因而页面只读观察不证明新后端代码已在该进程生效。
5. **部署范围**：人工已选择“本机可试用”；不要求公网部署，但本机新版本仍需在真实
   真实调用与验收后方可标为可试用。浏览器网络中断后的自动重连仍未验；
   键盘仅检查了部分控制项的焦点可达性。

## 4. 独立端口的本机运行检查

为避免中断原有的 `8000`／`5173` 服务，本轮在 `127.0.0.1:8001` 启动当前后端，
以 `SCENEWEAVE_MODEL_PROVIDER=mock`、`SCENEWEAVE_MODEL_FORCE_MOCK=true`、
`SCENEWEAVE_MODEL_API_KEY=` 和独立数据库
`sqlite:////private/tmp/sceneweave-local-trial-20260927.db` 隔离运行；前端通过新增的
`SCENEWEAVE_DEV_API_PORT=8001` 在 `127.0.0.1:5174` 启动。两项命令均进入
运行状态，后端输出 `Application startup complete`，前端输出 `ready`。

| 实际检查 | 退出码／结果 |
|---|---|
| `curl -fsS http://127.0.0.1:8001/api/health` | 0；`status=ok`、`run_state=READY`、`model_provider=mock`、`model_configured=false`、`model_credential_source=none` |
| `curl -fsS http://127.0.0.1:5174/api/health` | 0；返回同一组健康字段，证明前端代理连到独立后端 |
| 读取 `http://127.0.0.1:5174/` | HTTP 200 |
| 浏览器创建“三个室友的客厅”预置会话 | 成功，3 名角色、`READY`；模拟模式提示明确显示 |
| 浏览器单步运行 | 成功 1 次、失败 0 次，场景进入暂停；未发起真实模型请求 |
| 浏览器提交全体可见事件 | 事件 `#1` 显示在时间线，并提示“事件已生效” |
| 浏览器打开行为分析抽屉 | 显示“分析能力未开启”、实际分析模型请求数 0；按钮禁用 |
| 新端口配置后 `pnpm run typecheck`、`pnpm run build`、`pnpm run test -- --run` | 均退出码 0；前端 49 passed |
| `git diff --check` | 0 |

这证明当前代码能以 Mock 模式在本机独立运行，仍不证明真实模型效果、真实行为分析或
九份质量样本的人工作品判断。原有 `8000`／`5173` 服务未中断。

## 5. 事件流追赶与键盘检查

在上述隔离会话中，浏览器又提交全体可见事件 `#2`，页面显示“事件已生效”。
随后直接读取当前运行服务的有界 SSE 端点：

| 请求 | 退出码 | 实际结果 |
|---|---:|---|
| `GET /api/scenes/{id}/stream?since_seq=0&replay_limit=5`（提交 `#2` 前） | 0 | 返回已提交的 `id: 1` |
| `GET /api/scenes/{id}/stream?since_seq=1&replay_limit=5` | 0 | 仅返回 `id: 2`，正文为“断线追赶检查：第二条已提交事件。” |
| `GET /api/scenes/{id}/stream?since_seq=2&replay_limit=5` | 0 | 空响应，没有重复补发 |

这验证了**实际本机 HTTP 服务**的有界追赶，不等同于浏览器在网络中断后自动重连的
完整验收。浏览器键盘焦点检查确认 `Shift+Tab` 可以从分析抽屉按钮依次到达
“提交事件”、“事件可见范围”和“事件正文”；可见范围可用方向键展开、`Escape`
收起。未覆盖整页的键盘与辅助技术验收。

为核对持久化，本轮只停止自己启动的 `8001` Mock 后端（原有 `8000` 服务不受影响），
确认 `8001` 健康接口连接失败后，以相同隔离数据库重启。后端再次输出
`Application startup complete`，前端代理的健康接口重新返回 `status=ok`；
刷新浏览器后，历史会话仍为 `PAUSED`，打开后 `#1`、`#2` 各显示一次。
这一操作验证了重启后的持久化读取，**没有**观察到浏览器原有 EventSource 自动重连的
完整状态迁移，故该项仍列未验证。

结论：本机离线准备与分析适配通过；**“本机可试用”尚未完成**，不得将本报告的
Mock／假 SDK 证据计作真实供应商或人工质量验收。
