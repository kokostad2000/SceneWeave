# SceneWeave 验收矩阵

来源：`PRD.md` 第 10 节「硬验收」+ 第 9 节各模块通过条件。
规则：**每条都必须指向实际执行过的测试与命令**；环境无法验证的项标为「未验证」，**不计入通过**。

- 生成日期：2026-09-26
- 本轮验证环境：Python 3.12.14、Node 24.2.0、pnpm 11.19.0、SQLite（标准库 `sqlite3`）
- 测试规模：后端 **347 passed**、前端 **48 passed**（均为确定性 Mock／假分析器，**不联网、不需要密钥**）
- **历史口径（2026-09-28 v0.1.0 收尾）**：后端 **459 passed**、可选上游假 SDK **7 passed**、
  前端 **49 passed**，类型检查与构建退出 0；后端阻断出站并允许本机回环假服务，无 skip／xfail。
  应用提交为 `48a63eb86c89b7332d7e3080402f0ac2b6cdaf1b`；459 = 原应用 452 + 本轮交付脚本 7。
  原始命令、环境失败、JUnit 和基线恢复证据见 [首版报告](../state/reports/FIRST-RELEASE-2026-09-28.md)。
  下文阶段性数字作为历史记录保留，不替代当前口径。
- **模块状态变更**：同期真实分析定位发现 Q1/Q2，M06 退回进行中；本文件 14 项硬验收保留工程层结论，
  不涵盖标签语义正确性，也不代表当前全部模块已验收。详见 [定位报告](../state/reports/ANALYSIS-LOCALIZATION-2026-09-28.md)。
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

## 8. 当前交付结论（2026-09-28 v0.1.0 本机范围）

**本机可试用**：真实 DeepSeek 三人对话、定向事件、行为分析与浏览器操作已实际跑通；
三个预置场景各三份真实样本已留存。最新命令、退出码、用量和故障边界见
[`state/reports/LIVE-TRIAL-2026-09-27.md`](../state/reports/LIVE-TRIAL-2026-09-27.md)。
当前后端 459 passed、可选上游 7 passed、前端 49 passed；迁移 001～004。
新增三场景各两会话真实观察：84 次角色请求成功、3 次合法 PASS、6 次分析 NORMAL，共 95,490 tokens。
原始样本与按影响排序反馈见 [USAGE_OBSERVATION.md](USAGE_OBSERVATION.md)。
两份室友分析的标签与目标安然的主动提议行为矛盾（F1/P1），**NORMAL 不证明语义正确**。

**正式质量验收仍未完成**：人工需按 [`docs/QUALITY_REVIEW.md`](QUALITY_REVIEW.md)
逐份判断九份真实样本；便利店第 2 份全员 `PASS`，应重点观察。浏览器自动重连、
长期运行、异机或公网部署仍未验证。行为分析曾出现分析对象偏题；加强对象标识后
一次真实复测已聚焦所选角色，但上游标签不完整，结果被标为 `DEGRADED`，
不能据此保证长期语义准确性。

## 9. 首版冻结与恢复

源码、依赖锁、迁移校验与限制冻结为 v0.1.0；归档、逐文件清单与恢复说明见 [BASELINE.md](BASELINE.md)。
本轮新增七项确定性测试涵盖 live 前置条件、PASS／空材料、UNKNOWN 不隐藏、定向可见性、归档篡改／路径穿越／禁止覆盖。
恢复目录的实际重建和数据库备份核对按首版报告记录；不把源码恢复等同于异机部署或人工验收。


## 5. 私聊增量 PC 核验（2026-09-28，当前工作区）

本次按任务书串行完成 M00～M07 增量，后端全量 538 passed（阻断真实出站，允许回环假服务），前端 53 passed，类型检查和构建退出 0。各模块原始数字保留为历史阶段记录，新增要求不从历史“已验收”继承。精确命令、失败过程与证据路径见 `state/reports/M07.md` 的 PC 增量段。

