# M04 运行一致性修复（2026-09-28）

## 范围与状态

状态：已验收（R1～R7 通过）。修复行动原子提交、场景级连续点名计数、单步并发暂停三项缺陷。
不新增产品功能，修复核验阶段未提交或推送 Git，未发起真实供应商请求。后续人工于 2026-09-28 明确授权将本轮修复本地提交到 `main`。

跨模块影响（修改前登记）：新增存储迁移会更新 M01 的迁移版本断言；M02 的纯调度规则不变，M04 改为传入场景级计数；M06 共用预算仓储，需完整后端回归确认分析计数不受影响。公开接口及生成契约保持兼容。

## 修改文件与实现

| 文件 | 变更 |
|---|---|
| `backend/role_theater/storage/runtime_repo.py` | PENDING＋预算原子预留；成功结果整体提交；失败与未发送退款同事务；读取场景计数 |
| `backend/role_theater/storage/migrations/004_scene_scheduler.sql` | 新增场景点名计数；升级从 0 起算，旧角色计数清零 |
| `backend/role_theater/runtime/runner.py` | 使用场景计数、完整成功提交；单步／自动运行共用暂停收尾，停止优先 |
| `backend/tests/test_m04_runner.py` | 新增 11 个测试函数、参数展开后 17 个用例；原重启夹具取消重复手动预算递增 |
| `backend/tests/test_m01_storage.py` | 迁移顺序精确断言增加版本 004，原检查保留 |
| `docs/ARCHITECTURE.md`、`tasks/M04.md`、`state/STATUS.md`、`state/reports/M04.md`、本报告 | 同步事务边界、升级说明、A15～A18、状态与证据 |

生成契约没有变化；旧 `RoleCursor.consecutive_requested_priority` 字段继续保留兼容，调度不再读取。场景次数只在成功 SPEAK／PASS 提交时更新，失败不推进；正常轮转成功时清零，重启保持。

## 实际命令与结果

以下命令后端在 `backend/`、前端在 `frontend/` 执行，契约重建和差异检查在仓库根目录执行。

