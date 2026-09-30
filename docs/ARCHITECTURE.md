# SceneWeave 架构说明（首版）

状态：M00 建立，2026-09-29 同步双模式 P1。适用范围为首版及 PRD 第 1.4 节冻结增量；扩展位置只在文末登记。

需求唯一来源是 `PRD.md`。本文件只说明首版的目录职责、核心数据结构、接口边界与运行状态。

---

## 1. 总体形态

模块化单体：一个 FastAPI 进程（单应用 worker）承载全部后端职责，一个 SQLite 文件承载全部持久化，前端为独立构建的 React SPA，通过 HTTP 控制接口 + SSE 事件流通信。

```
浏览器 (React SPA)
   │  HTTP 控制命令（含 request_id，幂等）      │  SSE 已提交事件（按 seq 补发）
   ▼                                          ▼
FastAPI 应用（单进程、单 worker）
   ├── api/          路由层：校验、幂等入口、错误映射
   ├── contracts/    请求／响应契约（Pydantic）——接口唯一来源
   ├── ports/        外部端口协议：ModelPort、AnalysisPort（+ Mock 实现）
   └── [M01～M06]    领域与运行时：角色/场景、ContextBuilder、Scheduler、
                     ModelClient 实现、状态机、分析适配层
   ▼
SQLite（事实来源：模板、快照、事件、行动、请求结果、分析结果）
```

硬性约束（来自 PRD 第 8 节）：

- 后端请求／响应模型是接口的**唯一来源**；导出 OpenAPI 并生成前端类型，前后端不各自维护不一致枚举。
- 只定义两个外部端口：**模型行动**与**行为分析**。不建通用插件系统。
- 数据库事件是事实来源；不把多消费者 Queue 当广播，不引入完整事件溯源框架。
- 服务默认仅监听本机，不把无认证服务暴露到公网。

## 2. 目录职责

| 路径 | 职责 | 归属模块 |
|---|---|---|
| `backend/role_theater/contracts/` | 公共契约：枚举、行动、事件、命令、端口、M01 配置接口的请求／响应模型；`registry.py` 登记全部契约模型供 OpenAPI 导出 | M00 + M01 |
| `backend/role_theater/ports/` | `ModelPort`、`AnalysisPort` 协议定义与 Mock／Fake 实现 | M00（协议）／M03、M06（实现） |
| `backend/role_theater/storage/` | SQLite 短连接、版本化迁移（`migrations/*.sql`）、模板与场景仓储 | M01 |
| `backend/role_theater/domain/` | 领域服务与领域错误：`TemplateService`、`SceneService`（不依赖 FastAPI） | M01 |
| `backend/role_theater/presets.py` | 预置“三个室友的客厅”（PRD 3.1） | M01 |
| `backend/role_theater/api/` | HTTP 路由：健康检查与契约自检（M00）、模板与场景（M01）；控制与 SSE 在 M04 | M00 + M01 + M04 |
| `backend/role_theater/config.py` | 运行配置与预算常量（模型名、超时、重试、长度上限、SQLite 路径） | M00 |
| `backend/role_theater/`（运行时） | ContextBuilder、Scheduler、状态机 | M02～M04 |
| `backend/role_theater/analysis/` | 行为分析适配层，唯一允许导入外部 `behavior-psychology-v2.0` 的位置 | M06 |

行为分析可选依赖锁定到上游提交 `bd1e8fa97b395223d629539022fbd92e1a5429d7`。
适配层从 `src.analyzer` 加载 `DefaultBehaviorAnalyzer`，从 `src.schemas` 加载请求模型，
并以显式配置和关闭隐式重试的 SDK 代理调用。上游安全边界在占用分析预算前检查；
请求始终设置 `persist_profile=false`。未安装可选依赖或缺少真实模型配置时能力显示为关闭。
| `backend/scripts/export_contracts.py` | 导出 `backend/openapi.json` 与前端契约摘要（无需密钥） | M00 |
| `backend/tests/` | 后端测试（契约、失败路径、存储、状态机、幂等） | 各模块 |
| `frontend/src/api/generated/` | 生成产物：`schema.d.ts`（OpenAPI 类型）、`contract-summary.json`（枚举／上限／端口） | M00（生成，勿手改） |
| `frontend/src/api/` | 请求封装与契约的运行时视图 `contracts.ts` | M00 |
| `frontend/src/lib/` | 前端工具，含与后端一致的 Unicode 码点计数 | M00 |
| `frontend/src/views/` | 配置页、聊天页、历史页（复用聊天页只读模式） | M05 |
| `frontend/src/components/` | 时间线、运行控制、角色侧栏、角色视角、分析抽屉 | M05 |
| `frontend/src/hooks/` | `useSceneStream`：SSE 按 `seq` 去重与断线追赶 | M05 |
| `docs/` | 架构、验收（`ACCEPTANCE.md` 待建）、资料来源（`SOURCES.md` 待建） | 持续 |
| `tasks/` | 模块任务书，每份只设“需求／目标／规范”三节 | 各模块开工前 |
| `state/` | `STATUS.md` 与 `reports/Mxx.md`（证据） | 持续 |
| `scripts/export_contracts.sh` | 一键重建全部契约产物 | M00 |

