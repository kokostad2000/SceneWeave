# SceneWeave 本机试用质量观察表

本表用于 `PRD.md` 第 10 节要求的人工观察。每个预置场景各运行三次，共九份真实模型样本。
样本文件由 `live_integration.py --quality-only` 保存到 `state/reports/live/`；
记录会话原文和异常，不用 Mock 样本推断真实模型质量。

观察者逐份阅读 JSON 中的 `timeline` 与 `actions`（`PASS` 是合法的沉默，
不会产生公开消息）；便利店第 1 份由同名 `.db` 中的 `scene_turns` 确认
`PASS／PASS／SPEAK`，该早期 JSON 尚无 `actions` 字段。对下列问题填写
“是／否／不确定”和具体序号：

1. 角色是否回应了前文的具体内容，而非只泛泛接话？
2. 不同角色的关注点与表达方式是否有可辨差异？
3. 是否泄露了没有提供给该角色的具体私有事实？
4. 是否反复使用礼貌套话或重复已经说过的内容？
5. 是否允许沉默、拒绝或结束话题，而非强制每次发言？

| 预置场景 | 真实样本 | 行动（SPEAK／PASS） | 公开消息 | 人工观察结论 |
|---|---|---|---:|---|
| 三个室友的客厅 | [第 1 次](../state/reports/live/quality-roommates-1.json) | S／S／S | 3 | 待填写 |
| 三个室友的客厅 | [第 2 次](../state/reports/live/quality-roommates-2.json) | S／S／S | 3 | 待填写 |
| 三个室友的客厅 | [第 3 次](../state/reports/live/quality-roommates-3.json) | S／S／S | 3 | 待填写 |
| 深夜便利店的三个顾客 | [第 1 次](../state/reports/live/quality-convenience-store-1.json) | P／P／S | 1 | 待填写 |
| 深夜便利店的三个顾客 | [第 2 次](../state/reports/live/quality-convenience-store-2.json) | P／P／P | 0 | 待填写 |
| 深夜便利店的三个顾客 | [第 3 次](../state/reports/live/quality-convenience-store-3.json) | P／S／S | 2 | 待填写 |
| 周末露营地的三个人 | [第 1 次](../state/reports/live/quality-campsite-1.json) | S／S／S | 3 | 待填写 |
| 周末露营地的三个人 | [第 2 次](../state/reports/live/quality-campsite-2.json) | S／S／S | 3 | 待填写 |
| 周末露营地的三个人 | [第 3 次](../state/reports/live/quality-campsite-3.json) | S／S／S | 3 | 待填写 |

初步异常提示（供人工判断，不计作人工结论）：便利店第 2 次三人均沉默，
无法从这份样本判断具体回应或角色差异；便利店第 1 次旧版脚本因误要求
“三人都发言”退出 4，但数据库记录三次请求均成功，已修正脚本并保留原始证据。
露营地第 3 次只有两名角色发言，第三条仍是何澜的回应。

观察者：________　日期：________　总体结论（可试用／需修改／不确定）：________

逐条异常请注明：**样本文件、消息序号、观察到的现象、是否影响本机试用**。
“不确定”不得自动记为通过。质量观察完成后，把人工结论与日期写入验收记录；
自动计数和离线测试只提供辅助证据。
