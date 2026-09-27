# 缺陷修复报告：引用标识不可用导致真实调用 4/8 失败

- 触发：人工要求「看一下日志，有几次 API 调用失败原因查一下」，随后**人工明确授权**「你来改吧」。
- 性质：**跨模块缺陷修复**（M02 提示词 + M03 解析 + M04 范围构建 + 契约产物），不是新模块，不改 PRD 需求。
- 修复日期：2026-09-26。基线版本：`dc047e2 SceneWeave 首版（M00–M07）`。
- 相关模块报告：`state/reports/M02.md`、`M03.md`、`M04.md`。

## 1. 现象与证据（修复前）

真实调用日志不在文件里：`/private/tmp/*uvicorn*.log` 只覆盖 21:01 之前的离线验证，无模型调用。
真实调用的记录在 `backend/sceneweave.db` 的 `scene_turns`（每次调用的模型名、provider 请求 ID、
用量、耗时、`failure_kind`、`failure_detail`）。

| 本地时间(UTC+8) | 角色 | 入参截止 seq | provider 请求 ID | 耗时 | 入/出 tokens | failure_kind | failure_detail |
|---|---|---|---|---|---|---|---|
| 23:42:11 | 安然 | — | 09b1ab11… | 1133ms | 387/92 | — | 成功 |
| 23:42:12 | 许川 | 1 | 79ddc6cc… | 634ms | 443/50 | `SCHEMA_INVALID` | `reply_to_message_id` 应为 string，实际 int `1` |
| 23:43:30 | 许川 | — | d176d965… | 892ms | 443/50 | — | 成功 |
| 23:43:31 | 陈禾 | — | 6a43a31e… | 1022ms | 474/52 | — | 成功 |
| 23:43:32 | 安然 | 3 | e78ed843… | 1052ms | 506/89 | `SCHEMA_INVALID` | int `3` |
| 23:44:38 | 安然 | — | af1cb7a5… | 935ms | 506/95 | — | 成功 |
| 23:44:39 | 许川 | 4 | 1280e52e… | 692ms | 569/46 | `SCHEMA_INVALID` | int `4` |
| 23:47:31 | 许川 | 4 | 3d19b78c… | 723ms | 569/47 | `SCHEMA_INVALID` | int `4` |

- 8 次真实调用（`sent=1`、`budget_consumed=1`）：4 成功、**4 失败**，失败率 50%；4 次失败请求照常计费，
  场景预算 8/24，其中 4 次被浪费。
- 4 次成功调用的 `reply_to_message_id` 全部为 `null`——**只要模型显式引用某条发言就必然失败**。
- 每次失败都把场景置为 `PAUSED / PROVIDER_ERROR`（符合 PRD 5.3），`scene_commands` 里能看到人工重启 4 次
  （`start-ee930f35`／`ba630f89`／`00447ebc`／`128a252c`）。

## 2. 根因

用应用自身装配重建当时实际发出的提示词（`SceneRunner.snapshot` + `ContextBuilder`）后确认：

1. 时间线只渲染 `[#序号]`，**从不输出 `msg_…`**（`role_theater/context/builder.py`），
   而 `TimelineItem` 连 `message_id` 字段都没有；名册同样只有名字，没有 `agt_…`。
2. 输出格式区却要求「`reply_to_message_id` 只能指向……的消息 ID」「`requested_speaker_id` 只能指向……
   的角色 ID」——模型**没有任何合法 ID 可抄**，只能把 `#` 后面的序号当 ID 回传。
3. `ActionDraft.reply_to_message_id` 是 `MessageId`（字符串），pydantic v2 不做 int→str 强制转换，
   于是 `SCHEMA_INVALID`。
4. 引用范围校验比较的是真实消息 ID（`msg_…`），所以即使模型回字符串 `"4"`，也只会从
   `SCHEMA_INVALID` 变成 `REFERENCE_INVALID`——按修复前的提示词，引用路径**在任何写法下都不可满足**。
5. `requested_speaker_id` 是同一类隐患（名册不暴露 `agent_id`），本轮 4 次成功恰好都没用该字段。

测试缺口：引用校验用例全部手写 scope（`allowed_message_ids=["msg-1"]`），
没有一条「ContextBuilder 出题 → 模型按题面作答 → 解析通过」的闭环用例，因此该缺陷在 407 项测试全绿的情况下漏出。

## 3. 修复内容