依赖方向：`api → contracts`、`api → 领域/运行时 → ports ← 具体实现`。**契约层不得反向 import 领域实现或具体模型客户端。**

## 3. 核心数据结构（首版）

字段名即为契约字段名（`snake_case`）。所有长度限制按 **Unicode 码点**计数，裁剪空白后校验。

### 3.1 配置与角色

| 结构 | 关键字段 | 说明 |
|---|---|---|
| `AgentTemplate` | `template_id`, `name`, `persona`, `speech_style`, `initial_goal`, `private_background`, `created_at`, `updated_at` | 五项内容：名称／人物设定／表达习惯／初始目标／私有背景 |
| `AgentSnapshot` | 上述五项（值拷贝） + `template_id`（来源） | 本场角色保存的**模板快照**；模板后续改动不影响历史与已有会话 |
| `SceneAgent` | `agent_id`（关联主键）, `scene_id`, `name`（显示字段）, `snapshot`, `order_index` | 名称是显示字段，`agent_id` 是主键；同场景内名称不可重复；2～8 人，**不使用** `agent1/agent2/agent3` 固定列 |
| `Scene` | `scene_id`, `title`, `background`, `status`, `schema_version`, `budget`, `created_at`, `ended_at` | 场景背景 ≤ 2000 码点；一个活动场景，多份历史记录 |

长度上限（首版初值）：名称 30／人物设定 1000／表达习惯 300／初始目标 500／私有背景 1000／场景背景 2000／事件正文 1000。

### 3.2 行动

| 结构 | 关键字段 | 说明 |
|---|---|---|
| `ActionDraft` | `action`, `text`, `reply_to_message_id`, `requested_speaker_id`, `recipient_id` | **新提示词规定这五个字段**；`actor_id`／`scene_id`／消息 ID／时间由服务端添加 |
| `ActionType` | `SPEAK`, `PRIVATE`, `PASS` | `SPEAK`／`PRIVATE`：策略2 `text` 1～1000码点，策略1 1～200码点；`PASS`：`text` 与三个对象／引用字段都必须为空 |
| `ActionRecord` | `action_id`, `turn_id`, `attempt_id`, `scene_id`, `actor_id`, `status`, `draft`, `message_id`, `input_cursor_seq`, `created_at` | 一次调用的落盘结果；**只有成功 SPEAK／PRIVATE／PASS 才推进该角色已处理位置**，失败不推进 |
| `Message` | `message_id`, `scene_id`, `seq`, `actor_id`, `text`, `reply_to_message_id`, `requested_speaker_id`, `created_at` | 公开聊天记录；`PASS` 不形成气泡但保存行动结果 |

引用校验：`reply_to_message_id` 为空，或指向本场**已提交**且该角色**可见**的公开发言；`requested_speaker_id` 为空，或为本场另一名有效角色。

**可引用标识必须先出现在提示词里**：ContextBuilder 的时间线条目带出发言的 `message_id` 并与 `#序号` 别名并列（`[#3 | msg_…] 陈禾：…`），名册带出角色的 `agent_id`（`陈禾（agt_…）`）。`ReferenceScope` 同时携带同一批发言的 `allowed_message_ids` 与 `allowed_message_seqs`，因此模型回消息 ID 或回序号都能被确定性解析；序号不在范围内依旧是非法引用。这是**查表换算**，不是静默修剪、自动广播或追加修复调用（2026-09-26 真实联调因提示词不暴露消息 ID 导致 4/8 次调用 `SCHEMA_INVALID`，见 `state/reports/FIX-reply-reference.md`）。

