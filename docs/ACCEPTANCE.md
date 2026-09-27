# SceneWeave 验收矩阵

来源：`PRD.md` 第 10 节「硬验收」+ 第 9 节各模块通过条件。
规则：**每条都必须指向实际执行过的测试与命令**；环境无法验证的项标为「未验证」，**不计入通过**。

- 生成日期：2026-09-26
- 本轮验证环境：Python 3.12.14、Node 24.2.0、pnpm 11.19.0、SQLite（标准库 `sqlite3`）
- 测试规模：后端 **347 passed**、前端 **48 passed**（均为确定性 Mock／假分析器，**不联网、不需要密钥**）
- **2026-09-27 更新**：引用缺陷修复与预算默认值调整后，重跑为后端 **423 passed**（出站网络阻断下同样 423）、
  前端 **49 passed**；`tsc --noEmit` 与 `vite build` 退出码 0。真实模型已接通并跑过两场真实会话，
  见 §4 与 `state/reports/FIX-reply-reference.md`。本文件 §1～§3 的 347／48 保留为 M07 交付时的原始记录。
- **2026-09-27 本机试用推进**：当前代码重跑后端 **429 passed**（阻断出站）、可选上游适配
  **5 passed**、前端 **49 passed**，类型检查与构建通过；独立 `8001`／`5174` 端口的
  Mock 服务与浏览器操作、实际 HTTP SSE 有界追赶已验证。证据见
  `state/reports/LOCAL-TRIAL-2026-09-27.md`。这不计作真实供应商或人工质量验收。

- **2026-09-27 真实试用更新**：后端 **435 passed**（外网阻断）、可选上游 **7 passed**、
  前端 **49 passed**；本机真实服务与专项调用已执行。下方 M07 阶段表格保留历史
  通过条件；当前真实验收以 §8 和最新报告为准。

---

## 1. 硬验收（PRD 第 10 节）

| # | 硬验收项 | 覆盖测试 | 命令 | 结论 |
|---|---|---|---|---|
| 1 | **2／3／5／8 人配置** | `test_m01_scenes.py::test_scene_creation_is_data_driven_for_any_allowed_size[2/3/5/8]`；`test_m07_end_to_end.py::test_scene_sizes_two_three_five_eight_via_http`；越界 0／1／9／20 → 422 | `cd backend && uv run pytest` | 通过 |
| 2 | **快照隔离** | `test_m01_snapshot_isolation.py`（8 项：改模板／删模板／复制模板／锁定后改模板／两场景互不影响／预置模板按需重建） | 同上 | 通过 |
| 3 | **可见性过滤** | `test_m02_context.py`（私有材料不串入、定向事件仅目标可见、公开内容全体可见、结构上排除非剧情数据） | 同上 | 通过 |
| 4 | **SPEAK／PASS 协议** | `test_action_contract.py`（额外字段拒绝、PASS 必须全空、SPEAK 1～200 码点、码点而非 UTF-16）、`test_m03_model_adapter.py`（12 项内容失败分类） | 同上 | 通过 |
| 5 | **公平调度** | `test_m02_scheduler.py`（启动机会一次、自发言不自唤醒、点名优先上限 2、最久未行动轮转、平局按固定顺序） | 同上 | 通过 |
| 6 | **暂停／结束** | `test_m04_state_machine.py`（六状态迁移表）、`test_m04_runner.py::test_pause_stops_the_loop_at_the_call_boundary`、`test_m07_end_to_end.py::test_paused_scene_can_be_resumed_and_ended` | 同上 | 通过 |
| 7 | **事件顺序** | `test_m04_runner.py::test_events_injected_during_a_call_activate_after_it_in_order`（调用中两个事件 → 接受顺序生效、序号 2／3）、`test_m07_end_to_end.py`（时间线顺序 = 生效顺序：3 发言 → 定向事件 #4 → 被唤醒发言 #5） | 同上 | 通过 |
| 8 | **预算** | `test_m04_runner.py`（发送即占用、失败不退款、耗尽 → ENDED、未发送不占用、UNKNOWN 保守占用）、`test_m06_analysis.py`（分析预算独立、拦截不占、耗尽拦截） | 同上 | 通过 |
| 9 | **空响应与截断** | `test_m03_model_adapter.py`（空 content／全空白／`finish_reason=length` 优先于内容合法性／非法 JSON／非对象） | 同上 | 通过 |
| 10 | **重入幂等** | `test_m04_runner.py::test_repeated_command_returns_existing_result_without_new_call`、`test_m04_api.py::test_command_is_idempotent_through_http`、`test_m04_api.py::test_event_injection_is_idempotent` | 同上 | 通过 |
| 11 | **SSE 追赶** | `test_m04_sse.py`（按 `seq` 补发、`since_seq` 只发新条目、重连不重复、有界追赶、结束关闭、心跳不入剧情） | 同上 | 通过 |
| 12 | **重启暂停** | `test_m04_runner.py::test_restart_marks_pending_unknown_and_pauses_without_replay`；**真实进程级验证**：崩溃写入在途 `PENDING` → 重启后 `PAUSED`/`PROCESS_INTERRUPT`、预算不退款、时间线零新增（见 `state/reports/M04.md` §3 第 6 项） | `uv run pytest` + 手动 uvicorn 两次 | 通过 |
| 13 | **分析隔离** | `test_m06_analysis.py::test_analysis_does_not_change_the_scene_or_the_role_context`、`test_m06_api.py::test_analysis_state_has_no_effect_on_the_scene`、`test_m06_analysis.py::test_records_are_isolated_by_scene_and_agent`、`test_there_is_no_profile_table_in_the_schema` | `uv run pytest` | 通过 |
| 14 | **依赖可选性** | `test_m06_analysis.py::test_load_analysis_port_disabled_does_not_need_the_external_package`、`test_load_analysis_port_enabled_without_package_gives_a_concrete_reason`、`test_health.py::test_health_does_not_require_external_analysis_package` | 同上 | 通过 |

