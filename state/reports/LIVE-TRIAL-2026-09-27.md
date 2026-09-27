# SceneWeave 本机真实试用核验（2026-09-27）

## 授权与范围

人工明确允许将本项目虚构角色设定、提示词和生成对话发送到 DeepSeek API 并产生费用；
先前逐次人工授权门槛已移除。所有真实脚本仍需显式 `--live`，角色与行为分析每次
供应商请求在发送前检查输入估算加最大输出不超过 **10,000,000 tokens**。
本轮只在本机回环地址运行，没有提交、推送、改动上游仓库或查看密钥值。

## 真实 API 专项

| 检查 | 原始证据 | 结果 |
|---|---|---|
| 三人聊天、定向事件、行为分析 | [首次专项](live/live-integration-20260927-first.json) 与同名 `.db` | 脚本退出 0；6 次角色请求成功，三名角色参与初始对话，定向事件仅目标可见并被其处理，行为分析 `NORMAL`、供应商请求 1 次。该次目标发言未提及较含糊的事件，语义效果不计通过 |
| 更具体的定向事件 | [漏水事件专项](live/live-integration-20260927-salient-event.json) 与同名 `.db` | 脚本退出 0；6 次角色请求成功；仅许川看到定向事件，其他两人后续发言未提“漏水”，许川在事件后公开发言明确提到“客厅窗边水管漏水” |
| 九份质量样本 | [人工观察表](../../docs/QUALITY_REVIEW.md) 中逐份链接与同名 `.db` | 三个预置场景各三次，每份 3 次角色请求均成功；需要人工判断对话质量 |

上述专项使用 `backend/.venv/bin/python scripts/live_integration.py --live --turns 3
--after-event-turns 6 --with-analysis --out <证据路径>`（首次），第二次不带
`--with-analysis`；质量样本使用 `--live --quality-only --preset <场景> --out <证据路径>`。
九份质量样本中，便利店第 1 次原脚本错误要求“三人都发言”，因此历史退出码为 **4**；
同名数据库确认三次 `SUCCEEDED`（`PASS／PASS／SPEAK`），修正验收判断后保留原始
证据，未伪称该次脚本当时退出 0。便利店第 2 次 `PASS／PASS／PASS`，没有公开消息；
`PASS` 是合法沉默，仍需人工判断这种体验是否可接受。

## 浏览器本机试用

后端为 `127.0.0.1:8002`，前端为 `127.0.0.1:5175`，使用独立本地数据库
`backend/sceneweave-live-trial.db`；没有占用原有的 8000／5173 服务。两端
`/api/health` 均返回 HTTP 200，`model_provider=deepseek`、`model_configured=true`、
`model_credential_source=dotenv`、`analysis_enabled=true`，没有输出凭证。

在浏览器创建“三个室友的客厅”会话，连续点击三次“单步”：安然、许川、陈禾各产生
一条真实发言；界面显示成功 3、失败 0、结果不明 0、角色预算 3／200。
选安然与三条公开发言进行真实行为分析，第一次调用返回 `NORMAL`，但内容主要
讨论陈禾，属于分析对象偏题。随后在 `analysis/boundary.py` 的实际发送文本中明确
分析对象及其他材料仅作上下文，重启服务并对同场景再调一次；第二次内容聚焦安然，
但上游缺少行为标签，应用如实显示 `DEGRADED`、`llm_no_allowed_tags` 和
`missing_behavior_labels`。两次均计入真实分析请求数，不把降级结果写成成功质量结论。
服务重启后原会话、三条发言、请求计数及第一次分析记录仍在，证明本机存储可恢复。

实际 HTTP SSE 按序号补发已在本轮早期 Mock 本机环境核对；浏览器代理中断后前端
自动重连的行为仍未独立证实，不计通过。

## 用量与凭证边界

汇总 11 个专项数据库和 1 个本机界面数据库：**42 次角色请求**（失败 0、
用量未知 0），输入 24,865／输出 2,956 tokens；**3 次行为分析供应商请求**，
输入 4,444／输出 976 tokens，状态为 2 `NORMAL`、1 `DEGRADED`。
观察到的单次输入加输出最大 **1,847 tokens**，低于 10,000,000 上限。
证据 JSON 的键名检查未发现 `api_key`、`authorization`、`secret` 或
`reasoning_content` 字段；没有打印或记录密钥值。应用的发送前检查为保守估算；
若供应商不遵守最大输出值，响应后才可按实际 usage 判定超限，已产生费用无法撤销。

## 本轮修改与核验

相关修改见工作树：真实调用规则、共享 token 边界、分析适配、质量留样脚本、
分析对象提示、对应测试及文档。历史报告不倒改为“当时已通过”。

| 实际命令或检查 | 退出码 | 结果 |
|---|---:|---|
| `PYTHONPATH=/private/tmp .venv/bin/python -m pytest -p no_net_plugin -p no:cacheprovider -q --tb=short`（`backend/`，允许回环假服务、阻断外网） | 0 | **435 passed**；1 条既有 Starlette 弃用警告 |
| 同样插件下 `tests_optional/test_external_upstream.py -q` | 0 | **7 passed**，假 SDK |
| `.venv/bin/python -m pytest tests/test_m06_boundary.py -q -p no:cacheprovider` | 0 | **12 passed**，含分析对象提示和长度上限边界 |
| `pnpm run test -- --run`（`frontend/`） | 0 | **49 passed** |
| `pnpm run typecheck`（`frontend/`） | 0 | TypeScript 检查通过 |
| `git diff --check` | 0 | 补丁格式通过 |

第一次完整后端回归在受限执行环境中退出 **1**，6 个测试均因本机回环端口
`PermissionError` 未能启动假 HTTP 服务；在获准回环绑定、同时由插件阻断外网后
原样重跑退出 **0**。该次失败不掩盖，也不算代码缺陷。

## 结论与仍需观察

本机真实服务和界面现已可试用。真实三人对话、定向事件、行为分析调用及九份质量
样本均有原始记录；分析偏题在一次真实复测中改善，但第二次为降级结果，不能推断
长期分析质量。PRD 第 10 节要求的**人工质量观察**仍待人在
[`docs/QUALITY_REVIEW.md`](../../docs/QUALITY_REVIEW.md) 逐份填写；便利店全员
沉默样本应重点判断。浏览器自动重连、长时间运行、其他机器或公网部署也未验证。