服务端在保存前必须校验：枚举、字段完整性、额外字段、文本长度、角色与消息引用。空 content、`finish_reason=length`、格式异常、非法引用、过长正文一律**失败**，不静默修剪、不自动广播、不追加修复调用。

### 3.3 事件

| 结构 | 关键字段 | 说明 |
|---|---|---|
| `Event` | `event_id`（稳定）, `scene_id`, `seq`（单调）, `body`, `visibility`, `target_agent_id`, `status`, `schema_version`, `accepted_at`, `effective_at` | 操作者人工事件；`seq` 与行动／消息共享同一个场景内单调序列 |
| `EventVisibility` | `ALL`, `TARGETED` | `ALL` 全体可见；`TARGETED` 仅 `target_agent_id` 可见 |
| `EventStatus` | `ACCEPTED`, `EFFECTIVE` | 界面必须区分“已接受”和“已生效” |

规则：暂停时提交事件**立即生效但不自动继续**；调用进行中提交先保存为 `ACCEPTED`，当前调用结束或失败后按接受顺序生效。结束请求之后拒绝新事件；此前接受的事件在调用边界顺序落盘，但不再触发新行动。已生效事件不可编辑或删除，纠正用追加新事件。

### 3.4 调度与预算

| 结构 | 关键字段 | 说明 |
|---|---|---|
| `RoleCursor` | `scene_id`, `agent_id`, `processed_seq`, `startup_opportunity_consumed`, `last_action_at` | 每角色已处理位置；仅成功行动推进 |
| `SchedulerDirective` | `actor_id`, `reason`, `based_on_seq` | 调度结果可复核；每场同一时刻**只有一个**角色请求在执行 |
| `Budget` | `max_role_requests`（默认 **200**，人工裁决 2026-09-26 由 24 上调）, `max_analysis_requests`（默认 4） | 两者独立计数，各自最多一个在途请求；发送即占用，失败／超时／重试不退款。创建会话时可在 [1, 200] 内下调，开始后锁定；单步／自动运行的控制方式不变 |
| `Usage` | `input_tokens`, `output_tokens`, `cached_tokens`, `unknown` | 以服务端返回为准；**缺失记为 unknown，不是 0**；本期不承诺货币费用 |

### 3.5 端口请求／响应

| 结构 | 关键字段 |
|---|---|
| `ModelActionRequest` | `scene_id`, `actor_id`, `prompt_template_id`, `prompt`（已由 ContextBuilder 构建）, `cursor_seq`, `params` |
| `ModelActionResponse` | `raw_content`, `parsed_draft`, `finish_reason`, `requested_model`, `returned_model`, `usage`, `provider_request_id`, `latency_ms`, `failure` |
| `ModelFailure` | `kind`（`EMPTY_CONTENT`／`TRUNCATED`／`INVALID_JSON`／`SCHEMA_INVALID`／`REFERENCE_INVALID`／`TIMEOUT`／`PROVIDER_ERROR`／`CONTEXT_LIMIT`）, `detail` |
| `AnalysisRequest` | `scene_id`, `agent_id`, `behavior_description`（≤4000 字符）, `context`（≤4000 字符）, `persist_profile`（强制 `false`）, `provider_attempts` |
| `AnalysisReport` | `status`, `behavior_labels`, `mechanisms`, `alternative_explanations`（≥2）, `limitations`, `disclaimer`, `degradation_flags`, `usage` |
| `AnalysisStatus` | `NORMAL`, `BLOCKED`, `DEGRADED`, `FAILED`, `DISABLED` |

外部端口协议（首版仅两个）：

```python
class ModelPort(Protocol):
    async def generate_action(self, request: ModelActionRequest) -> ModelActionResponse: ...

class AnalysisPort(Protocol):
    async def analyze(self, request: AnalysisRequest) -> AnalysisReport: ...
    @property
    def enabled(self) -> bool: ...
```

- 分析被**本地边界规则**拦截时：记录一次分析操作，但 `provider_attempts = 0`；用户可见的分析操作数与实际模型请求数分开。
- 禁用分析时**不得**要求外部包已安装；`AnalysisPort` 的默认实现不导入任何外部包。
- 库内部吞掉供应商异常并返回降级结果的情况必须能被识别（`degradation_flags`），不把返回 JSON 当成分析成功。

### 3.6 运行参数（首版初值，非性能承诺）

