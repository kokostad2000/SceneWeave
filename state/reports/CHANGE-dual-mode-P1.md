# 双模式 P1 实施与核验（2026-09-29）

本轮按用户“根据修改后的 PRD 开始开发”的授权串行完成 M00→M07。G0 范围门、DM-P1-01～16 工程门通过；G2 有限真实观察已执行。人工行为质量、真实长期容量和原 M06 Q1／Q2 继续未验证／未关闭。

## 实现与改动范围

沿用一个 SceneService、Runner、Scheduler、消息系统、预算和数据库。新增契约版本 `dm.p1.1`（事件 schema_version 不变），模式为 simulation／discussion；省略 mode 的旧入站仍为 simulation。配置采用同一 Scene 内的嵌套模式 schema。公共字段裁剪后以换行连接并沿用 background；换行也计入合计 2000 码点，避免前后端对总输入产生不同算法。

模板和本场快照新增显式 public_profile；讨论参与者的关注点与可空初始观点是本场私人配置。迁移 007 只增列／索引，旧模式默认 simulation、公开身份默认空，不从私人字段抽取；原请求快照不回填、不重写。模式创建后不可修改。

ContextBuilder 先调用可见性过滤，模板只拿公开名册、自己的私人快照与合法材料，不拿第三方私人配置。两种模板分别标记 `role_action@simulation.p1.1`、`role_action@discussion.p1.1`，共用服务端身份／行动／引用检查。Runner 只增加两个快照字段；Scheduler 无改动，也无模式专用引擎、自主唤醒或语义停止。

前端增加平级入口与各自表单，复用 ChatView／HistoryView；历史 mode 筛选和缓存按场景／视角隔离。事实统计从同一合法可见集合生成，角色只看自己的行动结果和本人可见消息，统计不调用模型、不回写运行。行为分析只增加现有能力的显式描述和推荐，两种模式均可手动使用；未添加高级 Analyzer。

主要代码：contracts/mode、scene、api、analysis、api_runtime 与注册／摘要；storage/migrations/007_dual_mode.sql、模板／场景仓储和服务；context/models、visibility、builder；runtime/runner 的两字段接线；api/scenes、templates、runtime；前端配置、共享聊天／历史、侧栏、分析抽屉与 RecordFacts。新增七份 `backend/tests/test_dm_*.py`（含 delivery）、前端 dm-ui 与分析用例；M07 新增有限观察脚本。生成文件全部由正式脚本生成。

开工前已有私聊修复和文档 WIP 单独保存到 `$TMPDIR/sceneweave-p1-baseline`；未提交／推送 Git，未修改原试用数据库、原运行服务、其它项目或系统服务。各模块的阶段结果追加在 M00～M07 原任务书／报告；历史模块状态及旧未验证项保留。

## 实际命令与证据

