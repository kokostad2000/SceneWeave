# 参数变更报告：每场角色请求上限默认 24 → 200

- 触发：人工指示「限额可以改的高一些，给 200 轮对话的限额，其他不变，还是要人工选择是否进入下一步或者下一轮对话」（2026-09-26）。
- 性质：**配置默认值变更**（契约常量 + 前端默认值 + 文档），不新增功能、不改状态机、不改调度与控制方式。
- 相关模块：M00（`Budget` 常量）、M01（场景创建预算）、M04（预算计数与控制）、M05（配置页默认值）。

## 1. 口径确认（人工可复核）

- 本项目预算的单位是**角色请求**：一次角色行动 = 一次模型调用 = 一条发言（或一次 PASS），
  即界面上「单步」一次、`scene_turns` 一行。
- 因此「200 轮对话的限额」按 **`max_role_requests = 200`** 落实；`max_analysis_requests` 保持 4。
- **待人工确认的口径**：若「一轮」指的是「三名角色各说一次」，则 200 轮需要约 600 次角色请求，
  应改为 600 并同步上调 `MAX_SCENE_REQUEST_LIMIT`。本次按前者实现，改动可逆。
- 「其他不变」按字面执行：`MIN_SCENE_REQUEST_LIMIT..MAX_SCENE_REQUEST_LIMIT = 1..200` 不变，
  **单步仍然一次调用后停下等人工决定**，自动运行、暂停、继续、结束的语义一律未动。

## 2. 改动文件

| 文件 | 改动 |
|---|---|
| `backend/role_theater/contracts/limits.py` | `MAX_ROLE_REQUESTS_PER_SCENE` 24 → **200**（并注明人工裁决与出处）；`MAX_ANALYSIS_REQUESTS_PER_SCENE` 仍为 4；可配置范围仍为 [1, 200] |
| `backend/role_theater/contracts/api.py` | 默认值导出注释「默认 24／4」→「默认 200／4」 |
| `frontend/src/views/ConfigView.tsx` | 配置页两个预算输入框的初值改为读取 `budgets.max_role_requests_per_scene`／`max_analysis_requests_per_scene`（来自 `contract-summary.json`），**前端不再手写这两个数字** |
| `backend/openapi.json`、`frontend/src/api/generated/schema.d.ts`、`contract-summary.json` | 由 `scripts/export_contracts.sh` 重新生成（`@default 24` → `200`，`budgets.max_role_requests_per_scene: 200`） |
| `docs/ARCHITECTURE.md` | `Budget` 行更新为默认 200，并写明可下调范围与「控制方式不变」 |
| `tasks/M00.md`、`tasks/M01.md`、`tasks/M04.md` | 预算默认值更新为 200，并标注这是人工裁决（PRD 初值为 24）；M04 补一句控制方式不变 |
| `state/STATUS.md` | 测试数字与决策记录（§4 B7）；PRD 原文**未改** |

`PRD.md` 保持原样（需求唯一来源，第 5.3 节仍写默认 24）；本次按 B6 的同一惯例，把人工裁决
记录在 `STATUS.md` §4 与本报告中，而不是改写 PRD。

## 3. 实际执行的命令与结果

| # | 命令（工作目录） | 退出码 | 结果 |
|---|---|---|---|
| 1 | `UV_CACHE_DIR=.cache/uv uv run --directory backend python scripts/export_contracts.py`（根） | 0 | 重写 `backend/openapi.json`、`contract-summary.json` |
| 2 | `pnpm run gen:api`（`frontend/`） | 0 | `schema.d.ts` 的 `@default` 更新为 200 |
| 3 | `.venv/bin/python -m pytest`（`backend/`） | 0 | **423 passed** |
| 4 | `PYTHONPATH=/private/tmp .venv/bin/python -m pytest -p no_net_plugin`（`backend/`） | 0 | 阻断出站网络后仍 **423 passed** |
| 5 | `pnpm run typecheck`（`frontend/`） | 0 | `tsc --noEmit` 无输出 |
| 6 | `pnpm test`（`frontend/`） | 0 | **49 passed**（新增 1 项：配置页预算默认值取自契约并原样提交） |
| 7 | `pnpm run build`（`frontend/`） | 0 | `vite build` 成功 |

## 4. 核验（按 AGENTS.md 5.1）

- **V1 重建检查**：契约产物由脚本从源码重建；`backend/tests/test_contract_export.py` 漂移检测与
  `frontend/tests/generated-schema.test.ts` 均通过，证明前端类型与后端契约一致。
- **V2 反例检查**：受影响断言全部**按新值收紧为字面量 200**，没有改用常量比较、没有放宽：
  `test_scene_contract.py::test_budget_defaults_and_bounds`、`test_health.py`（`/api/contracts/summary`）、
  `test_m01_scenes.py::test_budget_defaults_match_the_contract`、`test_m04_api.py`（summary 的 `max_role_requests`）、
  `frontend/tests/contracts.test.ts`（契约摘要预算）。越界用例（0／10000 → 422、
  `Budget(max_role_requests=0)` 与 `=10000` 抛错）保持原样并继续通过。
- **V3 越界检查**：无新增依赖、无网络调用（第 4 行命令证明）、未改调度与状态机、
  未提前实现后续模块功能；既有预算耗尽用例仍用显式小额上限（如 `max_role_requests=2`）驱动，不依赖默认值。
- **V4 控制方式回归**：`test_m04_runner.py` 的「单步只执行一次调用并暂停」「自动运行到预算耗尽才结束」
  等既有用例全部通过，证明提高上限没有改变「人工决定是否进入下一步／下一轮」的行为。
- 未验证项：**未发起真实模型调用**验证 200 次预算下的实际表现（属于额度花费，需人工决定）。

## 5. 遗留

- 「一轮」口径待人工确认：若指「所有角色各说一次」，需把上限改成角色数 × 200，并同步
  `MAX_SCENE_REQUEST_LIMIT`；当前实现取「一次角色请求 = 一轮」。
- 提高上限只影响**上限**，不改变花费速度：单步仍是一次调用；自动运行仍按原规则连续调用直到
  暂停条件（无新信息／预算耗尽／人工暂停）。真实花费取决于人工点击与自动运行的暂停时机。
- **生效条件**：与引用修复同属代码改动，需要重启后端。2026-09-27 00:25 已重启（人工要求），
  线上 `/api/contracts/summary` 由 `24` 变为 **`200`**；重启与验证全过程见
  `state/reports/FIX-reply-reference.md` §8。旧场景的预算在创建时已落库，不会因重启而改变。