`model=deepseek-flash`、`stream=false`、`response_format=json_object`、显式关闭思考、不发送 tools；新场景策略2 `max_output_tokens=4096`、旧策略1为1024；请求总期限 90 秒；SDK 自动重试 **0**；`max_prompt_chars=32000`（保守字符限制，超过则暂停，不静默截断）。思考模式开启时温度参数无效——**不能用较低 temperature 推断思考已关闭**。不向公共 API 发送 `reasoning_effort=100`。

真实角色调用与行为分析共用单次 **10,000,000 tokens** 上限：发送前用文本消息的
UTF-8 字节数、4,096 token 包装余量及最大输出参数计算保守上界，超限不发送；
服务端返回实际输入与输出用量后若报告超限，记录用量并标记失败。服务端未返回用量
仍记为 unknown，不能声称实际消耗已被测量。

### 3.6.1 可替换模型适配器（PRD 第 8 节）

`ModelPort` 有三个实现，由配置 `SCENEWEAVE_MODEL_PROVIDER` 选择：

| 提供方 | 实现 | 凭证 | 请求体差异 |
|---|---|---|---|
| `mock`（无凭证时的默认） | `MockModelPort` | 不需要 | 不发起任何网络请求 |
| `deepseek` | `DeepSeekModelClient` | **必须有** | 发送 `thinking: {"type": "disabled"}` |
| `local` | `LocalModelClient` | **不需要** | **不发送** `thinking`；`response_format` 可关闭 |

- `auto`（默认）：有凭证走 `deepseek`，否则走 `mock`；
- **显式选定的提供方不得静默回落 Mock**：`provider=deepseek` 但缺凭证时按 `MISSING_CONFIG` 失败（不派发、不占预算），避免“以为在真实调用”；
- 三个实现共用同一套**发送 → 解析 → 用量 → 失败分类**机制（`ports/openai_chat.py` 的 `ChatProfile` 只描述请求差异），因此换后端**不放宽**判定；
- `local` 指本机或局域网内的 OpenAI 兼容端点：Ollama `:11434/v1`、LM Studio `:1234/v1`、vLLM `:8000/v1`、llama.cpp `:8080/v1`；
- `backend/scripts/fake_local_model.py` 是**严格模式**的假本地服务，可在没有安装任何本地模型时验证该链路（它会拒绝 `thinking` 等云服务专有字段，因此未被拒绝即证明请求体干净）。

### 3.7 存储 schema（M01）

SQLite，短连接 + 显式事务；迁移文件在 `storage/migrations/NNN_name.sql`，已应用迁移记录 checksum，被改写即拒绝启动。四张表：

| 表 | 关键列 | 约束与理由 |
|---|---|---|
| `agent_templates` | `template_id` PK、五项内容、`is_preset`、`created_at`、`updated_at` | 名称唯一（索引 `idx_agent_templates_name`） |
| `scenes` | `scene_id` PK、`title`、`background`、`status`、`pause_reason`、`schema_version`、`max_role_requests`、`max_analysis_requests`、`budget_locked_at`、`preset_key`、时间戳 | `status` 用 CHECK 约束到六个合法值；`budget_locked_at` 非空即表示已锁定 |
| `scene_agents` | `agent_id` PK、`scene_id` FK、`name`、`order_index`、`source_template_id`、六个 `snapshot_*` 列、`snapshot_captured_at` | `UNIQUE(scene_id, name)`、`UNIQUE(scene_id, order_index)`；**没有** `agent1/agent2/agent3` 之类固定列 |
| `schema_migrations` | `version` PK、`name`、`checksum`、`applied_at` | 迁移幂等与防篡改 |

两条硬性设计决定：

1. 本场角色**每行一个**，快照列内联在 `scene_agents` 中——角色是集合，人数由数据决定，代码不写死。
2. `source_template_id` **不设外键**：模板被移除后，已有场景的快照必须继续可读（PRD 3.2 的快照隔离）。

锁定语义：`scenes.budget_locked_at` 非空后，新增／重命名／移除本场角色一律 409 `scene_locked`。M01 提供 `SceneService.lock()`；**由 M04 在首次实际角色请求开始时调用**。M01 不提供背景编辑接口，因此不存在“悄悄改写背景”的路径（tasks/M01.md §3.6 I2）。

## 4. 运行状态

```
READY ──start──▶ RUNNING ──pause──▶ PAUSING ──▶ PAUSED ──resume──▶ RUNNING
                   │  ▲                              ▲
                   │  └──────────────────────────────┘
                   ├──stop──▶ STOPPING ──▶ ENDED
                   └──budget exhausted──▶ ENDED
```