| 文件 | 改动 |
|---|---|
| `backend/role_theater/context/models.py` | `TimelineItem` 新增 `message_id`，`from_message` 由 `Message.message_id` 填充 |
| `backend/role_theater/context/builder.py` | 时间线渲染为 `[#3 \| msg_…]`；名册渲染为 `名字（agt_…）`；输出格式区说明两种引用写法；`PROMPT_TEMPLATE_ID` 由 `role_action@m02` 升为 `role_action@m02.1`（提示词内容已变，历史 turn 可区分） |
| `backend/role_theater/contracts/model.py` | `ReferenceScope` 新增 `allowed_message_seqs: dict[int, MessageId]`（与 `allowed_message_ids` 同一批发言的序号别名视图） |
| `backend/role_theater/ports/action_parser.py` | 新增 `resolve_message_alias`：把 `3`／`"3"`／`"#3"`／`"[#3]"` 确定性换算成真实消息 ID；只在给定序号表时生效，越界序号仍按 `REFERENCE_INVALID` 报告，`bool` 不当作序号。其余字段一律不改写 |
| `backend/role_theater/runtime/runner.py` | 构建 `ReferenceScope` 时同时写入消息 ID 与序号别名（仍然只包含 `seq <= based_on_seq` 的已提交发言） |
| `backend/openapi.json`、`frontend/src/api/generated/schema.d.ts` | 由 `scripts/export_contracts.sh` 重新生成（`contract-summary.json` 无变化） |

契约语义：别名解析是**查表换算**，不放宽任何判定——序号不在允许范围内、ID 不在允许范围内，
仍然是失败；不追加任何修复调用（符合 PRD 4.2、5.3）。

## 4. 实际执行的命令与结果

| # | 命令（工作目录） | 退出码 | 结果 |
|---|---|---|---|
| 1 | `.venv/bin/python -m pytest`（`backend/`） | 0 | **423 passed**, 1 warning（修复前基线 407；新增 16 项） |
| 2 | `pnpm run gen:api`（`frontend/`） | 0 | 由 `backend/openapi.json` 重新生成 `schema.d.ts` |
| 3 | `UV_CACHE_DIR=.cache/uv uv run --directory backend python scripts/export_contracts.py`（根） | 0 | 重写 `backend/openapi.json`、`contract-summary.json` |
| 4 | `pnpm run typecheck`（`frontend/`） | 0 | `tsc --noEmit` 无输出 |
| 5 | `pnpm test`（`frontend/`） | 0 | **48 passed**（6 个文件） |
| 6 | `pnpm run build`（`frontend/`） | 0 | `vite build` 成功（dist 为 gitignore 产物） |
| 7 | 真实库回放（见 §5） | 0 | 旧失败样本 `4`／`"4"`／`"#4"`／真实 ID 全部解析为同一条消息 |
| 8 | `PYTHONPATH=/private/tmp .venv/bin/python -m pytest -p no_net_plugin`（`backend/`） | 0 | 阻断出站 DNS／连接后仍 **423 passed**（沿用 M00 起的核验插件） |

说明：`scripts/export_contracts.sh` 直接运行会因沙箱不允许写 `~/.cache/uv` 而失败（`os error 1`），
因此第 3 步显式指定仓库内缓存目录 `UV_CACHE_DIR=.cache/uv`；这是环境限制，不是代码问题。

## 5. 核验（按 AGENTS.md 5.1）

- **V1 重建检查**：删除 `backend/openapi.json`、`frontend/src/api/generated/schema.d.ts`、`contract-summary.json`
  后从零重建，三个文件 sha256 与重建前**完全一致**（`294c02e8…`／`89fc1649…`／`f0931582…`）；
  后端测试含 `test_contract_export.py` 漂移检测，423 项全绿。
- **V2 反例检查（关键）**：把 5 个源码文件临时回退到 `HEAD`（测试保留），新增回归用例**全部失败**：
  - `test_m04_runner.py::test_reply_reference_taken_from_the_prompt_is_committed[id|seq|#{seq}|[#{seq}]]` → 4 项 FAILED
  - `test_m02_context.py::test_prompt_exposes_*`／`test_message_ids_of_invisible_items_never_leak` → 3 项 FAILED
  - `test_m03_model_adapter.py::test_seq_alias_*`／`test_boolean_is_never_treated_as_a_seq_alias` → 7 项 FAILED
  随后从备份恢复源码并复跑，423 项全绿。证明新用例真的盯住了该缺陷，不是恒真断言。
- **V3 越界检查**：全程未联网、未使用真实密钥（真实调用是人工此前在应用里发起的，本轮只读库、不重放）；
  `-p no_net_plugin` 阻断出站 DNS／连接后仍 **423 passed**（命令见 §4 第 8 行）；未新增 `skip`／`xfail`；
  未放宽既有断言（唯一改动的既有断言是 2 处 `prompt_template_id` 期望值随模板号升级，
  以及 1 处 `TimelineItem` 字段集合新增 `message_id`）。
