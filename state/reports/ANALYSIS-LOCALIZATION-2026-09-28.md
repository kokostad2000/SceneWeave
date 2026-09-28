# 行为分析六次定位测试

状态：测试完成；**工程检查通过，语义定位未通过，缺陷待修复**。执行授权：人工“开始测试”；既有配置可真实调用，每次供应商请求输入加输出上限 10,000,000 tokens。

范围：离线工程检查 → 六次真实定位 → 异常登记／固定复测。36 次阶段验收留待主要缺陷收敛。
不以 API 返回成功替代语义检查，不设置成功率数值门槛，不用其他成功抵消不可接受输出。

## 已执行

- 后端：`PYTHONPATH=scripts .venv/bin/python -m pytest tests/test_m06_analysis.py tests/test_m06_boundary.py tests/test_m06_api.py tests/test_model_analysis_contract.py tests_optional/test_external_upstream.py -p block_outbound_plugin -p no:cacheprovider -r a --tb=short`，退出 0，74 passed；一条既有 Starlette 弃用警告。阻断出站网络。
- 前端：`pnpm run test -- --run`，退出 0，49 passed（其中分析组件 7 项）。

工作区另有发布基线工作持续变化；本轮保留这些文件，只修改本测试脚本、任务／状态及取证报告。本轮不提交或推送，不修改应用业务代码或上游文件。

## 证据约束

三层仅保存供应商普通 content、安全模型元数据与用量、上游规范化响应、项目分析记录；
不保存密钥、认证头、环境变量或 reasoning_content。剧情由 Mock 写入独立测试库，
真实 API 只做分析，未使用本机试用数据库。语义判断逐例附原文依据。

## 执行方法与命令

脚本：`backend/scripts/analysis_localization.py`。默认假 SDK；真实分析必须带 `--live`。
通过真实应用的创建场景、STEP、分析 POST、历史 GET 路径取证。角色行动是 Mock，
不冒充真实角色生成质量。六次首轮、四次异常固定复测各有独立证据文件，未覆盖首轮。
每个子过程按指定样例数限制供应商请求数，SDK 重试为 0；每个输出上限 1400 tokens。

以下命令在 backend 下执行，输出路径以仓库为基准：

| 命令 | 退出码 | 结果 |
|---|---|---|
| `PYTHONPATH=. .venv/bin/python scripts/analysis_localization.py --output ../state/reports/live/analysis-localization-20260928-fake6.json` | 0 | 六次假 SDK 工程校验通过；不计入真实语义证据 |
| `PYTHONPATH=. .venv/bin/python scripts/analysis_localization.py --live --output ../state/reports/live/analysis-localization-20260928-live.json` | 0 | 六次真实分析，逐例工程校验通过；退出 0 只表示工程检查，不表示语义通过 |
| `PYTHONPATH=. .venv/bin/python scripts/analysis_localization.py --cases L1 L3 L5 L6 --output ../state/reports/live/analysis-localization-20260928-retest-fake.json` | 0 | 四次异常样例筛选路径的假 SDK 检查通过 |
| `PYTHONPATH=. .venv/bin/python scripts/analysis_localization.py --live --cases L1 L3 L5 L6 --output ../state/reports/live/analysis-localization-20260928-retest-live.json` | 0 | 四次真实固定复测，工程校验通过，语义异常再次出现 |
| `git diff --check` | 0 | 本轮修改无空白错误 |

真实命令经沙箱提权执行，调用使用 Settings 的既有配置；仅记录配置布尔值和来源，不打印凭证。
首轮准备脚本时曾有失败，均未删除：fake／fake2（退出 1）将独立分析预算增加误作剧情变化，
第一版还复用客户端累积请求计数；fake3／fake4（退出 1）误用时间线角色字段，实际应为
`message.actor_id`；fake5（退出 1）误从顶层读取私有背景，实际在 `agent.snapshot`。
对应工具输出保留，存在的 fake／fake2／fake5 JSON 保留。修复只涉及新取证脚本，
未删用例或放宽现有产品测试；仅排除两个响应中同一个独立分析预算字段，其余快照逐项严格比较。

## 1. 工程链路

- 离线 74 项覆盖五状态、未发送拦截、可选配置、预算、材料长度／公开范围、画像关闭及异常隔离；前端分析组件 7 项包含降级与展示。
- 本轮十次真实分析均验证：本人的原文只在 behavior_description，其他角色的原文只在 context；分析对象前缀正确，已有私有背景未进入任何取证层。
- 比较每次前后完整场景／人设、运行状态、剧情时间线、角色状态和三个角色的 viewpoint：除独立分析请求预算按设计增加，均不变。画像写入方法被测试陷阱监测，没有写入尝试；返回 profile_persisted=false。
- 每次实际请求为 1，实际用量已知，保守上界和实际用量均在单次额度内；API 历史记录与本次返回一致。
- 五种状态映射在离线反例中通过；真实十次均为 NORMAL，**不表示五状态都在真实供应商上验证**。
- 三层取证为 raw_model → normalized_upstream → project_api.report。十次标签完全相同，未出现过滤丢失或适配丢失。本轮原先的“缺少合法标签”未复现；不能回推上轮未保存原始 content 时标签消失的具体原因。
- 原始模型每次提供两种替代解释，未用项目占位说明冒充真实解释。项目返回局限说明和免责声明，前端相关展示在组件测试中通过。先前进度消息误称局限字段为空，已更正，**不登记此项为缺陷**。

## 2. 六次固定定位样例的语义复核

