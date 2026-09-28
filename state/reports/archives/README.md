# 历史离线测试证据归档

## 2026-09-28

归档：[test-evidence-2026-09-28.zip](test-evidence-2026-09-28.zip)。
用户授权将十份未跟踪的测试产物归档、核验后移除散文件，并更新报告引用。

- 10 份原始文件：801,144 字节；ZIP：82,862 字节。
- ZIP SHA-256：`240ed5c2b016b76e021454626d62e12fd21e1fa7aeba571bb1e3b173de023422`。
- 包内另有 `MANIFEST.json`，记录每份文件的原始仓库相对路径、字节数与 SHA-256。
- 创建后实际核验 ZIP CRC、成员清单及全部文件哈希，并恢复到独立临时目录，
  与来源逐文件按字节比较，10/10 一致，命令退出 0。移除散文件前再次核对来源哈希。

### 包内文件

成员路径保持原仓库相对路径，原始内容完整保留。

| 目录前缀 | 文件 |
|---|---|
| `state/reports/live/` | `analysis-localization-20260928-fake.json` |
| 同上 | `analysis-localization-20260928-fake2.json` |
| 同上 | `analysis-localization-20260928-fake5.json` |
| 同上 | `analysis-localization-20260928-fake6.json` |
| 同上 | `analysis-localization-20260928-retest-fake.json` |
| `state/reports/release-checks-2026-09-28/` | `backend-verified.xml` |
| 同上 | `backend.xml` |
| 同上 | `optional.xml` |
| 同上 | `restored-backend.xml` |
| 同上 | `restored-named-backend.xml` |

原始失败记录与成功记录一并保存；对应结果与解释见
[分析定位报告](../ANALYSIS-LOCALIZATION-2026-09-28.md)和
[首版交付报告](../FIRST-RELEASE-2026-09-28.md)。
已跟踪的两份真实定位 JSON、其他真实调用证据、原测试日志及汇总仍保存在各自原目录。

### 核验与恢复

在仓库根执行 CRC 核验：

```bash
backend/.venv/bin/python -m zipfile -t state/reports/archives/test-evidence-2026-09-28.zip
```

逐文件清单核验：

```python
from pathlib import Path
import hashlib
import json
import zipfile

archive = Path("state/reports/archives/test-evidence-2026-09-28.zip")
assert hashlib.sha256(archive.read_bytes()).hexdigest() == "240ed5c2b016b76e021454626d62e12fd21e1fa7aeba571bb1e3b173de023422"
with zipfile.ZipFile(archive) as bundle:
    assert bundle.testzip() is None
    manifest = json.loads(bundle.read("MANIFEST.json"))
    assert manifest["file_count"] == len(manifest["files"]) == 10
    assert set(bundle.namelist()) == {row["path"] for row in manifest["files"]} | {"MANIFEST.json"}
    for row in manifest["files"]:
        content = bundle.read(row["path"])
        assert len(content) == row["size_bytes"]
        assert hashlib.sha256(content).hexdigest() == row["sha256"]
print("10 个原始文件的 CRC、字节数与 SHA-256 全部通过")
```

恢复示例：向一个新的目录解压，即可按包内原始路径读取各份证据。

```bash
backend/.venv/bin/python -m zipfile -e state/reports/archives/test-evidence-2026-09-28.zip /private/tmp/sceneweave-test-evidence-restore
```
