# 自由续聊实施报告（2026-09-29）

> 公开分支仅发布核验汇总；下文提及的 JSON、XML、截图、完整模型请求和数据库备份均为本机留存，未随此分支发布。

状态：M00～M07自由续聊增量已验收；原M06 Q1/Q2及人工自然度/长期容量仍未验证。用户已授权方案实施，按M00→M07串行推进。公开发布分支仅含源码、测试与汇总文档。

## 跨模块登记（修改前）

M00 契约新增独立 chat_policy_version、COLLECTIVE_SILENCE 与规则限额；M01 新迁移及场景创建；M02 轮转／沉默与 Prompt；M03 策略校验；M04 原子保存成功序号／PASS／优先消费与恢复；M05 上下文／暂停／历史显示；M06 长正文分析边界检查；M07 回归和对照证据。生成产物仅由 scripts/export_contracts.sh 重建。历史测试继续覆盖策略 1，新策略增加独立测试。原有 configuration_version 不复用。

## 未验证项

本报告引用的原始输入输出、完整请求快照、XML、截图和本地服务记录仅留在本机，GitHub提交不附这些运行产物；公开仓库保留汇总、命令与验收边界。

实际命令、退出码与失败证据见逐模块记录及M07表。已完成代理操作的隔离Mock浏览器检查；人工自然度、真实长期容量、真实讨论分析、SSE自动重连、远端CI、异机部署及原分析Q1/Q2仍未验证／未关闭。工程及有限真实观察不替代人工语义结论。后续已获用户对提交和推送的明确授权。

## 2026-09-29 自由续聊 M00（FC-01/02）

已验收。修改契约策略版本、暂停枚举、Unicode长度、输出额度和成功游标字段；前端产物仅正式导出。实际命令：scripts/export_contracts.sh（0）；backend/.venv/bin/python -m pytest tests/test_fc_contracts.py tests/test_action_contract.py tests/test_ports_contract.py tests/test_scene_contract.py tests/test_contract_export.py -q（0，77项通过）；-p scripts.block_outbound_plugin tests/test_m07_config_dotenv.py -q（0，16项通过，包括无变量／空／占位环境）。三个生成产物删除后重新导出（0），漂移检查另行执行。旧200／201断言显式按策略1验证，新1000／1001独立验证；未删除／skip／xfail。无真实外部调用，无密钥输出。未验证：真实自然度、浏览器人工质量、长期容量、远端CI及原Q1/Q2。进入M01条件已满足。

## 2026-09-29 自由续聊 M01（FC-03）

已验收。009迁移为旧场景补策略1，新增成功游标列；新建API／Service／预置默认2，可显式1，两种配置版本独立。旧列逐项一致、失败迁移整体回滚、重复执行为空、新库重建。实际命令（backend cwd）：.venv/bin/python -m pytest -p scripts.block_outbound_plugin -o addopts='' -q tests/test_fc_storage.py tests/test_m01_storage.py tests/test_m01_scenes.py tests/test_sr_storage.py（0，64 passed）。初次错误文件路径退出4；新测试调用错方法曾1 failed／62 passed，已修正为insert_scene_with_agents；一次错误cwd加载网络插件失败退出1，正确cwd重跑上述64项通过。SR原008迁移断言在001～008夹具保留，新009单列检查，未放宽原数据一致性检查。无真实调用，不改试用库。未验证清单沿用。进入M02。

## 2026-09-29 自由续聊 M02（FC-04～06）

