# 人物／本场设定分离实施报告（2026-09-29）

> 公开分支仅发布核验汇总；下文提及的 JSON、XML、截图、完整模型请求和数据库备份均为本机留存，未随此分支发布。

已按用户「修订 PRD 后进行开发」授权，先修订唯一 PRD 与任务书，串行完成 M00→M07。SR-01～12 工程核验通过；有限真实观察已执行。本机前后端已更新并保持真实 API 配置。人工对话质量、真实长期容量、真实讨论分析及历史 M06 Q1/Q2 不在本轮通过项中。

## 最终行为与改动范围

人物目录复用名称与 ID；新建会话提交 configuration_version=2，五项 role_profile（公开身份、人设、表达习惯、初始目标、私有背景）在本场提供，全部可空。未填字段不从旧目录、姓名或其它场景回填。Discussion 的 focus／initial_position 继续作为本场私人配置。预置场景直接复制 PresetScene 的设定，既有同名目录中的旧文字不能覆盖它；新补齐目录仅保存名称。

创建后的完整快照保存于原 scene_agents 列。新 PATCH profile 接口仅在版本 2、READY、首次请求前开放；完整 role_profile 替换，省略 discussion_config 保留，空配置清空。在事务内再次检查锁定，阻止首次请求开始与编辑提交之间的竞争。目录更新／删除不改本场快照，开始后通过原事件表达变化。

版本 1 保留旧客户端与历史：未指定版本仍复制旧模板，明确提供新配置字段（含 null）拒绝；新配置不会被静默忽略。迁移 008 仅增加 configuration_version 默认 1；原业务字段、真实请求快照原样保留。新提示标识为 role_action@simulation.sr.1／discussion.sr.1，旧场景保留 p1.1。共用行动、权限、JSON、引用、用量与停止规则。

主要代码：contracts/scene、api、registry／导出；domain/scenes、templates；storage/scenes_repo、008；api/scenes、templates；context/models、visibility、builder；Runner 单行配置版本接线；前端 RoleProfileEditor、ConfigView、ChatView、client。新增五份 test_sr_*.py 与 sr-ui.test.tsx。生成产物仅用 scripts/export_contracts.sh。M07 添加独立有限观察脚本，不添加运行功能。

Scheduler、模型适配、状态机、分析生产代码与开工基线一致；没有自主唤醒、高级分析、长期记忆或额外运行引擎。开工前 PC／DM 未提交工作全部保留。源码副本／SHA 清单在 $TMPDIR/sceneweave-scene-role-baseline，最终差异在 scope-audit.json（原始记录仅本地留存）。未提交／推送 Git，未改其它项目、上游仓库或系统服务。

## 分模块独立核验

下表均为本轮实际执行。后台命令在 backend 内使用前缀 `PYTHONPATH=scripts .venv/bin/python -m pytest -p block_outbound_plugin -o addopts='' -q`；所列测试逐个重新运行，不继承历史通过结论。详情与失败过程保留在 M00～M07 的 SR 段。

| 模块 | 实际集合／命令 | 退出码／结果 |
|---|---|---|
| M00 | test_sr_contracts、test_scene_contract、test_contract_export、test_m07_config_dotenv；删除三个生成文件后 scripts/export_contracts.sh | 0；45 passed；后续显式 null 反例纳入最终回归 |
| M01 | test_sr_storage、test_m01_scenes、test_m01_templates、test_m01_storage、test_dm_storage、test_m07_config_dotenv | 0；96 passed；后续锁竞争反例另补核 |
| M02 | test_sr_context、test_dm_context、test_m02_context、test_m02_scheduler | 0；66 passed |
| M03 | test_m03_model_adapter、test_dm_model、test_token_limit、test_pc_parser | 0；105 passed |
| M04 | test_sr_runtime、test_dm_runtime、test_pc_runtime、test_m04_runner、test_m04_api、test_m04_sse | 0；178 passed |
| M05 | frontend：pnpm test／pnpm run typecheck／pnpm run build；独立 Mock 浏览器 | 全部 0；73 passed；真实交互／布局检查通过 |
| M06 | test_dm_analysis、test_m06_analysis、test_m06_api、test_m06_boundary、test_m06_localization、test_model_analysis_contract | 0；90 passed；原 Q1/Q2 不关闭 |