| 编号 | 实际证据／测试 | 本次结论 |
|---|---|---|
| PC-01 | test_action_contract、test_pc_parser：五字段、频道、200/201 码点、emoji、身份及对象正反例 | 工程通过 |
| PC-02 | test_pc_actual_requests_silence_old_reply_relay 捕获实际端口参数；HTTP viewer／菜单／计数；M05 第三方切换；真实请求快照再核对正文与 ID | 工程通过，有限真实样本通过 |
| PC-03 | test_pc_reference_channels：收到／自己的私聊、不同发送者、公开、未来、不存在 ID 及 # 别名 | 工程通过 |
| PC-04 | test_pc_four_actions_same_received_snapshot 四种结果在同一收到私聊的快照中均合法 | 工程通过 |
| PC-05 | PASS 不生成消息／通知、不反复唤醒；新定向事件后回复旧私聊；UI 沉默与失败分开 | 工程通过 |
| PC-06 | M02 及 PC runtime 转述新消息仍无原正文／ID；M06 实际假分析参数只含 B 的公开转述且作者 B | 工程通过 |
| PC-07 | 2/3/5/8 人全部无序对与双向发送共用 1/3/10/28 项；派发失败不留空会话；另一场标识不同 | 工程通过 |
| PC-08 | M02 候选与 PC runtime：只有收件人有新信息、发送者不自唤醒、PASS 后候选空暂停 | 工程通过 |
| PC-09 | M02 公私共享两次连续优先与第三人轮转；M04 故障／恢复计数；旧 004 计数 2 升级保留 | 工程通过 |
| PC-10 | M03 token／参数／上下文边界；M04 预算耗尽、已发送失败计数与单请求并发；全部私聊也走相同入口 | 工程通过 |
| PC-11 | 四种行动 × PAUSE/STOP 的真实受控在途 Mock、事件接受／生效与截止游标、幂等命令零新增请求 | 工程通过 |
| PC-12 | messages/scene_turns/role_cursors/scene_scheduler_state 故障回滚；快照预留故障零派发；M04 多消费者 SSE／UNKNOWN 保守恢复 | 工程通过；真实浏览器自动断线重连未验证 |
| PC-13 | M05 公共／私聊／全场、二级菜单、卸载重挂与第三方切换零 POST；实际浏览器双向同项、历史只读、刷新恢复 | 工程通过，代理浏览器检查通过 |
| PC-14 | 后端 generating／latest success／failure 独立字段；角色仅本人的行动；M05 四种中文标签、无猜测行动 | 工程通过 |
| PC-15 | M06 公私混选整体 BLOCKED、provider_attempts=0、预算不变；公开转述不附私聊；分析关闭聊天正常 | 工程通过 |
| PC-16 | 新库 001～006、旧 003 升级、004 SQLite backup 副本逐表原列不变、重复迁移、005 失败回滚；删除生成产物两次重建一致 | 工程通过 |
| PC-17 | M03/M04 原异常路径全部保留；缺配置 live 入口拒绝且没有数据库／供应商调用，无伪 PASS 或修复请求 | 工程通过 |
| PC-18 | Mock 独立样本、2/3/5/8 人容量 JSON、显式 live 8 次请求，6 私聊／5 回复、3 次第三方实际输入检查；用量模型与模板完整 | 工程与有限 live 通过；人工质量／真实长期容量未验证 |

真实样本：`state/reports/private-chat/live/20260928T150856368493Z/evidence.json`，正文／ID 再核对为同目录 `third-party-recheck.json`（只使用原请求，不再调用供应商）。8 次角色请求成功，0 失败，输入 6206、输出 606、合计 6812 tokens，最大单次 1034。角色目标利于观察私聊，但没有将模型结果强制改为 PRIVATE；此样本不证明自由行动质量或普遍回复率。

Mock 容量：2/3/5/8 人分别建 1/3/10/28 项会话，8 人 28 消息、34 次 Mock 请求及 1 次显式操作者新事件；无新信息时仍正常暂停。最多提示 1944 码点，8 人总耗时约 0.599 秒。Mock 用量 unknown，不据此推算真实网络时延或 token 费用。

原 M06 Q1／Q2 保持进行中；人工视觉与对话质量、真实长期容量、远端 CI、异机部署及原始资料缺口仍未验证。本次没有提交／推送，也没有升级既有试用库或重启原服务。

## 10. 双模式 P1 增量核验（2026-09-29）

G0范围门和G1工程门通过，历史PC条件保留。M00→M07分别追加核验，不继承旧模块通过结果。实际命令V1～V7、退出码、失败过程与边界见[双模式增量报告](../state/reports/CHANGE-dual-mode-P1.md)；完整后端XML709项、前端65项、类型与构建均通过，0 skip/xfail。

