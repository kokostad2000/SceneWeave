# 分析定位取证脚本异常 JSON 修复

日期：2026-09-28。状态：已完成（取证脚本 P2 崩溃修复；M06 仍进行中）。用户授权：设计方案后修复。

## 1. 问题与范围

原脚本对 `parsed_content` 直接调用 `.get()`，只验证了 JSON 语法，未验证顶层与 tags
类型。离线注入 `["unexpected"]` 已复现：上游及项目 API 返回 DEGRADED，脚本却抛出
AttributeError，当前样例缺少 engineering_checks，整批没有汇总结论。

本轮只修改取证脚本、增加基础／可选上游测试，并同步任务／状态／本报告。
不修改业务 API、契约、前端或只读上游；保留已有工作区修改与历史取证文件。
属于 M06 取证修复，没有跨模块业务影响。

## 2. 修复方案

1. 保留原始 content 和解析结果；解析失败只记录固定错误码，不记录异常文本。
2. 标签差异计算前校验：顶层对象、tags 列表、每项字符串。空列表（tags=[]）合法；
   缺失／错误字段类型明确登记，不转换为成功的空标签。
3. tag_trace 记录结构错误；异常时 removed_by_normalization=null，表示无法比较。
   新增工程检查，异常样例判失败；API／上游的原状态与降级标记保持原样。
4. 每例仍保存隔离、预算、用量、持久化检查，完成所选固定样例后保存汇总并退出 1。
   不补发或隐式重试。完成时取消 atexit 保存回调，避免完成文件被退出回调重复写入。
5. 基础测试不需要外部分析包；可选测试经现有适配层加载锁定上游，使用假 SDK
   验证异常响应到项目 API 与取证文件的完整路径。

## 3. 实际命令与结果

以下 Python 命令均在 `backend/` 执行，退出码来自本轮实际执行。

| 编号 | 实际命令 | 退出码 | 结果 |
|---|---|---:|---|
| R1 修复前反例 | `PYTHONPATH=.:scripts .venv/bin/python -m pytest tests_optional/test_analysis_localization.py::test_malformed_tags_preserve_evidence_and_complete_all_cases -p block_outbound_plugin -p no:cacheprovider -r a --tb=short` | 1 | **1 failed**；原第 247 行 `AttributeError: 'list' object has no attribute 'get'`，0.99 秒；失败保留，不计通过 |
| R2 新增测试 | `PYTHONPATH=.:scripts .venv/bin/python -m pytest tests/test_m06_localization.py tests_optional/test_analysis_localization.py -p block_outbound_plugin -p no:cacheprovider -r a --tb=short` | 0 | **20 passed**，2.56 秒 |
| R3 针对性回归 | `PYTHONPATH=.:scripts .venv/bin/python -m pytest tests/test_m06_localization.py tests/test_m06_analysis.py tests/test_m06_boundary.py tests/test_m06_api.py tests/test_model_analysis_contract.py tests_optional/test_analysis_localization.py tests_optional/test_external_upstream.py -p block_outbound_plugin -p no:cacheprovider -r a --tb=short` | 0 | **94 passed**，3.85 秒；含既有 74 项及新增 20 项，无 skipped／xfail |
| R4 独立重跑 | `PYTHONPATH=. .venv/bin/python scripts/analysis_localization.py --output /private/tmp/sceneweave-localization-fixed-01a0e5e8.json` | 0 | 六例工程检查全部通过，4 NORMAL／2 DEGRADED，6 次假 SDK 请求；每次假用量 100 输入＋50 输出，结构错误均为 null |
| R5 反例／越界扫描（仓库根） | `rg -n -e skip -e xfail -e 'import src' -e 'from src' backend/tests/test_m06_localization.py backend/tests_optional/test_analysis_localization.py backend/scripts/analysis_localization.py` | 1 | 无匹配；未新增 skip／xfail 或直接导入外部 src |
| R6 空白检查（仓库根） | `git diff --check` | 0 | 已跟踪修改无空白错误；新增文件另做 no-index 空白检查 |

新增文件分别执行 `git diff --no-index --check -- /dev/null <文件路径>`，均退出 1
（新文件与 /dev/null 存在差异），空白错误输出均为空：
`backend/scripts/analysis_localization.py`、`backend/tests/test_m06_localization.py`、
`backend/tests_optional/test_analysis_localization.py`、`state/reports/FIX-analysis-localization.md`。

R1～R4 均出现 1 条既有 Starlette 弃用警告，未新增警告。R4 的 JSON 为本轮临时
重建文件，不复用或覆盖历史 fake／live 证据。

### 核验结论

- **V1 重建**：R2／R3 的每个集成测试从不存在的输出路径、新临时 SQLite 库创建
  场景与记录；R4 用全新路径从零执行 CLI，六例完成，不使用旧 JSON 结果。
- **V2 反例**：先通过 R1 在原脚本复现，再用同一断言通过 R2／R3；新增基础测试
  16 项覆盖数组（空／非空）、字符串、数值、布尔、null、缺失 tags、null／字符串／
  对象 tags、混合及嵌套数组、合法空列表、归一化标签差异、解析失败及上游结果缺失。
  可选集成测试 4 项验证实际锁定上游的降级、非法 JSON、正常六例与整批结果。
  异常首例之后所有指定样例仍完整保存；整批 engineering_passed=false、退出 1，
  同时保持 API DEGRADED、原始 content／解析值、实际假用量与剧情隔离检查。
- **V3 越界**：R1～R3 由 `block_outbound_plugin` 阻断外部 DNS／连接；R4 使用脚本
  默认假 SDK，角色行动也是 Mock。被测应用以 `_env_file=None` 和非真实占位凭证装配，
  未打印或写入真实凭证；
  未修改业务、契约、前端、上游、其它项目、系统或 Git 历史，未放宽原测试断言。
- **V4 配置矩阵**：R3 包含既有 `test_optional_analysis_configuration_matrix`，
  无凭证（None）、空字符串、空白字符串均禁用，非真实占位凭证启用，全部通过。
  新增 16 项基础测试不调用 `build_upstream_port`，不要求可选上游；可选集成测试
  显式位于 tests_optional，经唯一现有外部适配层加载。未更改配置／依赖逻辑。

修改文件：`backend/scripts/analysis_localization.py`、
`backend/tests/test_m06_localization.py`、`backend/tests_optional/test_analysis_localization.py`、
`tasks/M06.md`、`state/STATUS.md`、本报告。已有未提交任务修改及历史证据保留。

**结论**：V1～V4 通过，本 P2 取证崩溃已修复；异常结构会明确判失败，合法空标签
仍按原行为处理。仅修复原始标签取证类型边界，不将标签结构校验当作完整模型响应
契约或语义质量验收；其它响应字段由原锁定上游与项目适配层校验。

## 4. 未验证项与后续条件

真实供应商未复测：本问题用确定性非法响应验证，普通测试不调用外部供应商。
本轮未重跑完整后端、前端或构建：改动集中于取证脚本，相关分析回归已实际执行。
既有 Q1（材料不足仍贴趋势标签）／Q2（无依据附加标签）不在本修复范围，继续待修复。
36 次阶段验收、人工语义／视觉复核、长期稳定性仍未验证，详见原定位报告。
本脚本修复通过后关闭该 P2 崩溃；M06 保持进行中，不据此进入 M07 或宣称语义质量通过。