每阶段使用新临时数据库／端口或纯快照重建；非法版本、字段、长度、引用、锁定、失败、预算、幂等与恢复反例均执行。无／空／占位凭证矩阵由配置与模型集合覆盖，禁用及缺可选分析依赖分别验证。没有删旧用例或新增 skip／xfail，旧版本精确列表增加 008，不放宽原字段、回滚或漂移断言。

## M07 最终命令与证据

| 编号 | 实际命令／检查 | 退出码／结果 | 证据 |
|---|---|---|---|
| SR-V1 | 根目录：删除三份生成文件；scripts/export_contracts.sh 两次 | 0／0；从空重建与连续导出 SHA 完全一致 | 生成重建（原始记录仅本地留存） |
| SR-V2 | backend：上述 pytest 前缀＋`--junitxml=../state/reports/scene-role-profile/backend-offline.xml` | 0；768 passed，1 warning in 26.96s；0 failure/error/skipped | 全量 XML（原始记录仅本地留存） |
| SR-V3 | backend：pytest 前缀＋`tests_optional --junitxml=../state/reports/scene-role-profile/analysis-optional.xml` | 0；11 passed；假 SDK，无真实供应商 | 可选依赖 XML（原始记录仅本地留存） |
| SR-V4 | frontend/dist 删除后 pnpm test、pnpm run typecheck、pnpm run build | 全部 0；73 passed、tsc 0、49 modules、546ms，JS/CSS 重新生成 | 完整输出（原始记录仅本地留存） |
| SR-V5 | pytest 前缀＋test_sr_delivery、test_sr_contracts、test_contract_export | 0；28 passed；未知用量／超限／晚失败非零退出、缺配置不建库 | test_sr_delivery.py；SR-V2 |
| SR-V6 | pytest 前缀＋test_sr_storage、test_sr_runtime | 0；34 passed；两模式关闭应用重开，配置／实际快照原样、重放零调用；锁竞争 409 | SR-V2 对应新用例 |
| SR-V7 | SQLite 旧试用库一致副本升级、重复迁移／原列 SHA 对比 | 0；仅应用 008、重复为空；12 张业务表逐列一致、integrity=ok | 副本迁移（原始记录仅本地留存） |
| SR-V8 | 独立 Mock 8003／5176 实际浏览器 | 五字段初始空、开始前编辑零调用、STEP 后锁定、本人视角隔离、390／1280 无横向溢出、控制台 0 error | 浏览器事实（原始记录仅本地留存）、browser-edit.png |
| SR-V9 | `.venv/bin/python scripts/scene_role_observation.py --live --turns 3 --output ../state/reports/scene-role-profile/live` | 0；两个独立样本共 6 成功请求，5950 tokens，单次最大 1069 | 真实汇总（原始记录仅本地留存） |
| SR-V10 | 项目服务备份、精确 PID 重启、直接／代理 health、原列对比 | 0；sr.p1.1、deepseek、model_configured=true、dotenv；迁移 8，257 原请求保留，启动新增调用 0 | SCENE-ROLE-SERVICE-20260929T071213Z.json（原始记录仅本地留存） |
| SR-V11 | 更新后 5175 浏览器只选择议题模式及旧何澜，未创建／运行 | 五字段空、全场／本人标签清楚、控制台 0 error；临时标签关闭 | service-new-config.png |
| SR-V12 | git diff --check；开工副本比较／AST 用例数量／XML | 0；引擎未改、原测试未删、skip／xfail 0，旧 WIP 保留 | scope-audit.json |

完整离线回归使用插件阻断真实出站；回环假服务器由原测试创建。首跑默认沙箱 6 failed／757 passed，全部为 socket.bind PermissionError，保存 失败 XML（原始记录仅本地留存）；允许回环后原样重跑 763 passed。补齐两模式真实应用关闭重开与编辑锁竞争反例后，当时重新全跑为 766 passed；最后补齐旧新增角色接口的混用边界后，最终 768 passed。没有跳过或替换六项测试。Starlette TestClient 依赖弃用警告保留，不影响退出码。

