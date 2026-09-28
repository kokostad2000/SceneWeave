# v0.1.0 首版交付收尾与使用观察

状态：三项交付工作已核验完成；基线为带已知限制的本机试用版，M06 缺陷与人工质量验收保持开放。任务书：`tasks/FIRST-RELEASE.md`。

## 范围与初始事实

- 起始 HEAD：`48a63eb86c89b7332d7e3080402f0ac2b6cdaf1b`，工作树干净；main 比当前 origin/main 跟踪引用超前 1 个提交，未 fetch，不据此宣称远端实时状态。
- 前后端版本均已为 0.1.0。后端锁文件实际 37 包；可选 behavior-psychology 2.1.0 已在项目虚拟环境安装。
- README 的“不可试用”、423 项测试、分析依赖未安装等口径过时；STATUS 已记录最新 452/7/49 与迁移 004。
- 本轮开始时受限环境的 8002/5175 健康请求不可达；获准回环访问后两端均 HTTP 200，配置来源 dotenv、分析开启、版本 0.1.0。本轮不重启服务，受限连接失败不能证明进程退出。
- 本轮只做 M07 交付维护：脚本、测试和资料；不修改产品运行代码、上游仓库、系统服务或 Git 历史。

## 实际命令与结果

命令从 `backend/` 或 `frontend/` 执行，归档／文档核对从仓库根执行。日志／JUnit 与汇总为 `state/reports/release-checks-2026-09-28/`。

