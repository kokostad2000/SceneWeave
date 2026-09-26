# 资料来源

本文件区分两类内容：

1. **本项目实际核对过的来源**（可点击、可复核，附核对日期与结论）；
2. **PRD 引用但当前无法核对的来源**（`[S1]`～`[S9]`）——**保持未验证，不编造地址**。

---

## 1. 本项目实际核对过的来源

| 编号 | 来源 | 核对日期 | 用于核对什么 | 结论 |
|---|---|---|---|---|
| V1 | DeepSeek API Docs — [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion) | 2026-09-26 | 请求字段与响应字段的真实契约 | 见下表 |
| V2 | DeepSeek API Docs — [Your First API Call](https://api-docs.deepseek.com/) | 2026-09-26 | `base_url`、`api_key`、可用模型名 | `base_url=https://api.deepseek.com`；模型为 `deepseek-flash`、`deepseek-v4-pro`；旧名 `deepseek-v4-flash`／`deepseek-v4-flash-vision-exp` 仍被接受，但对应模型已退役，请求由 DeepSeek-V4.1-Flash 承接并按 Flash 价格计费（与 PRD 2.1 的描述一致） |

### 1.1 与实现相关的核对结论（V1）

| 项目 | 官方文档 | 本项目实现 | 状态 |
|---|---|---|---|
| 思考开关字段 | `thinking: {"type": "enabled" \| "disabled"}`，**默认 `enabled`** | `DEFAULT_THINKING_DISABLED_PAYLOAD = {"thinking": {"type": "disabled"}}` | **一致**（原「U-M03-1 字段名待核对」由此**关闭**） |
| 思考强度 | `reasoning_effort ∈ {none, low, high, max}`；`minimal→low`、`medium/xhigh→high` | 不发送 `reasoning_effort`（PRD 2.2 要求不发送 `reasoning_effort=100`） | **一致** |
| JSON 输出 | `response_format={"type": "json_object"}`；**必须同时用 system/user 消息指示模型输出 JSON**，否则可能持续输出空白直至触顶 | 客户端发送 `response_format`；ContextBuilder 的提示词含「只返回一个 JSON 对象……不要输出 JSON 之外的任何内容」 | **一致**（无指示的调用会导致看似卡住的长请求，本项目已避免） |
| 截断表现 | `finish_reason="length"` 时 content 可能被截断 | `length` → `TRUNCATED`，且**优先于**内容解析 | **一致** |
| 其它终止原因 | `stop`／`content_filter`／`tool_calls`／`insufficient_system_resource`／`aborted` | 全部显式分类：`length→TRUNCATED`，其余异常取值 → `PROVIDER_ERROR`，并在解析内容**之前**判定 | **已补齐**（原先只处理 `length`，其余会退化成「空 content」） |
| 用量字段 | `usage.prompt_tokens`／`completion_tokens`／`total_tokens`／`prompt_cache_hit_tokens`／`prompt_cache_miss_tokens`，以及 `prompt_tokens_details.cached_tokens` | 读取 `prompt_tokens`／`completion_tokens`／`prompt_cache_hit_tokens`；**缺失记 unknown 而不是 0** | **一致** |
| `max_tokens` 范围 | 1～384K；非思考模式默认 8K | 发送 1024（PRD 2.2 初值） | **一致** |
| 温度 | 思考模式下 `temperature` 无效 | 不发送 `temperature`，也不用它推断思考已关闭 | **一致** |
| tools | 支持；思考模式下 `required`／指定工具会返回 400 | 不发送 `tools`／`tool_choice` | **一致** |
| 思考内容 | 思考模式返回 `message.reasoning_content` | 不存储、不展示（PRD 7.2） | **一致** |

### 1.2 仍未由文档解决、必须真实联调才能确认的项

| 编号 | 项目 | 说明 |
|---|---|---|
| U-M03-2 | 真实响应结构在**本项目参数下**的实际表现 | 文档给出了字段定义，但空 content、内容过滤、资源不足等情形的实际返回组合仍需一次真实调用观察 |
| U-M03-3 | 90 秒总期限在真实网络下的合理性 | 需真实联调 |
| U-M06-1／2 | 外部分析仓库 `behavior-psychology-v2.0` 的模块路径与响应字段名 | 仓库不可访问（`bd1e8fa…`），本文件**不编造**其内部结构 |
| U-M07-1 | 真实模型下的对话质量 | 需人工观察，且 Mock 结果不可替代 |

## 2. PRD 引用但当前无法核对的来源（保持未验证）

`PRD.md` 第 2、6 节与文末「资料索引」提到 `[S1]`～`[S9]`，并说明其原始地址、仓库提交与核对说明位于 `docs/SOURCES.md`。**但 `PRD.md` 本身没有给出这些地址**，当前工作区也没有该文件。

处置（沿用 `AGENTS.md` 第 5.1 节）：

- **不编造** `[S1]`～`[S9]` 的地址、提交号或核对说明；
- 因此 PRD 中依赖这些引用的表述（例如某些能力与评测结论）**保持未验证**；
- 若需要补齐，请提供原始地址，或明确授权联网检索后由本项目逐条核对并记录来源与日期。

| 编号 | 对应 PRD 位置 | 状态 |
|---|---|---|
| `[S1]`～`[S9]` | PRD 第 2 节表格、第 5.3／6.2 节、文末资料索引 | **未验证（地址缺失）** |

> 注：本项目自行核对的 V1／V2 与 `[S1]`～`[S9]` **不是同一批来源**，不能互相替代。V1／V2 只覆盖 Chat Completions 的接口契约。