- `READY` 待开始、`RUNNING`、`PAUSING`、`STOPPING`、`PAUSED`、`ENDED`。**没有**其他状态。
- 暂停／结束在**当前调用边界**生效；当前调用按超时配置有界收尾，不新建下一次调用。
- `PauseReason` 必须区分：`NO_NEW_INFORMATION`（旧策略候选为空）、`COLLECTIVE_SILENCE`（新策略全员成功PASS且无待处理可见信息）、`MANUAL`、`PROVIDER_ERROR`、`CONTEXT_LIMIT`、`PROCESS_INTERRUPT`。达到角色调用上限 → `ENDED`。
- `ENDED` 不可恢复运行，但允许查看历史与预算内的只读分析；重新开始创建**新会话**。
- 页面刷新只恢复视图，不重启任务；浏览器断开不自动停止后台场景，预算继续有效。
- 进程重启后把遗留在途请求标记 `UNKNOWN` 并暂停会话，**不自动恢复付费请求**；恢复边界先处理尚未生效的已接受事件，再允许新的角色请求。

控制命令携带 `request_id`，重复提交返回既有结果（幂等）。历史播放只读取已保存数据，不调用模型。人工重试是新的显式请求，重新构建当前合法上下文，**不冒充**精确重放，也不宣称 exactly-once 语义。

### 4.1 行动事务与调度计数（2026-09-28 修复）

- 派发前的短事务同时写入 `PENDING` 行动与角色预算占用；任何写入失败均回滚，随后才允许进入模型调用。
- 模型返回后的成功短事务同时提交 `seq` 分配、可选公开或私聊消息、行动结果、角色游标与场景点名计数；`PASS` 也在同一边界提交。提交后再生效待处理事件并通知 SSE，网络等待期间不持有写事务。
- 未派发失败的行动结果与预算退款同事务提交；已发送的失败或结果不明继续占用预算，重启不自动重发。
- 连续点名次数保存在迁移 `004_scene_scheduler.sql` 的 `scene_scheduler_state`，由 M04 传给纯调度器；成功点名行动加一（最多 2），成功普通轮转清零，失败不推进，重启保留。旧 `RoleCursor.consecutive_requested_priority` 字段为接口兼容保留，当前调度不再读取它。
- 升级时历史连续次数因缺少调度原因无法准确重建，统一从 0 起算并清零旧角色计数，原有消息、行动、游标位置与预算保留。
- 单步和自动运行共用调用边界收尾：STOP 优先，其次完成等待中的 PAUSE；调用失败已进入暂停时保留错误原因。单步成功后进入 `PAUSED`，不存在依赖后续循环清理的 `PAUSING`。

## 5. 接口边界

### 5.1 已实现：M00 工程与契约

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/health` | 最小健康检查：`status`、`app_name`、`app_version`、`contract_version`、`run_state`、`analysis_enabled`、`model_configured`。**不需要任何密钥即可返回 200** |
| `GET` | `/api/contracts/summary` | 契约自检摘要：枚举取值、长度上限、预算上限、端口名称。供前端与契约测试核对 |

契约产物的生成方式（`scripts/export_contracts.sh`，不需要密钥）：

1. `backend/role_theater/contracts/registry.py` 登记全部契约模型；
2. `role_theater.main` 在生成 OpenAPI 时把登记模型的 JSON Schema 合并进 `components.schemas`，因此 M02～M06 的路由尚未建立时，前端也能一次性生成**完整**契约类型；
3. 导出 `backend/openapi.json` 与 `frontend/src/api/generated/contract-summary.json`；
4. `openapi-typescript` 由前者生成 `frontend/src/api/generated/schema.d.ts`。

这三个产物都**不得手工修改**；后端测试 `tests/test_contract_export.py` 会检测产物与契约源码漂移。

### 5.2 已实现：M01 角色与场景（配置期接口）

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/api/templates` | 创建模板（五项内容，按码点校验长度） |
| `GET` | `/api/templates`、`/api/templates/{template_id}` | 模板列表／详情 |
| `PATCH` | `/api/templates/{template_id}` | 编辑模板（`None` 表示不改该字段） |
| `POST` | `/api/templates/{template_id}/copy` | 复制模板；省略 `name` 时自动取不重复名称 |
| `DELETE` | `/api/templates/{template_id}` | 移除模板（**不影响**已有场景快照） |
| `POST` | `/api/scenes` | 创建场景：2～8 名本场角色（契约层 + 服务层双重校验），可设预算上限 |
| `POST` | `/api/scenes/preset` | 用预置“三个室友的客厅”创建场景；缺失的预置模板按需补齐 |
| `GET` | `/api/scenes`、`/api/scenes/{scene_id}` | 场景列表（含角色数）／详情（含角色集合与快照） |
| `GET` | `/api/scenes/presets` | 预置场景摘要（key／标题／背景／角色名） |
| `POST` | `/api/scenes/{scene_id}/agents` | 由模板新增本场角色（上限 8；已锁定则 409） |
| `PATCH` | `/api/scenes/{scene_id}/agents/{agent_id}` | 重命名显示名（不改快照；已锁定则 409） |
| `DELETE` | `/api/scenes/{scene_id}/agents/{agent_id}` | 移除本场角色（不得少于 2；已锁定则 409） |