| Gate | 实际证据／检查 | 结论 |
|---|---|---|
| DM-P1-01 | test_dm_contracts合法／非法mode配置、旧入站默认；test_dm_storage同一API创建服务和mode筛选 | 通过 |
| DM-P1-02 | test_dm_storage模板CRUD／复制／快照／删除后历史保留；test_dm_context公开身份与私人唯一标记；旧006升级默认空 | 通过 |
| DM-P1-03 | test_dm_context空／给定初始观点；test_dm_model两模板经同一实际RecordingTransport接受四种行动；test_dm_runtime公共观点改变后原参与者快照相同 | 通过 |
| DM-P1-04 | test_dm_context过滤器输入与Prompt第三方标记；test_dm_runtime实际私聊输入、API／统计；dm-ui.test和browser第三方视角／菜单 | 通过 |
| DM-P1-05 | test_dm_model实际HTTP payload参数；test_dm_runtime逐条request_snapshot_json==端口请求；两模板版本及身份／越权反例 | 通过 |
| DM-P1-06 | test_dm_context相同原基线、mode两值的完整候选／选人／理由／计数比较；test_dm_runtime相同输入运行轨迹／恢复比较；Scheduler diff为空 | 通过 |
| DM-P1-07 | test_dm_runtime复跑STEP、在途暂停／结束、事件、预算、幂等、提交故障、UNKNOWN恢复、网络不持锁；双SSE消费者及原M04在途串行测试 | 通过 |
| DM-P1-08 | test_dm_storage旧006副本原所有列／快照逐项比较、007失败回滚／重复迁移／完整性；原003／004升级断言保留 | 通过 |
| DM-P1-09 | test_dm_storage模式修改405、两模式配置／public_profile／参与者配置关闭重开相同、模板修改不影响本场；原请求字串不重写 | 通过 |
| DM-P1-10 | dm-ui.test两入口／必填议题／null观点／提交payload及zero POST commands；IAB实际创建与私人字段标识 | 通过 |
| DM-P1-11 | dm-ui.test共用两模式ChatView、HistoryView三种筛选／刷新／缓存；IAB三份历史全量、单模式回看；导航后请求仍7 | 通过 |
| DM-P1-12 | test_dm_runtime两模式复跑原私聊隔离；dm-ui、m05-ui保留待生效事件频道反例、隐藏行动／菜单／PASS和失败分开 | 通过 |
| DM-P1-13 | test_dm_analysis两模式同一假分析器抓请求，混选私聊／未知PASS序号整组BLOCKED且0；公开转述只新公开材料；关闭／缺包模拟不影响互动；m06-analysis两模式推荐不限制手动选材 | 通过 |
| DM-P1-14 | test_dm_runtime按合法可见记录核对公／私／回复／PASS／失败计数与第三方；test_dm_analysis前后snapshot、游标、优先计数完全相同；不反馈运行 | 通过 |
| DM-P1-15 | test_dm_contracts两模式2／3／5／8与1／9反例、Unicode字段边界；test_dm_delivery两模式实际人数／200emoji；dm_model201／token，dm_context32000／32001，dm_runtime预算；原dotenv矩阵和缺依赖测试 | 通过 |
| DM-P1-16 | V1从零重建哈希相同；V2完整709／XML无skip；V3前端65、tsc／build0；V4范围diff；V6晚失败仍退出4；原WIP保留，无放宽断言／运行分叉／高级分析 | 通过 |

G2有限使用观察：V7显式--live，普通simulation3PASS、普通discussion3PASS，独立明确私聊目标discussion5PRIVATE／1PASS（4条关联回复）；共12成功请求，12,272 tokens，单次最大1307，预算和输入快照相同，停止后无在途。实际输入／输出见真实汇总（原始记录仅本地留存）及该汇总指向的独立样本。引导样本3组第三方实际输入无原私聊正文、ID或会话ID。

G2已执行不等于人工质量通过。普通两模式本次没有产生公开对话或观点演变；不为补覆盖强迫行动或重试。人工UX／行为质量、真实长期容量、真实讨论行为分析、自动重连、异机部署及远端CI保持未验证；M06 Q1/Q2未关闭。原服务与试用库未切换；本轮无commit/push。


## 人物／本场设定分离 SR 核验（2026-09-29）

本增量工程通过，六次有限真实观察已执行。本机 5175／8002 已升级到 sr.p1.1 并启用既有真实 API 配置。实际命令、退出码、失败过程、未验证项见 [SR 实施报告](../state/reports/CHANGE-scene-role-profile.md)。历史 PC／DM 证据保留，不继承新增核验。

