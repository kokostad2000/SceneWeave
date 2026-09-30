# 变更任务书：人物与本场设定分离

## 需求

唯一需求来源：PRD.md 第 1.5、3.2～3.4、4.1、10.3 节。用户已授权「修订 PRD 后进行开发」。本增量 SR-01～12 工程核验通过；实际命令／有限真实观察及未验证项见 [实施报告](../state/reports/CHANGE-scene-role-profile.md)。旧 PC／DM 证据保留。

## 目标

新界面复用人物名称及标识，所有行为设定在本场配置；预置场景复制自身设定。版本 1 兼容旧调用与历史，版本 2 不自动继承。保持一个 SceneService、ContextBuilder、Runner 和 Scheduler。

## 规范

- 开工基线为当前未提交私聊／双模式 WIP；源文件副本与摘要位于 $TMPDIR/sceneweave-scene-role-baseline，不覆盖既有改动，不提交／推送。
- 使用 role_profile 结构化五类文本，空值保留；Scene.configuration_version=1／2，迁移仅增加该列默认 1。新模板创建仅名称也合法，旧字段保留；新界面不编辑全局行为文字。
- 版本 1 请求带 role_profile 拒绝；新界面显式使用版本 2。版本 2 预设配置直接来自 PresetScene；完整快照落库后不读取动态目录。
- 新本场更新接口仅接受版本 2 且未锁定场景，更新全量 role_profile；discussion_config 省略保留、显式空配置清空。配置修改不调用模型。
- 两模式共用权限过滤；新 Prompt 版本为 role_action@simulation.sr.1／discussion.sr.1，旧模板 p1.1 保留。Runner 仅接线配置版本；Scheduler 文件不得修改。
- M00→M01→M02→M03→M04→M05→M06→M07 串行；各模块开始前追加任务／报告，独立完成重建、反例、越界、相关环境矩阵，实际命令／退出码写入报告。M03／M06原则上只回归。
- M00：契约／注册／生成／合法非法边界；M01：创建、预设、更新、迁移、快照隔离；M02：渲染／权限／调度比较；M03：参数、失败与 token 上界；M04：派发快照、锁定／恢复；M05：目录／本场表单、历史、浏览器；M06：分析隔离与可选依赖；M07：完整回归与 SR Gate／真实观察／服务切换。
- 原实际请求快照不重写；旧库只先在备份副本验证。服务切换前确认无在途请求、备份业务库、对比原字段；继续已有 real provider 配置，不读取／打印密钥。
- 测试：backend 内 PYTHONPATH=scripts .venv/bin/python -m pytest -p block_outbound_plugin -o addopts='' -q；frontend 内 pnpm test／pnpm run typecheck／pnpm run build；生成只能 scripts/export_contracts.sh。
- 真实观察单独显式 --live，独立证据库，限量调用；输入与输出用量走已有上界检查。质量、长期容量及历史 M06 Q1/Q2 保持独立未验证项。