## 2. 模块通过条件（PRD 第 9 节）

| 模块 | 通过条件 | 结论 | 证据 |
|---|---|---|---|
| M00 | 不用密钥可启动健康检查；契约测试通过 | **已验收** | `state/reports/M00.md` §11（核验 V1–V16） |
| M01 | 三人增至五人不改代码；旧场景不受模板改动影响 | **已验收** | `state/reports/M01.md` §3、§8 |
| M02 | 私有材料不串入；自发言不自唤醒；PASS 能使场景停下来 | **已验收** | `state/reports/M02.md` §2、§7 |
| M03 | 关闭隐式重试；空输出、截断等按契约失败 | **已验收** | `state/reports/M03.md` §2、§6 |
| M04 | 假模型端到端；暂停排序正确；重连与重启不重放请求 | **已验收** | `state/reports/M04.md` §2、§7 |
| M05 | 组件测试通过；操作可用；无假完成态 | **已验收** | `state/reports/M05.md` §2、§7 |
| M06 | 关闭模块可正常聊天；降级隔离；无画像写入 | **已验收** | `state/reports/M06.md` §2、§7 |
| M07 | Mock 与真实证据分开；缺密钥不得宣称真实验收完成 | **已验收（含未验证项）** | `state/reports/M07.md` |

## 3. 确定性端到端（Mock 证据）

| 项目 | 命令 | 结果 |
|---|---|---|
| 全量后端回归 | `cd backend && uv run pytest` | **347 passed** |
| 出站网络完全阻断下回归 | `cd backend && PYTHONPATH=/tmp uv run pytest -p no_net_plugin` | **347 passed**（证明无真实外部调用） |
| 全量前端回归 | `cd frontend && pnpm run test` | **48 passed** |
| 类型与构建 | `cd frontend && pnpm run typecheck && pnpm run build` | 退出码 0 |
| 假模型端到端场景 | `uv run pytest tests/test_m07_end_to_end.py` | **3 passed**（三人聊天 + 定向事件 + 分析 + 预算 + 视角隔离 + 只读历史） |
| 契约产物一致性 | `scripts/export_contracts.sh` + `tests/test_contract_export.py` | 一致（漂移即失败） |

## 4. 真实模型验收（2026-09-27 本机更新）

| 项目 | 当前状态 | 证据与边界 |
|---|---|---|
| 三人真实聊天 | **已验证** | 专项两场各 6 次成功角色请求；浏览器本机会话三人各发言一次 |
| 定向事件的真实效果 | **已验证一例** | 漏水事件仅目标可见，目标后续发言提及漏水；不推断所有事件都能稳定影响剧情 |
| 真实行为分析调用 | **已执行** | 专项 1 次 `NORMAL`，浏览器 2 次（`NORMAL`、`DEGRADED`）；第一次浏览器结果偏题，修正提示后复测聚焦目标但缺行为标签 |
| 三预置场景各三次真实样本 | **已留样，人工质量观察未验证** | 九份 JSON／SQLite 见 `docs/QUALITY_REVIEW.md`；便利店一次全员 `PASS` |
| `live_smoke.py` 单次路径 | **未验证** | 已由完整脚本与浏览器真实调用覆盖主要运行链路，该独立冒烟脚本未执行 |
| `live_integration.py` 完整路径 | **已执行** | 首次含真实分析、第二次验证显著定向事件；原始退出码与异常见最新报告 |
| Chat Completions 契约 | **已观察真实响应** | `finish_reason`、usage、响应 ID；90 秒超时分支仍未触发 |

真实脚本需要显式 `--live` 与有效配置；角色和分析单次请求上限
10,000,000 tokens。最新报告：
[`LIVE-TRIAL-2026-09-27.md`](../state/reports/LIVE-TRIAL-2026-09-27.md)。