判定依据为公开原文及标签语义，不以 NORMAL、白名单合法性或低置信度代替依据。

| 样例 | 所选对象／材料 | 首轮输出及结论 | 固定复测 |
|---|---|---|---|
| L1 | 安然，#1 弄洒饮料道歉，#4 碰湿纸道歉并补救 | repeated_apology 有依据；post_error_reassurance_request 无直接依据：并未请求原谅、安慰或确认。Q2 | 相同附加标签再现 |
| L2 | 许川，同一六条对话，#2 晚饭由别人决定，#5 电影由别人决定 | preference_nonexpression、decision_delegation、repeated_neutral_answer 有依据；未归入其他角色的道歉或解释。该定位点通过 | 无异常，不额外复测 |
| L3 | 陈禾，同一六条对话，#3、#6 两次解释费用平分 | repeated_explanation、message_repetition 有依据；clarification_request 证据不足：角色在提供说明，没有请求别人澄清。Q2 | 相同附加标签再现 |
| L4 | 安然，同样两次道歉；上下文加入许川攻击、陈禾反复资历强调 | 仍分析安然道歉，没有把他人攻击／资历归给她；仍附带无依据 post_error_reassurance_request。Q2 | 与 L1 同一标签问题，未追加重复调用 |
| L5 | 安然，只有“嗯。” | reduced_contact、shorter_replies 需要历史对照；单条回复无法证明联系减少或回复变短。虽解释承认材料不足，仍贴趋势标签并标 NORMAL。Q1 | 相同标签再现 |
| L6 | 安然，只有“收到。”；上下文为另外两人道歉／强调资历 | 未归入他人道歉或资历，但 shorter_replies、reduced_participation 缺基线；解释也承认没有回复时间／参与频率对照。Q1 | 相同标签再现 |

三人切换后分析内容随目标变化，强干扰没有复现原先的错对象问题。
然而“合法标签”仅表示属于白名单，**不等于每个标签都有材料依据**。
六次不能全部判通过；一次失败已足够登记，其他样例的成功不抵消。

## 3. 缺陷登记与定位

| 编号 | 缺陷 | 证据与归属 | 修复后固定复测要求 |
|---|---|---|---|
| Q1（P2，待修复） | 材料不足仍输出比较／趋势标签，缺基线且保持 NORMAL | L5、L6 首轮及复测；模型原始输出就有标签，上游只做白名单校验，项目原样保留 | 原样复测 L5、L6；允许空标签／正确降级／谨慎描述当次短回复，禁止凭单条材料推断“减少／变短” |
| Q2（P2，待修复） | 相关行为组的附加标签被一起带出，缺逐标签直接依据 | L1、L3、L4；L1、L3 固定复测；请求安慰／请求澄清均未发生于原文 | 原样复测 L1、L3、L4；保留有依据的道歉／重复解释标签，禁止无依据附加标签 |

**推断**：上游提示把每个行为与多个标签并排呈现，例如“反复道歉”同时列出请求安慰、
“反复解释”同时列出请求澄清，可能诱发同组标签一并选择。已确认的事实是三层都保留这些
标签；该提示编组是否为唯一原因尚未验证。不能靠删除结果标签、放宽验收或低置信度免责来宣称修复。

本轮逐条阅读首轮及四次复测普通 content、规范化结果与最终报告：
**未发现错误归因、私有背景泄露或无依据临床诊断**。这是本批观察，不是持续质量或安全保证。
Q1/Q2 是无依据行为标签缺陷，与“临床诊断”分别登记，不偷换分类。

## 4. 用量与原始证据

| 阶段 | 实际分析请求 | 输入 tokens | 输出 tokens | 缓存输入 tokens |
|---|---:|---:|---:|---:|
| 首轮六次 | 6 | 9,029 | 1,749 | 0 |
| 异常固定复测 | 4 | 5,923 | 1,081 | 5,239 |
| 总计 | 10 | 14,952 | 2,830 | 5,239 |

总输入输出 17,782 tokens；最大单次 1,861 tokens。单次预算按每条响应检查，
不将十次合并当一次。复测输入缓存命中率 88.45%；这是固定材料复用的点时证据，
不代表普通连续聊天已有同等命中率，也不代表本轮实现了缓存优化。

原始文件：

- `state/reports/live/analysis-localization-20260928-live.json`，SHA-256 `82e9455ed255dc14a551ecea7cc4e5a3c739dad1288153381ab3848b95f9c08d`。
- `state/reports/live/analysis-localization-20260928-retest-live.json`，SHA-256 `4a3289138cddbcbfb7f7b0394188c359fc715cba292a74a39f28be0e2bf5ca07`。

原始 JSON 中 semantic_review 为 pending，表示脚本不能自动判语义；正式复核结论以本报告为准。

## 5. 本轮结论与未验证项

工程链路检查通过；原先错对象／标签丢失问题未在本轮复现。
已发现并固定复现 Q1/Q2，**本批语义定位未通过，不能宣称分析质量稳定**。
M06 转为进行中（缺陷待修复），历史离线工程验收记录保留。

本轮没有修复业务实现。后续先修复标签证据约束，再跑相关离线反例和固定异常复测；
主要缺陷收敛后才运行 12 组 × 3 次阶段验收。
36 次验收、本批真实结果的浏览器视觉验收、人类独立复核、长时间稳定性均未验证；
前端组件测试不能替代这些项目。本轮没有重跑完整后端回归或构建：业务代码和契约未修改。