已验收。修改 context/models.py、visibility.py、builder.py 与 scheduling/scheduler.py；策略2独立轮转、按成功序号公平选择、逐角色PASS及本人可见信息判定沉默、每条最新点名由目标processed_seq消费。新Prompt fc.1；旧Prompt保持200码点与旧模板。实际命令（backend cwd）：.venv/bin/python -m pytest -p scripts.block_outbound_plugin -o addopts='' -q tests/test_fc_scheduler.py tests/test_m02_scheduler.py tests/test_m02_context.py tests/test_dm_context.py tests/test_sr_context.py（0，77 passed）。初次讨论测试夹具背景冲突1 failed／72 passed，修正夹具为一致背景；一次错误编辑cwd未生效使相同失败复现，最终完整检查通过。2／3／5／8人、同时间戳轮转、无新信息续聊、全员PASS、已消费优先、隐藏私聊前后第三方Prompt相同均覆盖。独立临时纯数据重建，无skip／xfail、无真实调用。未验证项沿用。进入M03。

## 2026-09-29 自由续聊 M03（FC-07）

已验收。action_parser按ReferenceScope策略验证正文上限；Mock草稿仍经同一边界。历史适配器夹具显式1024，原断言保持，新策略4096及1000码点单列验证。实际命令（backend cwd）：.venv/bin/python -m pytest -p scripts.block_outbound_plugin -o addopts='' -q tests/test_fc_model.py tests/test_m03_model_adapter.py tests/test_m03_local_model.py：初次7 failed／92 passed（1项夹具参数、6项回环权限），修正夹具后6 failed／93 passed；允许本机回环、阻断外网的原命令重跑退出0，99 passed。请求正文重建；空content、非法JSON、非法引用、截断、过长、单次token限制反例保持，无修复请求，无真实供应商调用。环境矩阵沿用本轮M00实际16项。未验证清单沿用。进入M04。

## 2026-09-29 自由续聊 M04（FC-08/09）

已验收。Runner传递保存的策略／Prompt／正文范围／输出额度；新策略请求4096、旧1024。RuntimeRepository成功事务同时保存消息、行动、processed_seq、PASS、单调成功序号及场景优先计数。全员沉默仅在待生效事件处理后判定；START／RESUME／STEP依据实际全员沉默状态原子清除沉默标志并开始，不重置顺序／预算／处理位置。实际命令（backend cwd）：.venv/bin/python -m pytest -p scripts.block_outbound_plugin -o addopts='' -q tests/test_fc_runtime.py tests/test_m04_runner.py tests/test_m04_api.py tests/test_m04_sse.py tests/test_pc_runtime.py tests/test_dm_runtime.py tests/test_sr_runtime.py（0，203 passed）。初次旧库夹具使用新仓储写旧列及迁移列表过期导致3 failed／177 passed，改为历史原列SQL播种、009完整迁移列表；原记录逐列相同断言未放宽。新测试覆盖两模式2／3／5／8人、主动续聊、公私聊、固定时钟、全员沉默、恢复幂等、待生效定向事件、失败／UNKNOWN、3处事务故障回滚、重启无请求、正文与预算／上下文。测试从临时空库重建，无skip／xfail和真实调用，未验证项沿用。进入M05。

## 2026-09-29 自由续聊 M04 补充复核

只读独立复核发现并修正：最后PASS与人工PAUSE同时发生时，继续应依据实际全员沉默重新授予机会；成功事务提交后、更新暂停状态前崩溃的RUNNING孤儿场景应转PROCESS_INTERRUPT而不重放行动。ModelActionRequest与ReferenceScope版本必须一致，未提供scope的真实解析仍按请求版本。实际追加回归：FC runtime／model + M04 runner／api + ports 130 passed（0）；FC runtime + M04 api + PC runtime 71 passed（0）。保留固定时钟、事务故障与幂等断言。task中“从全员沉默”指实际状态，不只依赖pause_reason文本。

## 2026-09-29 自由续聊 M05（FC-10）

