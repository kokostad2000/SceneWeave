# SceneWeave v0.1.0 基线与恢复

版本：**v0.1.0，本机单用户试用版**。前后端及 OpenAPI 均为 0.1.0。
应用代码对应提交 `48a63eb86c89b7332d7e3080402f0ac2b6cdaf1b`；本轮交付脚本、测试和资料作为
工作树增量随源码快照一起冻结。该快照在 Git 提交前生成，后续提交不改写原归档；未创建版本标签。

## 冻结内容

- 源码归档：`state/releases/v0.1.0/SceneWeave-v0.1.0-source.tar.gz`。
- 逐文件清单：同目录 `manifest.json`；归档内亦有 `RELEASE-MANIFEST.json`。
- 归档与清单 SHA-256：同目录 `SHA256SUMS`。清单记录应用源码指纹、依赖锁、每个迁移的校验值。
- 后端：`backend/uv.lock`（37 包，含可选分析）；前端：`frontend/pnpm-lock.yaml`。
- SQLite 迁移：001 初始数据、002 运行事件、003 分析记录、**004 场景级调度计数**。
- 可选分析上游固定提交：`bd1e8fa97b395223d629539022fbd92e1a5429d7`。
- 已知限制和验收边界随 [RELEASE.md](RELEASE.md)、[ACCEPTANCE.md](ACCEPTANCE.md) 一同冻结。

归档、数据库备份和恢复目录属于本机产物，不随 Git 推送。GitHub 提供源码、冻结脚本和对应证据。
新克隆可先执行 `backend/.venv/bin/python scripts/freeze_release.py freeze --out state/releases/v0.1.0`，
再按下文校验／恢复；新快照记录该克隆的 HEAD，其校验值与历史本机归档分别记录。

归档排除真实凭证、运行数据库／备份、日志、缓存、依赖安装目录和 Git 元数据。
虚构测试样本属于证据；不把日常数据库默认装入新环境。数据恢复须使用单独 SQLite 备份。

## 校验与源码恢复

在仓库根执行；恢复目录必须尚不存在，并位于本项目内：

```bash
backend/.venv/bin/python scripts/freeze_release.py verify \
  state/releases/v0.1.0/SceneWeave-v0.1.0-source.tar.gz
backend/.venv/bin/python scripts/freeze_release.py restore \
  state/releases/v0.1.0/SceneWeave-v0.1.0-source.tar.gz \
  state/restores/v0.1.0/SceneWeave
```

恢复逐文件核对 SHA-256；拒绝篡改、路径穿越、软链接和覆盖已有目录。
现有配置测试要求仓库末级目录名为 `SceneWeave`，恢复时按上述目录结构保留此名称；不放宽该断言。
恢复后在新目录按照 README 以锁文件安装依赖，不复制旧虚拟环境或 node_modules：

```bash
cd state/restores/v0.1.0/SceneWeave/backend
uv sync --dev --locked
# 需要分析再安装：uv sync --extra analysis --dev --locked
cd ../frontend
pnpm install --frozen-lockfile
```

重新生成契约须使用恢复目录的 `scripts/export_contracts.sh`；启动仍为回环地址、单 worker。
数据库第一次启动从 001～004 建立，已有库只追加缺失迁移；已执行迁移校验不一致会拒绝启动。

## 数据备份与恢复

对运行库使用 SQLite backup API 或项目 `scripts/backup_db.sh`，不直接复制活跃 WAL 主文件。
恢复前停止使用目标库的服务，先保存旧库，再将备份放到配置指定位置。
本轮本机试用库的独立备份及完整性、表计数、迁移核对结果写入首版报告；凭证需自行配置，不能由归档恢复。

## 基线判定

本轮实际冻结／恢复／重建命令及退出码见
[FIRST-RELEASE-2026-09-28.md](../state/reports/FIRST-RELEASE-2026-09-28.md)。
基线证明所列源码与数据可恢复，不证明人工质量验收、浏览器重连、长期运行、异机部署或公网可用。
行为分析定位已发现 Q1/Q2，M06 当前进行中；定位报告与本轮 F1 反馈不能自动视为首版质量验收通过。