## 5. 安装与运维验证

| 项目 | 命令 | 结果 |
|---|---|---|
| 依赖安装 | `cd backend && uv sync --dev`；`cd frontend && pnpm install` | 退出码 0（锁文件 `uv.lock`／`pnpm-lock.yaml`） |
| 数据库迁移（幂等） | 启动时自动执行；`tests/test_m01_storage.py` | 首次 `[1, 2, 3]`，之后 `[]`；篡改已应用迁移的 checksum 会被拒绝 |
| **备份** | `scripts/backup_db.sh <源库> <目标>` | 实际执行成功，打印 12 张表与行数 |
| **恢复** | 备份文件放回 `SCENEWEAVE_DATABASE_URL` 路径后启动 | 场景数、时间线条目、事件正文完整；迁移记录为空（幂等，未重复应用） |
| 崩溃恢复 | 真实 uvicorn 崩溃 + 重启 | `PAUSED`/`PROCESS_INTERRUPT`、在途标 `UNKNOWN`、**不重放付费请求** |
| 本地启动 | `uv run uvicorn role_theater.main:app --host 127.0.0.1 --port 8000`；`pnpm run dev` | 仅监听本机；前端 `/api` 代理到本机后端 |
| 凭证配置（`.env`／环境变量） | `tests/test_m07_config_dotenv.py`（13 项）+ 实测优先级 | `.env` 可被读取并报告来源 `dotenv`；环境变量优先；显式参数优先；密钥不出现在 `repr`／`model_dump`／健康检查响应；**测试注入 `_env_file=None`，真实 `.env` 不会被测试读取**（有占用测试固定）；实测两个 `.env` 同时存在时 `backend/.env` 覆盖仓库根 `.env`，已写入 `docs/RELEASE.md` §6.1 |

## 6. 未验证项汇总（不计入通过）

| 编号 | 项目 | 当前障碍 |
|---|---|---|
| U-M03-3 | 90 秒真实供应商超时 | 尚未遇到该分支；离线失败路径已测 |
| U-M04-1/2/3 | 多标签并发、长时间运行、真实代理下完整 SSE 时序 | 本轮只验证本机单会话、实际 HTTP 按序补发 |
| U-M05-1/2 | 人工视觉验收、浏览器 EventSource 自动重连 | 浏览器真实交互已操作；人工视觉结论和自动重连仍需观察 |
| U-M06-质量 | 分析长期语义质量 | 偏题曾出现，单次修正复测聚焦目标但降级，需更多人工判断 |
| U-M07-1 | 九份聊天质量人工观察 | 样本齐备，`docs/QUALITY_REVIEW.md` 结论栏待人工填写 |
| U8 | 远端 CI | 仅本地回归；未接入远端 CI |
| U7 | 异机或公网部署 | 本次目标限本机，未执行异机／公网部署 |

## 7. 需求矛盾与遗留缺口

| 编号 | 事项 | 处置 |
|---|---|---|
| B1 | `docs/SOURCES.md` 缺失（PRD 的 [S1]～[S9] 原始地址不在 PRD 内） | 保持**遗留缺口**：不编造引用；需人工提供地址或授权联网检索 |
| B4 | `docs/ACCEPTANCE.md` 缺失 | **本文件已建立**（M07），硬验收 14 项逐条对照完成 |
| B6 | PRD 第 10 节要求「预置三个场景各运行三次」，但第 3.1 节只定义了**一个**预置场景 | **人工裁决：补两个预置场景**（不改 PRD）。已新增 `convenience_store`／`campsite`，各 3 名角色；角色与情境为项目自撰内容。三个场景各运行三次的 Mock 样本已留档 |
| B7 | PRD 第 10 节「预置三个场景」与第 1.2 节「预置室友模板」的数量口径不一致 | 同上，登记为同一矛盾的另一种表述 |

## 8. 交付结论（2026-09-27 本机范围）

**本机可试用**：真实 DeepSeek 三人对话、定向事件、行为分析与浏览器操作已实际跑通；
三个预置场景各三份真实样本已留存。最新命令、退出码、用量和故障边界见
[`state/reports/LIVE-TRIAL-2026-09-27.md`](../state/reports/LIVE-TRIAL-2026-09-27.md)。
后端 435 passed、可选上游 7 passed、前端 49 passed。

**正式质量验收仍未完成**：人工需按 [`docs/QUALITY_REVIEW.md`](QUALITY_REVIEW.md)
逐份判断九份真实样本；便利店第 2 份全员 `PASS`，应重点观察。浏览器自动重连、
长期运行、异机或公网部署仍未验证。行为分析曾出现分析对象偏题；加强对象标识后
一次真实复测已聚焦所选角色，但上游标签不完整，结果被标为 `DEGRADED`，
不能据此保证长期语义准确性。