已验收。新建界面显式策略2，历史显示保存版本；全员沉默原因可继续／单步；角色卡展示实际Prompt码点数及80%提示，角色视角只返回本人数据；长正文保持换行与转义，分析提示缩小材料。实际命令：backend .venv/bin/python -m pytest -p scripts.block_outbound_plugin -o addopts='' -q tests/test_fc_ui_api.py tests/test_m04_api.py tests/test_pc_runtime.py（0，48 passed）；frontend pnpm exec vitest run --reporter=dot（0，78 passed／9文件），pnpm run typecheck（0）；删除frontend/dist后pnpm run build（0）。初次前端旧契约／默认字段5 failed／68 passed，明确保留新契约预期后通过；新增FC测试夹具TypeScript错误曾退出2，补齐契约字段／props后退出0，长文本改为恰好1000码点。历史200规则显示不发送命令；隐藏私聊前后第三方HTTP使用量与视角完全一致，所有只读查询不新增模型请求。无skip／xfail；Mock/组件验证不替代浏览器与人工自然度。进入M06。

## 2026-09-29 自由续聊 M06（FC-11）

隔离增量已验收；原Q1/Q2继续进行中。分析service自检接受COLLECTIVE_SILENCE，材料上限仍各4000，4条1000码点本人发言因来源前缀超限被阻断，缩小到3条后完整送出3000码点正文。1000码点私聊仍拒绝，阻断不占预算，运行状态／角色预算不变。实际命令：backend .venv/bin/python -m pytest -p scripts.block_outbound_plugin -o addopts='' -q tests/test_fc_analysis.py tests/test_m06_boundary.py tests/test_m06_api.py tests/test_m06_analysis.py tests/test_dm_analysis.py（0，60 passed）。第一次错误文件名退出4；新测试把分析NORMAL写为SUCCEEDED曾失败，修正为真实分析契约并保留材料长度／原文／只读断言。全部使用临时空库及假分析器，无skip／xfail，无真实分析调用、未修改上游。进入M07。

## M04/M03 最终只读复核修正及回归

统一START／STEP／RESUME先生效已接受事件；模拟进程中断后的首个真实Mock请求必须包含该事件，事件只生效一次。Mock无scope仍按请求策略验证201码点旧正文。控制命令在任何副作用前持久化未确认回执，完成后更新；结果尚未确认的重放只返回当前状态、不再派发。无自动重试，可能尚未执行的中断命令须新request_id再次显式操作。新增回归覆盖在途取消、成功后最终状态写入失败、重启后同request_id重放。修正时误插函数参数导致一次SyntaxError退出4；随后4条回执字段错误及1条新分析夹具错误（5 failed／167 passed）保留，修正后195 passed（0，包含FC/M04/M06及历史SR/DM观察）。新观察脚本初次误用scene_profile入站字段422（5 failed／190 passed），改为契约role_profile，最终195 passed。历史SR／DM脚本显式策略1，旧模板／停机断言保持，FC另测两策略。

## 2026-09-29 自由续聊 M07（FC-12）

已验收（工程增量及有限真实观察）；人工自然度与长期容量未验证，原M06 Q1/Q2仍进行中。实现按M00～M07串行修改，独立代理只读复核。原始运行证据仅本地留存。