- **V4 真实样本回放**：读真实库 `sceneweave.db` 的既有发言（只读）重建提示词与 `ReferenceScope`，
  用旧失败样本回放：`ref=4`／`"4"`／`"#4"`／`msg_520cccad…` 全部解析为 `msg_520cccad5e0041ffac440bdee1a8f708`。
- 未验证项：**未发起新的真实模型调用**。真实模型是否稳定照新提示词回写 ID／序号，需要一次显式 `live`
  冒烟（`backend/scripts/live_smoke.py --live --confirm-spend`）或人工在界面里重跑一场才能观察，本轮不花费额度。

## 6. 回归用例清单（新增 16 项）

| 位置 | 用例 | 盯住什么 |
|---|---|---|
| `backend/tests/test_m02_context.py` | `test_prompt_exposes_the_message_id_of_every_visible_message` | 可见发言的 `message_id` 必须出现在提示词里 |
| | `test_prompt_exposes_role_ids_so_speaker_requests_are_reachable` | 名册必须给出 `agent_id` |
| | `test_message_ids_of_invisible_items_never_leak` | 不可见内容与其 ID 都不得泄漏；事件不伪造可引用 ID |
| `backend/tests/test_m03_model_adapter.py` | `test_seq_alias_resolves_to_the_real_message_id[5 种写法]` | `3`／`"3"`／`"#3"`／`"[#3]"`／带空白 |
| | `test_seq_alias_out_of_range_is_an_invalid_reference_not_a_type_error` | 越界序号 → `REFERENCE_INVALID` |
| | `test_real_message_id_still_wins_over_alias_lookup` | 真实 ID 不被改写 |
| | `test_seq_alias_without_a_seq_table_keeps_the_strict_type_error` | 无序号表时不放宽 |
| | `test_boolean_is_never_treated_as_a_seq_alias` | `true` 不是序号 |
| `backend/tests/test_m04_runner.py` | `test_reply_reference_taken_from_the_prompt_is_committed[4 种写法]` | **端到端闭环**：真实 `DeepSeekModelClient` + MockTransport 读提示词作答 → 解析 → 落盘 `reply_to_message_id` |

## 7. 遗留与后续建议

- **待人工观察**：新提示词下真实模型的实际回写形式（是否还会回序号、是否开始用 `requested_speaker_id`）。
  建议下一场真实会话后复查 `scene_turns`（`SCHEMA_INVALID` 计数应为 0）。
- **未做**：`requested_speaker_id` 目前只暴露 `agt_…` ID，未接受角色名别名（同名歧义风险）。
  若真实模型习惯回名字，再按同一「查表换算」思路评估。
- **可观测性缺口（未修）**：`ModelActionResponse.raw_content` 并不落库，`scene_turns` 只有校验报错；
  真出问题时拿不到模型原始 JSON。是否把原始输出纳入诊断记录，属于产品边界取舍，需人工决定（PRD 未要求）。

## 8. 生效与重启验证（2026-09-27 00:25，人工要求「重启后端」）

**本修复是 Python 代码改动，必须重启后端进程才生效**：改动前的进程（PID 20073，无 `--reload`）在
00:14 与 00:15 的两次真实调用中仍然复现了同一个缺陷（`scene_turns` 两条 `SCHEMA_INVALID`，`input_value=1` int），
线上 `/api/contracts/summary` 仍返回 `24`、角色视角提示词仍是 `role_action@m02`——由此确认是进程陈旧，而非网络或模型问题。

重启步骤与验证（全部只读）：

| 步骤 | 命令／检查 | 结果 |
|---|---|---|
| 1 | 确认无在途请求后 `kill 20073` | `/state` 返回 `in_flight=false`；端口 8000 释放 |
| 2 | `cd backend && exec .venv/bin/python -m uvicorn role_theater.main:app --host 127.0.0.1 --port 8000`（托管后台作业 `bash-511`） | 新进程 PID 65746 监听 127.0.0.1:8000 |
| 3 | `GET /api/health` | `status=ok`、`model_configured=true`、`model_provider=deepseek` |
| 4 | `GET /api/contracts/summary` | `max_role_requests_per_scene=200`、`max_analysis_requests_per_scene=4`（旧进程为 24／4） |
| 5 | `GET /api/scenes/{id}/agents/{aid}/viewpoint` | `prompt_template_id=role_action@m02.1`；名册带 `agt_…`；时间线为 `[#1 \| msg_b3dd09c1…]` |
| 6 | `GET /api/scenes` 与各场景 `/state` | 4 个场景完好；运行中场景仍为 `PAUSED/PROVIDER_ERROR`、3/200、`last_seq=1`（重启未改动任何记录） |