| 检查／实际命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest tests/test_m07_usage_observation.py -p scripts.block_outbound_plugin -p no:cacheprovider -r a --tb=short`（首轮） | 0 | 3 passed，全部 Mock |
| 基线与观察两个测试文件合跑（首轮） | 0 | 6 passed；随后补 UNKNOWN 统计反例，最终新增共 7 项 |
| 完整 `pytest -p scripts.block_outbound_plugin -p no:cacheprovider -r a --tb=short`（受限沙箱） | 1 | 453 passed、6 failed，均为回环假服务绑定 PermissionError；保留 `backend.xml` 与 `backend.log` |
| 同一完整命令（获准回环绑定，仍阻断外网） | 0 | **459 passed**，0 skipped/xfail；`backend-verified.xml` 与日志 |
| 可选 `tests_optional/test_external_upstream.py`，同样阻断插件 | 0 | **7 passed**，假 SDK；`optional.xml` 与日志 |
| `pnpm run test` | 0 | **49 passed**，6 文件；`frontend.log` |
| `pnpm run build`（内含 typecheck） | 0 | TypeScript 与 Vite 构建通过；`build.log` |
| `bash scripts/export_contracts.sh` | 0 | 三项契约重建；应用及生成物与 HEAD 无差异 |
| `observe_usage.py --live --rounds 2 --out ../state/reports/usage-2026-09-28`（受限环境、首版脚本） | 0（脚本判定缺陷） | 18 次 UNKNOWN_REQUEST、确认发送 0、预算占用 18、用量未知，无成功样本；原证据保留，**不计通过** |
| 修正 UNKNOWN 汇总、首个供应商失败停止、失败非零；再运行 `--out ../state/reports/usage-2026-09-28-live`（获准联网） | 0 | **6 会话、84 角色请求成功、6 分析 NORMAL、95,490 tokens**；原文见该目录与 `docs/USAGE_OBSERVATION.md` |
| 本机 8002/5175 健康只读请求（获准回环访问） | 0 | 两端 HTTP 200，仅输出安全状态字段 |
| 对试用库 SQLite backup API＋integrity_check＋表计数／迁移核对 | 0 | `state/backups/v0.1.0-live-trial-20260928.db`；4 场景、25 消息、25 行动、2 分析，迁移 1～4、integrity ok |

不把首次脚本退出 0 当作真实验收成功；新增 UNKNOWN 反例后，脚本失败返回 4，失败即停止后续供应商请求。
首次两条测试命令还曾因日志目录未建而退出 1，未运行测试；建立目录后真实执行以上命令。

## 使用观察结论

六份完整原文已逐份阅读。角色关注点与说话长度有可辨差异，出现 3 次合法 PASS；定向事件均只在目标视角可见。
分析六次 NORMAL 中，两份室友标签与安然主动发起行为矛盾，列 **F1/P1**；沉默收束、事件语义影响与生成额外事实列 F2～F4/P2，统计展示列 F5/P3。
完整定位、建议与 token／耗时见 `docs/USAGE_OBSERVATION.md`。代理判断不替代人类质量验收。

## 工作区边界

本轮期间另一个人工授权的分析定位工作更新了 `tasks/M06.md`、`state/STATUS.md` 并创建自己的脚本／报告／假样本。
这些文件不属于本轮实现，不改动其内容或结论；只在 STATUS 保留该工作条目。基线仅纳入已跟踪源码和本轮明确列出的交付增量，
另一项工作的报告与两份真实证据作为限制说明保存，不将其脚本或假样本计入本轮通过项。
该工作已发现 Q1/Q2、M06 退回进行中；README／发布／验收已同步，未恢复为已验收。全量核验以当前已跟踪应用代码和本轮七个新用例为范围。

## 冻结、恢复与重建

先生成候选源码归档（210 个普通文件，SHA-256 `a53609908829196ac620d4723b6b77e5ebcb6b0559ad751490f216305f5488c6`），
逐文件校验、恢复至独立目录。随后补齐最新限制／恢复记录，最终归档和清单放在 `state/releases/v0.1.0/`；
最终逐文件校验记录由同目录 `final-verification.json` 保存，不覆盖被冻结的源文件。

| 实际恢复核验 | 退出码 | 结果 |
|---|---:|---|
| `freeze_release.py freeze --out state/releases/v0.1.0-candidate`；`restore <候选归档> state/restores/v0.1.0-candidate` | 0／0 | 源码逐文件 SHA-256 全部相同；拒绝凭证、数据库、缓存、日志、软链接和路径穿越 |
| 恢复目录 `uv sync --dev --locked --offline --python <原 Python>`，项目内 UV_CACHE_DIR | 0 | **新建**独立虚拟环境，按锁文件装包；非复制旧 .venv。首次日志相对路径错误退出 1，未安装，改为绝对路径后完成 |
| 恢复目录首次 `pnpm install --frozen-lockfile --offline` | 130（主动中止） | 缓存不齐，registry 元数据出现 ENOTFOUND 重试；不计安装通过 |
| `pnpm install --frozen-lockfile --store-dir <项目>/.cache/pnpm-store`（获准联网） | 0 | 恢复目录新建 node_modules，未复制旧安装；8.1 秒 |
| 首次恢复完整后端回归（末级目录为版本号） | 1 | 458 passed、1 failed：既有断言要求 REPO_ROOT.name 为 SceneWeave；未删除测试或放宽断言 |
| 再恢复至 `state/restores/v0.1.0-validation/SceneWeave`，重新 uv／pnpm 锁定离线安装 | 0／0 | 两边独立安装完成；前端缓存已齐，离线安装 1.5 秒；实际恢复说明保留正确末级目录名 |
| 在新恢复目录**删除三个契约产物**后执行唯一 `scripts/export_contracts.sh` | 0 | 全部重建，三个 SHA-256 与原始基线完全相同；`restored-contracts.json` |
| 新恢复目录完整后端回归（允许回环、阻断外网） | 0 | **459 passed**，0 skip／xfail；`restored-named-backend.xml` |
| 新恢复目录 `pnpm run test`、`pnpm run build` | 0／0 | **49 passed**，类型检查通过，Vite 从零生成 dist |
| 独立恢复试用库备份，用恢复源码以 Mock／分析关闭启动；读健康与历史 | 0 | HTTP 200／200，迁移无需重复；4 场景／25 消息／25 行动／2 分析完整保留、integrity ok；未新增供应商请求。`data-restore.json` |

本轮源代码与迁移仍与提交 `48a63eb` 相同；三项契约哈希见 `restored-contracts.json`，
依赖锁及每个文件／迁移哈希见最终 `manifest.json`，源码归档校验值见 `SHA256SUMS`。
数据库备份校验值 `b7edf5b15a5258ff09f9ee41869c31a276c083c53ef9784ec97752132df1b524`，
运行数据保持独立，未混入源码包。

## 核验结论与交付物

- C1 **资料一致性**：当前 459／7／49、版本 0.1.0、分析依赖已安装、迁移 004、M06 进行中及语义限制，在 README／STATUS／ACCEPTANCE／RELEASE 对齐；历史记录未倒改。
- C2 **可追溯、可恢复基线**：应用提交、依赖锁、迁移／文件清单、源码归档、恢复说明齐备；独立安装、产物从零重建、恢复目录回归与数据库恢复均已实际执行。
- C3 **使用观察**：三场景各两会话的原文、角色差异、具体回应、沉默、分析价值、耗时和 token 已记录；五条反馈按 P1／P2／P3 排序并定位原文。
- C4 **反例与边界**：新测试涵盖 UNKNOWN、无 live、PASS／空材料、定向隔离、篡改／路径穿越／覆盖；基础及恢复回归无 skip／xfail；未删除既有测试或放宽断言；真实采集单列，未自动放进 CI。

三项工作完成不等于项目全部验收通过。**下一项优先工作为 M06 标签证据约束修复及固定样本复测**，不以正常状态抵消语义问题；本轮不实现该新任务。

## 未验证项

人工对话质量及视觉结论、浏览器 EventSource 自动重连、长期运行、异机部署、真实本地推理服务、90 秒真实供应商超时、远端 CI、PRD S1-S9 原始地址。新代理观察不关闭人工验收。