M04 追加的**只读观察端点**（M05 为显示角色执行状态而请求，见 tasks/M05.md §3.4）：

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/scenes/{id}/agents/status` | 每个本场角色的执行状态（是否行动过／上次结果／已处理位置／是否被点名／发言条数）；只含运行事实，无心理评分 |

错误语义统一为 M00 的 `ApiError`：`not_found`→404、`duplicate_name`／`agent_count_out_of_range`／`scene_locked`／`unknown_template`→409、`validation_error`→422。这些接口**不调用模型**（PRD 3.1：创建配置、切换视图和历史回看不调用模型）。

### 5.3 已实现的运行与分析接口

| 方法 | 路径 | 模块 |
|---|---|---|
| `POST` | `/api/scenes/{id}/commands`（start／step／pause／resume／stop，含 `request_id`） | M04 |
| `POST` | `/api/scenes/{id}/events` | M04 |
| `GET` | `/api/scenes/{id}/stream`（SSE，按 `seq` 补发与去重） | M04 |
| `POST` | `/api/scenes/{id}/analyses` | M06 |
| `GET` | `/api/scenes/{id}/timeline`、`/api/scenes/{id}/agents/{aid}/viewpoint` | M02／M04 |

角色视角接口必须返回**与调用器实际使用相同**的上下文选择结果，不允许前端再实现一套权限。分析报告、错误、使用量、SSE 心跳和运行状态**不属于剧情**，不得进入角色上下文或唤醒角色。

## 6. 前端职责边界（首版）

- 完整消息显示，**不做逐字流式渲染**；生成中按钮仍可接收暂停／结束。
- 角色卡只显示名称与执行状态，不显示虚构心理仪表盘。
- 错误、待生效事件、停止原因与普通台词使用不同样式；当前待回应对象可高亮，但**不伪造**模型正在思考的具体内容。
- 模板与模拟（Mock）模式必须清楚标识，不把 Mock 演示当作 DeepSeek 实际输出。
- 文本渲染转义，不执行模型或事件中的 HTML／脚本。
- 完整 payload 仅限本机观察者检查，不进入普通应用日志。

M05 落地情况：配置页 / 聊天页 / 历史页（聊天页只读模式）+ 独立分析抽屉；角色卡只显示运行事实；
`model_configured=false` 时聊天页显示「模拟模式」标记；分析抽屉在 M06 接线前只提供选材与预览。

## 7. 首版之外的扩展位置（只登记，不实现）

角色中途加入／退出、长期记忆与 RAG、多人私聊、多场景并行、多用户鉴权、多 worker 并发、地图物品与移动、语音图片、联网与工具执行、通用插件系统。以上均**不设占位伪功能**；相应代码位置在上述目录内预留清晰边界即可。


## 8. 一对一私聊增量（pc.1，2026-09-28）

- 行动协议新增 `PRIVATE` 与 `recipient_id`，以回复引用有无区分主动私聊／回复私聊。`SPEAK` 只引用可见公开消息；`PRIVATE` 只回复本次快照中该收件人发给自己的消息。`ReferenceScope` 分开保存公开集合与本人收到的私聊及发送者，编号别名绑定当次请求。旧 SPEAK／PASS 缺少 recipient_id 读取为 null，PRIVATE 缺少收件人失败。
- 消息增加 `visibility`、`recipient_id`、`conversation_id`、`schema_version`；005 迁移将旧消息显式归 PUBLIC，保留原版本 1，新消息版本 2。人工事件结构与版本 1 不变。会话由场景 ID 与排序后的角色对稳定派生，从成功私聊消息聚合，因此没有未发消息的空会话；双向同项，按最新提交排序。
- 006 在 scene_turns 增加 request_snapshot_json。新请求的完整提示、参数、模板、局部引用映射与 PENDING／预算预留同事务保存，不含凭证。旧记录保持空值，不虚构旧提示快照。新结果中的消息、行动、游标、场景优先计数仍同事务提交，提交后通知 SSE。
- ContextBuilder 保留该角色完整可见公私历史，显示发送方向与来源；输出编号为可见集合局部编号，内部游标继续使用全局 seq。只有收件人得到新的外部信息；发送者不自唤醒，第三方没有私聊候选机会。公共点名和私聊收件人共用场景级两次连续优先上限。PASS 只消费本次机会，无剧情消息、无拒绝通知、无他人唤醒；新信息到达后仍能回复旧私聊。
- `GET /api/scenes/{id}/conversations` 支持 viewer_id、offset、limit；角色只返回本人会话。timeline 支持 viewer_id、conversation_id、offset、limit，先按权限筛选再分页，未知／无权会话 404。viewpoint 返回同一可见集合、局部编号、本人行动；events 的角色查询同样使用局部编号。agents/status 的角色查询隐藏其他角色行动、私聊对象和私聊计数。
- SSE 保持观察者全局提交序号，角色展示不连接或混入该流，而读取后端过滤结果。前端菜单为公共频道／私聊二级项／全场时间线，角色模式显示本人可见集合。视角切换清理旧数据并丢弃旧请求结果；sessionStorage 仅保存页面、场景、角色和频道 ID，刷新恢复视图而不请求模型。历史只读。生成状态与最近成功行动分开显示，失败不伪装为沉默。
- 分析仍只接收公开材料。前端不可选私聊；后端遇到私聊 ID 或公私混选整体 BLOCKED，provider_attempts=0。公开转述只作为转述者的新消息，不沿原私聊链接补材料。原 M06 Q1／Q2 缺陷继续保留。

契约版本为 pc.1，角色提示模板为 role_action@pc.1；需配套升级前后端。升级先使用 SQLite 一致备份，在副本验证 005／006 后再切换；回退使用升级前数据库与旧应用，不让旧程序读取新私聊库。详细命令与未验证项见 `docs/RELEASE.md` 和 `state/reports/M07.md`。


2026-09-29 M05 布局补充：消息区域使用随视口限定高度的独立滚动容器，公共／私聊／全场共用；标题与场景控制位于容器外。频道或角色切换重建滚动容器，从顶部开始，不删除或截断记录。会话菜单也限制最大高度并独立滚动；消息区可键盘聚焦，溢出滚动不传播到整页。

## 双模式 P1（2026-09-29）

Scene.mode 为 simulation／discussion；mode_config 是经过后端判别校验的 SimulationConfig／DiscussionConfig，旧 background 入站投影为 SimulationConfig。mode 创建后固定，background 是裁剪后以换行连接的公共信息投影，总计仍≤2000码点。角色模板和本场 snapshot 保存显式 public_profile；discussion_config 保存本场 focus／initial_position，私人配置仅本人进入Prompt，空观点不推断阵营。

迁移007增加模式、配置JSON、模板和角色公开身份列及mode索引；旧记录mode=simulation、public_profile为空，旧请求快照原样保留。新增列不改变原事件schema_version。契约版本dm.p1.1；生成文件仍只由scripts/export_contracts.sh生成。

Context流程：完整SceneSnapshot → visibility.filter_context → VisibleContext → 对应模式模板。VisibleContext仅包含公开PublicRole名册、自己的snapshot／discussion_config与合法可见条目，不携带第三方私人快照。模板分别为role_action@simulation.p1.1和role_action@discussion.p1.1；共用身份、四种产品行动、引用与工具禁用规则。Renderer不接触未过滤时间线。Runner仅接线mode／mode_config，Scheduler算法与状态机完全共用。

/api/scenes?mode=...只读筛选；/statistics?viewer_id=...通过现有可见性集合和本人行动记录统计消息、明确回复、参与者、成功／失败／UNKNOWN及PASS。观察者可查看全场；角色不拿隐藏会话或他人行动计数。统计不调用模型、不回写人设，也不输入Scheduler。

前端仅创建表单按mode分流；ChatView、HistoryView、私聊菜单、SSE与控制共用。视图缓存仅保存场景／角色／频道ID和历史筛选，切换时清除旧数据。现有AnalysisCapability增加有限显式能力描述、supported_modes／recommended_modes；推荐不限制手动调用，公开选材与整体拒绝规则不变，未新增Analyzer或动态插件框架。


## 人物／本场设定分离（sr.p1.1，2026-09-29）

人物目录复用 template_id／name。SceneRoleProfile 包含 public_profile、persona、speech_style、initial_goal、private_background；新场景的完整配置由 AgentSpecRequest.role_profile 提供，未提供的五字段保持空。创建后仍使用既有 scene_agents.snapshot_* 存储，不另建运行引擎或动态模板引用。DiscussionParticipantConfig 仍为本场私人配置。IdentityCreateRequest 提供仅名称入站，旧完整模板入站／更新／复制保留兼容；新界面只编辑目录名称。

Scene.configuration_version 为严格整数 1／2。008 仅增加该列，旧场景默认 1，原业务列和 request_snapshot_json 不重写；版本 1 保留旧模板复制与 p1.1 提示。新界面提交版本 2，只取目录名称；预置场景直接复制 PresetScene.agents 的配置，同名目录旧文字不能覆盖预设。新补齐的预设目录项为名称条目，既有旧文字不删除。

PATCH /api/scenes/{scene_id}/agents/{agent_id}/profile 接受完整 role_profile，仅限版本 2、READY、预算未锁定；discussion_config 省略保留、显式空配置清空。仓储在写事务内再次校验首次请求锁定，防止检查与提交之间开始运行。更新不改变来源 ID／agent_id，不发起模型请求，也不影响其它 Scene；开始后配置固定，后续变化使用原事件链路。

SceneSnapshot／VisibleContext 传递配置版本，过滤后才渲染本人资料与公开名册。版本 2 Prompt 标记为 role_action@simulation.sr.1／discussion.sr.1，说明资料只用于本场、目标可变、空资料不从姓名或旧场补全。行动规则与校验共用。Runner 只增加配置版本接线；Scheduler、模型适配、状态机、预算、公私聊、SSE 与分析生产代码均沿用开工基线。

当前本机 5175／8002 服务已升级到 sr.p1.1，先备份试用库后迁移 007→008；旧业务字段逐项一致，257 条原请求保留，启动新增供应商请求 0。恢复使用升级前备份配合旧应用；不要让旧程序直接读取升级后的库。服务凭证仍由配置层加载，证据只记录布尔值与来源。详情见 state/reports/CHANGE-scene-role-profile.md 与服务回执。


## 自由续聊 FC（2026-09-29）

- `Scene.chat_policy_version` 独立于人物 `configuration_version`；009迁移默认1，创建API默认2。旧Prompt/请求快照原样保留，新模板为 `role_action@{mode}.fc.1`。
- 策略2每个角色都能参与基本轮转，成功事务写入单调 `last_success_order`，公平性不依赖墙上时钟。最新消息的被点名／收件人优先仅在目标未处理该seq时有效，成功推进游标即消费，连续优先上限仍2。失败／UNKNOWN不推进成功游标。
- `last_success_action=PASS` 与本人可见外部消息/事件的processed_seq一起决定沉默；未完成启动机会的角色不算沉默。自己的发言仍使本人未沉默，须以后主动PASS；隐藏私聊不改变无关角色Prompt或上下文计数。全员判定前先激活待生效事件。所有显式开始／恢复／单步入口也先激活已接受事件。
- 从实际全员沉默再次显式运行，在转RUNNING的同一事务清空PASS标志，保留顺序、已处理位置和预算。孤儿RUNNING／PAUSING／STOPPING即使没有PENDING请求，重启后也暂停为PROCESS_INTERRUPT，不重放已成功行动。
- 控制命令在执行副作用前写入未确认回执，完成后更新结果。未确认回执重放返回当前状态与结果未确认提示，不再次执行；操作者须使用新request_id显式操作。这保证崩溃后相同命令不会重复消费预算，不承诺中断命令必然已执行。
- 模型请求及ReferenceScope保存一致策略；真实解析、Mock与Runner都检查本场正文上限。状态/视角API计算实际Prompt码点数，viewer查询仅返回本人。观察查询不写游标或调用模型。分析仍通过唯一隔离端口、各4000码点，无自动截断／摘要或工具扩权。