重启未触发任何恢复动作（`scene_turns` 无 `PENDING` 行），`recover_after_restart()` 没有标记 `UNKNOWN`、没有改动预算。
**注意**：该后端是本会话托管的后台作业；若要长期运行，请在自有终端执行步骤 2 的同一条命令。

## 9. 真实模型验证结果（2026-09-27 00:21–00:22，人工在界面上跑的一场）

重启后人工在 `scn_48c301dd89074c978aa3843f2b772043` 上连续运行，结果（数据来自 `scene_turns` 与 `messages`）：

| 指标 | 修复前（旧进程） | 修复后（重启后这一场） |
|---|---|---|
| 调用次数 / 失败次数 | 8 / **4**（全为 `SCHEMA_INVALID`） | 22 / **0** |
| 落盘消息数 | 4 | 22 |
| 其中带 `reply_to_message_id` | **0** | **21** |
| 其中带 `requested_speaker_id` | 0 | 2 |
| 单次耗时 | 634–1133ms | 590–1463ms（均值 898ms） |

结论：**提示词暴露 ID + 序号别名解析在真实模型上生效**——模型开始大量使用 `reply_to_message_id`，且全部通过引用校验；
原先「只要显式引用就必然失败」的现象消失。§7 的「待人工观察」项由此关闭；仍保留的观察点是模型今后是否改用
`requested_speaker_id` 的名字写法（当前只暴露 `agt_…` ID）。

同时记录这次运行暴露出的**花费节奏**：22 次调用墙钟仅 20.6s（平均 0.94s／次，两次调用之间的空档均值 21ms），
即「自动运行」在无人干预时约每秒花掉一次额度，只在无新信息／预算耗尽／人工暂停时停下。上限调到 200 后，
最长可连续花费约 3 分钟；想控制花费应使用「单步」。

## 10. 事后核对（2026-09-27 维护轮，只读，不改动上文记录）

复核方式：对 `backend/sceneweave.db` 以只读连接（`file:...?mode=ro`）查询 `scene_turns`／`messages`／`events`，
不改写任何行。核出的事实：

| 事实 | 值 |
|---|---|
| 场景 `scn_48c301dd89074c978aa3843f2b772043` 的 turn 总数 | **25** = 3（`role_action@m02`）＋ 22（`role_action@m02.1`） |
| `role_action@m02` 三条（修复前，旧进程） | 16:14:10 SUCCEEDED、16:14:11 `SCHEMA_INVALID`、16:15:59 `SCHEMA_INVALID`（均为 `reply_to_message_id` 类型错误，与 §1 现象一致） |
| `role_action@m02.1` 二十二条（修复后） | 16:21:46–16:22:06 UTC（＝本地 00:21:46–00:22:06），**全部 SUCCEEDED**，`failure_kind` 为空 |
| `messages`／`events` | 22 条消息（21 条带 `reply_to_message_id`、2 条带 `requested_speaker_id`）；**`events` 为 0** |

由此确认 §9 的「22 次调用全部成功」准确，且该 22 次**不含**修复前的 2 次失败（§8 提到的 00:14／00:15 两次失败即上表第二行）。

**发现并登记的一处记录不一致（未改动原文）**：§8 标题标为 00:25，晚于 §9 的运行时间 00:21–00:22；
但 §8 表格第 6 行记录的却是 `PAUSED/PROVIDER_ERROR、3/200、last_seq=1`——该状态只能对应 **§9 那 22 次调用之前**
（当时共 3 条 turn、1 条消息）。两者不能同时是「同一时刻的观测」。可从证据独立复原的只有：`role_action@m02.1`
的 22 条 turn 发生在 **00:21:46–00:22:06**，故生效那次重启发生在 00:21:46 之前；§8 那次重启的墙钟时刻与
「00:25」是否同一轮，无法由现有证据判定。场景**当前**状态为 `PAUSED/MANUAL、25/200、last_committed_seq=22`，
`pause_reason` 由 `PROVIDER_ERROR` 变为 `MANUAL` 发生在 §9 之后。

**对本缺陷的结论不变**：修复在真实模型上生效（22／22 成功）；`events` 仍为 0，**定向事件的真实效果仍未验证**。这
一处时间标注不一致属记录问题，不影响 §5 的核验结论，已写入 `state/reports/MAINT-2026-09-27.md`。
