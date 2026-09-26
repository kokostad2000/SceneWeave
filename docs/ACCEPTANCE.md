# SceneWeave 验收矩阵

来源：`PRD.md` 第 10 节「硬验收」+ 第 9 节各模块通过条件。
规则：**每条都必须指向实际执行过的测试与命令**；环境无法验证的项标为「未验证」，**不计入通过**。

- 生成日期：2026-09-26
- 本轮验证环境：Python 3.12.14、Node 24.2.0、pnpm 11.19.0、SQLite（标准库 `sqlite3`）
- 测试规模：后端 **347 passed**、前端 **48 passed**（均为确定性 Mock／假分析器，**不联网、不需要密钥**）

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

## 4. 真实模型验收（**未验证**）

| 项目 | 状态 | 障碍 |
|---|---|---|
| 三人真实聊天（PRD 10 要求） | **未验证** | 无模型密钥，且本轮明确禁止真实 API 联调 |
| 一次定向事件的真实效果 | **未验证** | 同上 |
| 一次真实行为分析（外部仓库 `behavior-psychology-v2.0`） | **未验证** | 外部仓库不可访问、未安装；模块路径与字段名待联调核对（`tasks/M06.md` U-M06-1/2） |
| 聊天质量人工观察（PRD 10：预置三个场景各三次） | **未验证（样本已就绪）** | ① **人工观察**未做；② 三个预置场景已按人工裁决补齐（B6），并已用确定性 Mock 各运行三次留样：`state/reports/quality-observation-mock.json`（9 次运行，`leaks_other_private_fact=false`、`allows_silence=true`）。Mock 样本**不代表真实模型质量** |
| `live_smoke.py` 的真实调用路径 | **未验证** | 只验证了三条**拒绝路径**（无开关 → 退出码 2；无 `--confirm-spend` → 2；无密钥 → 3） |
| `live_integration.py`（真实三人聊天 + 定向事件 + 分析） | **未验证** | 脚本已实现并验证拒绝路径（2／2／3）；**缺 `SCENEWEAVE_MODEL_API_KEY`**，未发起真实调用 |
| Chat Completions 接口契约（字段名、thinking 开关、用量字段） | **已由官方文档核对** | 见 `docs/SOURCES.md` §1.1；结论：`thinking: {"type": "disabled"}`、`response_format` 需同时指示 JSON、异常 `finish_reason` 已全部显式分类 |

运行真实冒烟的方式（会产生真实费用，**不在普通 CI 执行**）：

```bash
cd backend
SCENEWEAVE_MODEL_API_KEY=... uv run python scripts/live_smoke.py --live --confirm-spend
```

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

| 编号 | 项目 | 障碍 |
|---|---|---|
| U1 | 真实 DeepSeek 联调（三人聊天、定向事件） | 无密钥；本轮禁止真实调用 |
| U2／U3 | 外部分析仓库安装、受控客户端兼容性、真实分析质量 | 仓库不可访问（`bd1e8fa…`） |
| U-M03-1 | `thinking` 字段的确切名称与取值 | 需真实联调核对 |
| U-M04-1/2/3 | 多标签并发、长时间运行、真实网络下 SSE 时序 | 需人工与真实环境 |
| U-M05-1/2 | 人工视觉验收、真实浏览器 EventSource 重连 | 本环境无浏览器自动化 |
| U-M06-1/2/4 | 外部模块路径／字段名、干净虚拟环境安装验证 | 仓库不可访问 |
| U-M07-1 | 聊天质量人工观察 | 需人工；且 PRD 只定义 1 个预置场景（B6） |
| U8 | 远端 CI | 本轮为本地基线；是否接入由人工决定 |
| U7 | 真实部署（服务未部署到任何环境） | 本轮只在本机验证 |

## 7. 需求矛盾与遗留缺口

| 编号 | 事项 | 处置 |
|---|---|---|
| B1 | `docs/SOURCES.md` 缺失（PRD 的 [S1]～[S9] 原始地址不在 PRD 内） | 保持**遗留缺口**：不编造引用；需人工提供地址或授权联网检索 |
| B4 | `docs/ACCEPTANCE.md` 缺失 | **本文件已建立**（M07），硬验收 14 项逐条对照完成 |
| B6 | PRD 第 10 节要求「预置三个场景各运行三次」，但第 3.1 节只定义了**一个**预置场景 | **人工裁决：补两个预置场景**（不改 PRD）。已新增 `convenience_store`／`campsite`，各 3 名角色；角色与情境为项目自撰内容。三个场景各运行三次的 Mock 样本已留档 |
| B7 | PRD 第 10 节「预置三个场景」与第 1.2 节「预置室友模板」的数量口径不一致 | 同上，登记为同一矛盾的另一种表述 |

## 8. 交付结论

**当前状态：未达到「可试用」。**

原因（缺项，与 `docs/RELEASE.md` 一致）：

1. **真实模型未接通**：没有密钥，三人真实聊天、定向事件、真实行为分析均未验证；
2. **服务未部署**：只在本机以 `127.0.0.1` 运行过；
3. **外部分析仓库未安装**：分析能力默认 `DISABLED`，真实分析路径未验证；
4. **人工观察未做**：聊天质量与界面视觉验收需人工。

**可以确认的部分**：工程、契约、角色与场景（含 3 个预置场景）、可见性与调度、模型适配、运行与事件、操作界面、行为分析（关闭路径 + 假分析器路径）均已实现并通过确定性验收；硬验收 14 项中的 14 项都有可执行的 Mock 证据；备份／恢复、崩溃恢复、迁移幂等均已实际执行。

→ 达到「可试用」所需的最小补充：配置有效密钥并把 `live_smoke.py --live --confirm-spend` 与 `docs/RELEASE.md` §6 的真实调用样例跑通（或明确接受「仅 Mock 演示」的定位），再补一次人工观察。