| 实际命令／检查 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest tests/test_m04_runner.py -k 'step_pause_during or runner_caps_requested or pending_and_budget or success_commit_failure' -p no:cacheprovider --tb=short`（修改产品代码前） | 1 | **7 failed**；真实触发 PAUSING 残留、第三次优先、PENDING／消息部分提交 |
| `.venv/bin/python -m pytest tests/test_m04_runner.py tests/test_m02_scheduler.py tests/test_m01_storage.py -p no:cacheprovider --tb=short`（初次修复） | 0 | **62 passed** |
| 同上（补齐升级、重启、PASS、错误原因、STOP、退款、无长事务检查后） | 0 | **72 passed** |
| 删除三个契约产物后 `bash scripts/export_contracts.sh`，前后 SHA-256 比较 | 0 | 三个文件重建成功，哈希完全一致（下节列出） |
| `PYTHONPATH=/private/tmp .venv/bin/python -m pytest -p no_net_plugin -p no:cacheprovider -r a --tb=short`（受限沙箱） | 1 | **446 passed、6 failed**；6 项均为本机假 HTTP 服务绑定回环端口时 `PermissionError` |
| 同一完整后端命令（自动审批允许本机回环绑定，仍阻断外网） | 0 | **452 passed**，无 skipped／xfail；1 条既有 Starlette 弃用警告 |
| `PYTHONPATH=/private/tmp .venv/bin/python -m pytest tests_optional/test_external_upstream.py -p no_net_plugin -p no:cacheprovider -r a --tb=short` | 0 | **7 passed**，使用假 SDK，不调用真实上游服务 |
| `pnpm run test` | 0 | **49 passed**，6 个测试文件 |
| `pnpm run build`（内含 `pnpm run typecheck`） | 0 | `tsc --noEmit` 与 Vite 构建通过 |
| Python AST 对照 HEAD 与当前两个测试文件 | 0 | 原 27＋8 个测试函数全部保留，既有测试断言数量未减少；无 skip／xfail；新增 11 个测试函数 |
| `git diff --check` | 0 | 无差异格式错误 |

外网阻断插件为 `/private/tmp/no_net_plugin.py`：pytest autouse fixture 拦截非回环 DNS 与 socket connect；本轮先读取并确认插件行为。完整测试没有自动发起真实模型请求。沙箱失败保留，未删除或跳过失败测试。

## 重建证据与复现

SHA-256：

- `backend/openapi.json`：`51c58d7341ca37382f274fd21965e0993c190ee15a9967b155e0844b375a6217`
- `frontend/src/api/generated/contract-summary.json`：`d434a041acd7b1618e0f3427d03d30a273be6abd7333c1be2b41c6ae96309883`
- `frontend/src/api/generated/schema.d.ts`：`86144e5bb613ed13ed97dcf79083638c77c29ab8137b5476453e9d52c4e3b990`

实际重建先将三个产物备份到临时目录，然后删除精确列出的文件，运行唯一生成脚本，比较前后哈希；失败时从备份恢复。所有数据库用例均使用 pytest 新建的临时 SQLite 文件。升级测试通过仅执行原 001～003 迁移构造旧库，写入消息／成功行动／游标／预算后，再执行 004；验证记录不变、旧计数清零、新场景计数为 0、重复迁移为空。

## 独立核验结论

| 编号 | 类型 | 实际证据与结论 |
|---|---|---|
| R1 | 重建 | 新临时数据库从零执行 001～004；三个契约产物删除后重建，哈希一致；通过 |
| R2 | 反例 | 旧代码 7 个失败用例，修复后通过；原测试与断言保留；完整回归无 skip／xfail；通过 |
| R3 | 原子性 | SQLite ABORT 故障注入预算、行动更新、游标、调度 INSERT／UPDATE；无部分消息、seq、成功状态或游标泄露；PASS 及未派发退款也整体回滚；通过 |
| R4 | 调度 | A→B→A 与 A→B→C 两条跨角色链第三次均轮转，之后点名重新有效；PASS 计数与普通 PASS 清零；新运行器／连接重开后保留次数；通过 |
| R5 | 控制交叉路径 | STEP 期间 PAUSE，SPEAK／PASS 成功后 PAUSED；失败保留 PROVIDER_ERROR；随后 STOP 则 ENDED，始终仅一次调用；既有自动暂停与事件排序回归通过 |
| R6 | 升级与环境边界 | 旧库升级记录保留；模型等待期间另一连接可立即 BEGIN IMMEDIATE；无配置／密钥／可选依赖实现变更，三态配置矩阵不新增要求，既有缺配置失败及可选依赖用例随完整回归通过 |
| R7 | 越界 | 仅修改登记的 M04 代码、迁移断言及文档；完整回归阻断外网；未查看、输出或修改密钥值、未改变生成接口、未修改上游、未新增功能；通过 |

M04 恢复为**已验收**。M05～M07 已有验收结论，本轮为维护修复，不自动新增功能。现有试用服务本轮未重启；已用旧库模拟升级验证迁移，实际已有会话数据库将在下次启动时由正常启动流程应用 004。

## 未验证项

真实模型、浏览器 EventSource 自动重连、人工对话质量、长时间运行及异机部署不由本轮 Mock 回归证明；保留既有未验证项。


## 2026-09-28 服务重启与人工测试入口

用户要求重启后测试。启动前 8002／5175 无监听，两个健康检查均连接失败；旧库仍在，无 PENDING 角色请求。先用 SQLite backup 保存到 `backend/backups/sceneweave-live-trial-before-restart-20260928-093413.db`（未提交的运行数据）。

实际启动命令（后端／前端各自目录）：

```bash
SCENEWEAVE_DATABASE_URL=sqlite:///./sceneweave-live-trial.db SCENEWEAVE_MODEL_PROVIDER=deepseek SCENEWEAVE_MODEL_FORCE_MOCK=false SCENEWEAVE_ANALYSIS_ENABLED=true .venv/bin/python -m uvicorn role_theater.main:app --host 127.0.0.1 --port 8002 --workers 1
SCENEWEAVE_DEV_API_PORT=8002 pnpm run dev --host 127.0.0.1 --port 5175 --strictPort
```

两项命令在允许本机回环绑定的执行环境中持续运行；后端日志确认 application startup complete，Vite ready。只读 HTTP／SQLite 核验脚本退出 0：

- 后端 `http://127.0.0.1:8002/api/health`、前端代理 `http://127.0.0.1:5175/api/health` 均 HTTP 200；`model_provider=deepseek`、`model_configured=true`、`model_credential_source=dotenv`、`analysis_enabled=true`。只输出安全状态字段。
- 前端入口 HTTP 200、HTML 包含 SceneWeave；场景列表 API HTTP 200。已请求在 Codex 浏览器面板打开测试入口（工具返回 queued）；也可直接访问上述前端链接。
- 真实旧库自动升级到迁移 `[1, 2, 3, 4]`；场景级计数为 0。重启前后均为 1 场景、3 消息、3 角色行动、2 分析记录，无丢失。
- 本轮重启未主动发起真实角色／分析调用；上述证据证明服务与记录可读取，后续人工交互质量仍待用户测试。