## 过程失败与修正

阶段失败保留在模块报告：初次插件工作目录错误、两个不存在的测试名均不计为通过。仅名称创建最初使旧部分字段校验退化，补充完整旧字段校验后 M01 通过；旧迁移版本断言严格更新为 8。M02 新夹具公共投影不一致及候选对象携带配置文字变化，修正为合法快照、版本单变完整对象比较／配置单变资格与截止比较；没有改原断言。

M04 新测试误用 Mock.requests（实际为 calls）和幂等 deduplicated 预期，按真实接口改正。前端初次类型错误来自 Object.fromEntries 返回形状、讨论字段缺省及生成旧模板字段必填；明确生成 IdentityCreateRequest 并复核 M00／M01 后通过。旧版本字面量按新契约更新，未泛化断言。

最终补强锁竞争测试初次访问不存在的 app.state.scene_repository，1 failed／33 passed；改为实际 SceneService 仓储后 34 passed，再完整回归。后端最后刷新初次等待退出超时：Uvicorn 正等待 SSE 长连接；再确认 PENDING=0 后按其提示发送 SIGINT 关闭连接并启动最终后端，全部行再次一致、代理健康 200。最终复核新增角色接口也必须拒绝旧版本的新配置字段（含 null），补充两模式反例；`test_sr_storage.py test_m01_scenes.py test_m01_storage.py test_sr_runtime.py` 补核 79 passed，最后完整 768 passed。副本取证首次使用不存在的 SQL 列 id／locked，随后以 schema 的 scene_id／budget_locked_at 查询，仅只读失败，没有业务改动。早期 fullPage 截图拼接失真，最终改为视口截图；角色按钮首次选择器不匹配，读取真实 AX 后完成隔离检查。临时 Mock 服务已停止，PAUSED 样本仍保存在独立临时库，不混入试用库。

## 有限真实观察与服务切换

| 样本 | 真实请求／行动 | 实际输入与边界 |
|---|---|---|
| empty-discussion | 3 成功／3 PASS；2835 tokens | 旧露营目录同名三人，新本场五字段为空；实际请求不含任何旧行为文本，discussion.sr.1；不追加请求强迫发言 |
| preset-simulation | 3 成功／3 SPEAK；3115 tokens | 同名目录故意提供不同旧文字；本场实际取 CAMPSITE 原定义，simulation.sr.1；目录内容未覆盖场景预设 |

两份独立样本均 ENDED、无在途；实际端口输入与落库 request_snapshot_json 逐条相等，预算与实际请求一致，返回模型均 deepseek-flash。每次调用分别记录输入输出用量并走原单次 10,000,000 上界检查；不把六次合计当作单次验收。不记录 API key／认证头／reasoning_content。

服务切换前无 PENDING／RUNNING／PAUSING／STOPPING，先一致备份再停止已核对的项目进程；停止后再次备份，启动新版单 worker 后端与 Vite。API 库 007→008 后 12 张业务表原列 hash 相同，旧场景配置版本均为 1，257 条原请求保留。直接／代理健康检查均 200，真实提供方继续启用，analysis_enabled=false 保持已有配置。旧新增角色兼容校验补齐后，后台又一次备份并只刷新后端，最终版本健康和全部数据库行再次一致（见回执 final_backend_refresh）。启动／查询未新增模型请求；本轮 6 次真实验收只存在独立样本库。

原试用库升级前备份：$REPO_ROOT/state/backups/scene-role-service-before-20260929T071213Z.db。当前端口仍 5175／8002；新建会话使用新版空设定，旧会话保留旧提示与旧设定。回退须使用备份配合旧应用，不让旧程序读取已升级的数据库。源码及证据未提交／推送。

SR-01～12 的逐项映射见 [docs/ACCEPTANCE.md](../../docs/ACCEPTANCE.md)。工程与有限真实观察已完成；空资料不会自动使角色更活跃，三次 PASS 不能证明自由讨论、观点演变或对话质量通过。人工 UX／行为质量、真实长期容量、真实讨论分析、原 M06 Q1/Q2、浏览器自动重连、异机部署及远端 CI 保持未验证／未关闭。