| 编号 | 实际命令／检查 | 退出码及结果 | 证据 |
|---|---|---|---|
| FC-V1 | backend：`PYTHONPATH=.:scripts .venv/bin/python -m pytest -p scripts.block_outbound_plugin -o addopts='' -q tests --junitxml=../state/reports/free-chat/backend.xml` | 0；851 passed，0 skipped／xfail；外网阻断，本机回环假HTTP允许 | free-chat/backend.xml |
| FC-V2 | backend：同pytest前缀，`tests_optional --junitxml=../state/reports/free-chat/analysis-optional.xml` | 0；11 passed；假SDK | free-chat/analysis-optional.xml |
| FC-V3 | frontend：`pnpm exec vitest run --reporter=dot`、`pnpm run typecheck`；删除dist后`pnpm run build` | 全部0；78 passed／9文件；类型检查及空构建成功 | M05实际记录 |
| FC-V4 | 删除三个契约产物后`scripts/export_contracts.sh`；同pytest前缀`tests/test_contract_export.py tests/test_m07_config_dotenv.py` | 全部0；24 passed，含无／空／占位环境；正式产物从零重建无漂移 | M00/正式导出 |
| FC-V5 | 独立8132／5212 Mock应用、实际浏览器创建／自动运行／继续／本人视角 | 997码点正文完整、pre-wrap、内嵌script节点0；4成功全员沉默→继续→7成功；他人用量隐藏 | free-chat/browser-evidence.json、browser.png |
| FC-V6 | `.venv/bin/python scripts/free_chat_observation.py --turns 6 --output ../state/reports/free-chat/mock` | 0；四个独立Mock样本均2 PASS；全员沉默／旧无新信息正常；用量为测试值 | free-chat/mock/20260929T154701064536Z |
| FC-V7 | `.venv/bin/python scripts/free_chat_observation.py --live --turns 6 --output ../state/reports/free-chat/live` | 0；20成功、0失败／UNKNOWN／PENDING；27371 tokens，单次最大2076 | free-chat/live-summary.json及4份完整evidence.json |
| FC-V8 | 真实试用库一致备份→副本009→精确项目PID刷新→原列hash／直接及代理health | 0；11旧场景策略1；266原请求保留；12业务表及原迁移行原列一致；integrity ok；fc.p1.1、deepseek、配置true、dotenv | free-chat/service.json；state/backups/free-chat-before-20260929T154517Z.db |
| FC-V9 | `git diff --check`、原测试AST函数／assert数量检查、XML反例检查 | 最终0；原用例未删除、断言数量未减少、无skip／xfail、未改.env或上游 | free-chat/scope-audit.json |

### 失败证据与处置

首次完整命令未提供脚本导入路径，收集1 error退出2（backend-collection-failed.xml）；加入项目PYTHONPATH后11 failed／840 passed（backend-first-failure.xml）：8项旧DM模型夹具仍默认4096但原断言1024，1项迁移列表少009，2项旧PC验收脚本随API默认切到策略2。分别显式1024、精确[7,8,9]、PC脚本显式策略1；原断言未删除或放宽，最终全量851通过。一次diff检查报告M04末尾空行退出2，清理后退出0。进程ps沙箱只读检查退出126，获本机进程读取权限后核对成功；全页浏览器截图存在拼接失真，采用browser.png视口图，不将失真图当布局证据。以上失败均不计通过。

### 有限真实对照

每种Mode/策略至多6次、相同两人设定，遇自然暂停即停止，不为了补足样本而继续；每场使用独立数据库。simulation策略1：2 PASS、1852 tokens；策略2：6 SPEAK、7755 tokens、最长162码点。discussion策略1：6 SPEAK、8427 tokens、最长190；策略2：6 SPEAK、9337 tokens、最长353。无真实私聊出现，不要求覆盖或强迫回复；私聊及1000边界有确定性Mock/适配器证据，但本次真实样本不证明这些自然发生率。每次供应商调用分别先检查10,000,000输入+最大输出的保守上界，返回输入输出用量均完整且未超限。实际端口请求与落库request_snapshot逐条一致，实际发送预算一致。没有记录认证头、密钥或reasoning_content。

20个请求只是有限观察，不能证明自然度普遍提升、长篇逻辑质量或模型必能输出1000码点。人工自然度、真实长期容量、真实讨论分析、原Q1/Q2、SSE自动重连、远端CI和异机部署继续未验证／未关闭。

### 本机可用状态

5175／8002已更新，frontend现有Vite按源码热更新，后端精确刷新为单worker。11旧场景全部策略1，原消息/请求/配置/游标/预算未改写，启动及健康查询新增请求0。刷新页面后新建会话默认策略2；旧会话不自动转换。当前analysis_enabled=false保持既有配置。隔离浏览器服务验收后停止，不混入试用库。回退使用备份配合旧源码，不能让旧程序直接读取已升级库。
