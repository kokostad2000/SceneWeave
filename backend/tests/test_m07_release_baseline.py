"""源码恢复必须拒绝篡改、路径穿越及覆盖现有目录。"""

import importlib.util
import io
import json
import tarfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("freeze_release", Path(__file__).resolve().parents[2] / "scripts/freeze_release.py")
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)


def archive_at(tmp_path, *, payload=b"print('restored')\n", tamper=False, unsafe=False):
    archive = tmp_path / "source.tar.gz"
    manifest = {"version": "0.1.0", "source_commit": "fixture-commit", "files": {
        "backend/app.py": {"sha256": baseline.digest(payload), "size": len(payload), "mode": 0o644},
    }}
    with tarfile.open(archive, "w:gz") as tar:
        for name, data in {
            "RELEASE-MANIFEST.json": json.dumps(manifest).encode(),
            "backend/app.py": b"changed" if tamper else payload,
        }.items():
            path = f"{baseline.ARCHIVE_ROOT}/{name}"
            if unsafe and name == "backend/app.py":
                path = f"{baseline.ARCHIVE_ROOT}/../../outside.py"
            info = tarfile.TarInfo(path)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return archive


def test_baseline_restores_exact_bytes_and_refuses_existing_destination(tmp_path):
    archive = archive_at(tmp_path)
    target = tmp_path / "restored"
    result = baseline.restore(archive, target, root=tmp_path)
    assert result["verified"] and result["restored"]
    assert (target / "backend/app.py").read_bytes() == b"print('restored')\n"
    with pytest.raises(ValueError, match="尚不存在"):
        baseline.restore(archive, target, root=tmp_path)
    with pytest.raises(ValueError, match="项目内"):
        baseline.restore(archive, tmp_path.parent / "outside", root=tmp_path)


@pytest.mark.parametrize("unsafe", [False, True])
def test_baseline_rejects_corruption_or_path_traversal_without_writes(tmp_path, unsafe):
    archive = archive_at(tmp_path, tamper=not unsafe, unsafe=unsafe)
    target = tmp_path / "restored"
    with pytest.raises(ValueError):
        baseline.restore(archive, target, root=tmp_path)
    assert not target.exists()