| 编号 | 本次证据 | 结论 |
|---|---|---|
| SR-01 | sr_contracts 严格版本／混字段／null；sr_storage 两模式五字段空与旧复制；sr-ui 明确版本 2 | 工程通过 |
| SR-02 | sr_storage 场景间独立 ID／快照、空值／目录删除；sr_runtime 目录变更不改本场、应用重开 | 工程通过 |
| SR-03 | sr_storage 同名旧内容不能覆盖预设；仅补齐本场人物、名称条目；真实 preset-simulation | 工程通过，有限真实通过 |
| SR-04 | sr_context 公开全员／私有唯一标记；PC／DM 公私聊反例；实际 Mock 角色上下文和 UI 隔离 | 工程通过 |
| SR-05 | sr_runtime 两模式实际派发 == 保存 JSON；新旧模板标识；真实两个样本无旧文字 | 工程通过，有限真实通过 |
| SR-06 | sr_storage 全量修改／讨论清空、锁定与事务竞争 409；sr_runtime 幂等零增调用；Mock 实际编辑／锁定 | 工程通过 |
| SR-07 | 008 故障回滚／重复、旧 006／007 原字段；真实库副本与服务升级 12 业务表旧列逐项不变 | 工程通过 |
| SR-08 | sr-ui 目录仅名称、完整五字段、两模式空值／v2、旧／锁定／只读；实际 Mock 与真实服务表单 | 工程通过 |
| SR-09 | sr_runtime 两模式实际应用关闭重开，配置／保存请求完全相同、重放零调用；旧版提示组件 | 工程通过 |
| SR-10 | 开工源 SHA：Scheduler／模型适配／状态机／分析未改；Runner 仅一行接线；sr_context 调度比较；v2 复跑 16 原运行反例＋全量 SSE／PC／DM | 工程通过 |
| SR-11 | 两模式 2／3／5／8、Unicode／200／32000、配置矩阵；可选依赖 11；空生成再导出无漂移 | 工程通过 |
| SR-12 | 最终后端 768、可选 11、前端 73；tsc／空构建 0；实际浏览器及真实 6 次分别取证；失败 XML／无删例／skip | 工程通过，质量限制保留 |

真实 empty-discussion 3 PASS、preset-simulation 3 SPEAK；共 5950 tokens，单次最大 1069，快照／预算一致，两份样本均 ENDED。见 真实汇总（原始记录仅本地留存）。空设定样本没有产生讨论，不关闭对话丰富度、观点演变或人工质量验收。原 M06 Q1/Q2、长期容量、真实讨论分析、自动重连、异机部署／远端 CI 保持未验证／未关闭。试用库升级前一致备份和服务回执已保留，启动新增模型请求 0，未 commit／push。


## 自由续聊 FC（2026-09-29）

本表核验PRD 10.4的新需求，历史PC／DM／SR结果保留当时规则，不自动覆盖新策略。旧行为测试显式策略1，新策略单列；M06仅隔离增量通过，原Q1/Q2仍进行中。

| 检查 | 本轮实际证据 | 状态 |
|---|---|---|
| FC-01/02 | test_fc_contracts；200/201、1000/1001 Unicode、严格版本值及导出 | 工程通过 |
| FC-03 | test_fc_storage、迁移009回滚／重复；真实试用副本及原列hash | 工程通过 |
| FC-04/05 | test_fc_scheduler/runtime；两Mode、2/3/5/8人、同钟轮转、无新消息、逐角色PASS／可见信息、再次继续 | 工程通过 |
| FC-06 | 单次目标优先、连续2次上限；私聊前后第三方Prompt／HTTP计数相同 | 工程通过 |
| FC-07 | test_fc_model；两策略额度、无scope边界、空／JSON／超长／引用／截断、Mock一致 | 工程通过 |
| FC-08/09 | test_fc_runtime及M04；命令预写与故障重放、原子回滚、UNKNOWN、孤儿活动状态、待接受事件恢复、预算／上下文 | 工程通过 |
| FC-10 | fc-ui、test_fc_ui_api、实际隔离Mock浏览器：997码点显示／转义、暂停继续、本人用量 | 工程通过；人工质量未验证 |
| FC-11 | test_fc_analysis＋原M06；四条1000因注释超限，三条完整送出；私聊拒绝、只读／无请求拦截 | 隔离增量通过；Q1/Q2未关闭 |
| FC-12 | 851 backend、11 optional、78 frontend、类型／空构建／契约空重建；真实两Mode×两策略共20请求、27371 tokens | 工程及有限观察通过；自然度普遍改善未验证 |

完整命令与汇总见 [实施报告](../state/reports/CHANGE-free-chat.md)；XML、失败证据、原始供应商输入/输出及服务备份仅本机留存，GitHub不附运行产物。没有真实私聊样本或长期容量结论；不把单个353码点输出当作长篇论证质量验收。旧场景保留策略1，新建默认策略2。