| 编号 | 工作目录／实际命令 | 退出码与真实结果 | 证据 |
|---|---|---|---|
| V1 | 根目录：删除三份生成产物和 frontend/dist 后 `scripts/export_contracts.sh` | 0；三个产物从零重建，重建前后 SHA256 完全相同 | dual-mode/generated-rebuild.json |
| V2 | backend：`PYTHONPATH=scripts .venv/bin/python -m pytest -p block_outbound_plugin -o addopts='' -q --junitxml=../state/reports/dual-mode/backend-regression.xml` | 0；709 passed，1 warning in 24.10s；XML 709 用例、0 failures、0 skipped | dual-mode/backend-regression.xml |
| V3 | frontend：`pnpm test && pnpm run typecheck && pnpm run build` | 0；7 文件、65 passed；tsc 0；Vite 48 modules，构建 581ms | dual-mode/verification.json；本报告原文摘要 |
| V4 | 根目录：`git diff --check`；`git diff --exit-code -- backend/role_theater/scheduling` | 均 0；Scheduler 差异为空；Runner diff 仅增加 mode、mode_config 的快照传递 | 最终工作区 diff |
| V5 | 独立 Mock 8013／5183，实际 IAB 浏览器操作 | 两模式单步4／3次，共7次；创建／查询／筛选／历史／角色切换后仍7次。宽1280无横溢出；窄390初次394，修复后390；第三方不显示原私聊正文、菜单或计数 | dual-mode/browser/evidence.json、home-wide.jpg及截图 |
| V6 | backend：`PYTHONPATH=scripts .venv/bin/python -m pytest -p block_outbound_plugin -o addopts='' -q tests/test_dm_delivery.py` | 0；13 passed in 1.52s。两模式2／3／5／8人实际单步、200 emoji正文；观察脚本成功后 TIMEOUT／UNKNOWN 仍退出4，缺配置退出3且无数据库 | test_dm_delivery.py，V2 XML |
| V7 | backend：`.venv/bin/python scripts/dual_mode_observation.py --live --turns 6 --output ../state/reports/dual-mode/live` | 0；三份独立样本共12次真实请求成功，12,272 tokens，单次最大1307；快照／实际输入、预算逐条吻合，最终均ENDED／无在途 | dual-mode/live-summary.json、live/20260929T023541502616Z/*/evidence.json |

离线回归阻断真实出站；仅回环假服务器需要沙箱之外的端口权限。第一次原样 M03 运行因 loopback socket.bind PermissionError 有6 failed／147 passed；允许回环后原命令153 passed，未降低测试。供应商调用只在 V7 的显式 --live 中发生；配置检查只打印 model_configured=true、credential_source=dotenv、analysis_enabled=false，不打印凭证。

重建核验包括空生成产物、空构建产物、独立新库、旧006副本逐列对比、重复迁移与故障回滚。反例包括非法配置／引用／身份、201正文、32001提示、超预算／token上界、private混选拒绝、提交故障、结果不明及观察脚本晚失败。配置矩阵使用 `_env_file=None` 与临时 dotenv；缺失／空值／占位值均实际执行，分析关闭和缺可选依赖分别验证。全量 XML 和静态标记检查无 skip／xfail，无删除原用例；历史迁移测试精确增加版本7，并以原列复制旧schema，保留原业务字段逐项比较；前端预算旧用例补足合法2名角色输入，保留原预算断言。

## 失败过程与修正

阶段失败不计入通过：M00／M01 初次误写不存在的测试文件退出4，随后修正文件名；旧版本／新增必填测试夹具按准确 schema 更新。M02 首跑2项失败，原因是公开名册名字渲染变化和旧测试 Row 缺少新字段；修正渲染和旧输入兼容。M04 新包装用例初次3项失败，原因是漏传故障阶段与游标字段名错误；修正并补齐提交阶段。前端先后发现旧夹具无 public_profile、无角色的旧提交、重复文本选择器与未用 import；准确补全夹具／断言对象后回归通过。窄屏真实394px溢出通过 facts dd 换行修复。

V6 首跑2 failed／9 passed，新增测试误将 RunStateView.status 写为 run_state；改为契约的准确字段后13 passed。汇总脚本曾误导入不存在模块退出1，删除误导入后真实证据汇总成功。重建时删除生成模块导致开发中的 Vite 两条预期 HMR 错误；完整重载后验证键盘导航／历史筛选／分析抽屉恢复。早期 fullPage 截图存在拼接失真，保留为过程记录；最终 home-wide.jpg 已视觉检查，响应式几何以 DOM 实测为准。

## G2 实际观察与限制

| 独立样本 | 请求／行动 | 观察与停止 |
|---|---|---|
| ordinary-simulation | 3成功，3 PASS，0私聊 | 普通室友情境；三位均沉默，NO_NEW_INFORMATION 后停止。不追加请求强迫对话 |
| ordinary-discussion | 3成功，3 PASS，0私聊 | 公共空间议题，三位初始观点均null；未生成观点或共识，NO_NEW_INFORMATION 后停止 |
| guided-discussion | 6成功，5 PRIVATE、1 PASS；4关联回复 | 明确私聊目标独立标识；预算6后结束。3组第三方实际输入核对均无原私聊正文、ID、会话ID |

实际返回模型均为 deepseek-flash；每次请求分别保存模板、参数、完整合法 Prompt、原输出、供应商请求ID、用量、落盘快照和预算，不保存凭证／认证头／reasoning_content。单次用量最大1307，未超过10,000,000；没有把三样本合计冒充单次验收。

G2证明上述有限样本的调用、合法行动和边界记录。普通样本全PASS说明这两份普通设定没有产生互动，不能声称自由对话丰富、观点演变或语义质量已通过。高级讨论分析、本次真实行为分析、长期容量、人工UX／行为质量、浏览器自动重连、异机部署／远端CI仍未验证；历史 M06 Q1/Q2 不关闭。原试用进程仍使用此前加载的代码，本轮没有切换服务；使用新功能需按项目启动流程重新启动当前工作区版本。

最后补强DM-P1-03给定初始观点的快照保持及DM-P1-04／13初始观点标记隔离；实际执行 `PYTHONPATH=scripts .venv/bin/python -m pytest -p block_outbound_plugin -o addopts='' -q tests/test_dm_runtime.py tests/test_dm_analysis.py tests/test_dm_storage.py` 退出0，68 passed in 3.85s。随后重跑V2保存最终XML。临时Mock后端退出0、Vite按Ctrl-C停止退出130；未留下测试监听服务。

16项映射见 docs/ACCEPTANCE.md 的双模式P1增量矩阵。本轮仅确认P1工程完成和有限G2观察，不改写历史质量结论。
