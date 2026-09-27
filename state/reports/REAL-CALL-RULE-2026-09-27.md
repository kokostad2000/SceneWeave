# 真实调用规则变更与核验（2026-09-27）

人工新指令：去除 SceneWeave 真实模型调用的逐次人工授权要求，允许自由调用，
但每次供应商请求的输入与输出用量合计不得超过 10,000,000 tokens。
此规则只改变真实调用门槛；`--live`、有效配置、普通 CI 不自动花费、凭证不外泄与
Mock／真实证据分离仍保持。

## 修改

- `AGENTS.md` 第 3 节：真实角色模型与行为分析无需逐次授权，加入单次 token 上限。
- `backend/role_theater/ports/token_limit.py`：用文本消息 UTF-8 字节数、4,096 的
  包装余量和最大输出参数做发送前上界检查；输入与输出合计超过 10,000,000 时拒绝。
- `backend/role_theater/ports/openai_chat.py` 和
  `backend/role_theater/analysis/external.py`：分别在角色调用与上游行为分析调用前
  执行检查；供应商报告实际用量超限时保留用量并标记失败。
- `backend/scripts/live_smoke.py`、`backend/scripts/live_integration.py`：去掉
  `--confirm-spend` 门槛，仍要求显式 `--live` 和有效凭证。更新任务书、发布与验收文档。
- 新增或更新边界测试：临界值、未给输出上限、发送前拒绝、角色与分析的服务端
  用量超限、真实脚本预检查。测试只使用假传输或假 SDK。

## 实际核验

| 命令／检查 | 退出码 | 结果 |
|---|---:|---|
| `PYTHONPATH=/private/tmp .venv/bin/python -m pytest -p no_net_plugin -p no:cacheprovider --tb=short` | 0 | 后端完整回归 **434 passed**；插件阻断出站；1 条既有弃用警告 |
| 同一阻断插件下跑 `tests_optional/test_external_upstream.py` | 0 | 可选上游包 **7 passed**，假 SDK，无真实供应商请求 |
| `UV_CACHE_DIR=<repo>/.cache/uv uv lock --check` | 0 | 锁文件一致，37 个包；初次无缓存变量时因沙箱拒绝访问用户缓存而退出 2，不计入通过 |
| `live_integration.py` 不带 `--live` | 2 | 拒绝真实调用；未读取模型配置 |
| `live_smoke.py` 不带 `--live` | 2 | 拒绝真实调用；未读取模型配置 |
| `git diff --check` | 0 | 补丁格式通过 |
| 配置状态（只打印布尔值与来源） | 0 | `provider=deepseek`、`model_configured=true`、`credential_source=dotenv`、分析包已安装；未查看或打印密钥 |

单次调用上限的发送前检查是文本请求的保守估算，不能替代供应商返回的真实用量；
供应商若不遵守输出上限，应用会在收到响应后标记超限，但无法撤销已产生的费用。
供应商不返回 usage 时仍记 `unknown`，不编造实际 token 数。

## 真实专项验收仍未执行

曾两次申请执行同一个 `live_integration.py --live --turns 3 --after-event-turns 6
--with-analysis` 命令，两次均在创建进程之前被自动审批拒绝；没有真实 API 调用，
专项证据 JSON 与独立数据库均未创建。审批给出的具体理由是：尽管人工已允许
“自由调用”，仍未在可信用户指令中明确允许**向 DeepSeek API 外发**项目的角色
设定、提示词与生成对话并产生费用。已核对拟用的三个预置场景均是项目中明确标明
的虚构内容，但第二次审批仍拒绝。不得通过其他命令或界面绕过这一拒绝。

因此真实定向事件、真实行为分析、九份真实质量样本和人工质量观察继续列为
**未验证**；收到对具体目的地与材料范围的明确批准后再继续。
