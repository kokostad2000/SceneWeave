"""在项目内冻结、校验和恢复源码基线；不写入 Git、不包含运行数据库。"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import subprocess
import tarfile
import tomllib
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.0"
ARCHIVE_ROOT = f"SceneWeave-v{VERSION}"
EXTENSIONS = {".md", ".py", ".json", ".toml", ".lock", ".yaml", ".ts", ".tsx", ".css", ".html", ".sql", ".sh"}
EXCLUDED_PARTS = {".git", ".venv", "node_modules", "__pycache__", ".cache", "dist", "backups", "releases"}
DELIVERY_ADDITIONS = (
    "backend/scripts/block_outbound_plugin.py", "backend/scripts/observe_usage.py",
    "backend/tests/test_m07_release_baseline.py", "backend/tests/test_m07_usage_observation.py",
    "scripts/freeze_release.py", "docs/BASELINE.md", "docs/USAGE_OBSERVATION.md",
    "tasks/FIRST-RELEASE.md", "state/reports/FIRST-RELEASE-2026-09-28.md",
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def selected_paths(root: Path) -> list[str]:
    raw = subprocess.check_output(
        ["git", "ls-files", "--cached", "-z"], cwd=root,
    )
    additions = [name for name in DELIVERY_ADDITIONS if (root / name).is_file()]
    for directory in ("state/reports/usage-2026-09-28", "state/reports/usage-2026-09-28-live",
                      "state/reports/release-checks-2026-09-28"):
        additions.extend(str(path.relative_to(root)) for path in (root / directory).glob("*.json"))
    # STATUS 引用的另一项工作仅留阶段说明，不把其未完成脚本／假样本装入基线。
    for path in root.glob("state/reports/ANALYSIS-LOCALIZATION-2026-09-28.md"):
        additions.append(str(path.relative_to(root)))
    for name in ("analysis-localization-20260928-live.json", "analysis-localization-20260928-retest-live.json"):
        path = root / "state/reports/live" / name
        if path.is_file():
            additions.append(str(path.relative_to(root)))
    selected = []
    for name in raw.decode().split("\0") + additions:
        if not name:
            continue
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or set(path.parts) & EXCLUDED_PARTS:
            continue
        if any(part.startswith(".env") for part in path.parts) and name != ".env.example":
            continue
        if path.parts[0] == "state" and not name.startswith("state/reports/") and name != "state/STATUS.md":
            continue
        if path.suffix not in EXTENSIONS and name not in {".gitignore", ".env.example"}:
            continue
        file = root / name
        if file.is_symlink() or not file.is_file():
            raise ValueError(f"源码条目不是普通文件：{name}")
        selected.append(name)
    return sorted(set(selected))


def freeze(root: Path, output: Path) -> dict:
    root, output = root.resolve(), output.resolve()
    if not output.is_relative_to(root) or output == root:
        raise ValueError("基线产物必须位于项目内的独立目录")
    if output.exists() and any(output.iterdir()):
        raise ValueError("基线目录非空；禁止覆盖已冻结基线")
    backend_version = tomllib.loads((root / "backend/pyproject.toml").read_text())["project"]["version"]
    frontend_version = json.loads((root / "frontend/package.json").read_text())["version"]
    api_version = json.loads((root / "backend/openapi.json").read_text())["info"]["version"]
    if {backend_version, frontend_version, api_version} != {VERSION}:
        raise ValueError("前后端／OpenAPI 版本必须一致为 0.1.0")
    paths = selected_paths(root)
    files = {name: (root / name).read_bytes() for name in paths}
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    timestamp = int(subprocess.check_output(["git", "show", "-s", "--format=%ct", "HEAD"], cwd=root, text=True))
    code = [name for name in paths if name.startswith(("backend/role_theater/", "frontend/src/"))]
    code_matches_head = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", "backend/role_theater", "frontend/src"], cwd=root,
    ).returncode == 0
    if not code_matches_head:
        raise ValueError("应用代码已变化；须重新确认首版提交与核验结果后才能冻结")
    manifest = {
        "format_version": 1, "version": VERSION, "source_commit": head,
        "source_commit_epoch": timestamp, "application_matches_source_commit": code_matches_head,
        "snapshot_kind": "source commit plus current delivery scripts, tests and documentation",
        "code_sha256": digest(json.dumps({name: digest(files[name]) for name in code}, sort_keys=True).encode()),
        "dependency_locks": {name: digest(files[name]) for name in ("backend/uv.lock", "frontend/pnpm-lock.yaml")},
        "database_migrations": {name: digest(data) for name, data in files.items() if name.endswith(".sql") and "/migrations/" in name},
        "excluded": ["credentials except empty .env.example", "runtime databases and backups", "logs", "caches", "Git metadata"],
        "known_limits_document": "docs/RELEASE.md", "restore_document": "docs/BASELINE.md",
        "files": {name: {"sha256": digest(data), "size": len(data),
                         "mode": 0o755 if (root / name).stat().st_mode & 0o111 else 0o644}
                  for name, data in files.items()},
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"SceneWeave-v{VERSION}-source.tar.gz"
    with archive.open("wb") as destination:
        with gzip.GzipFile(filename="", fileobj=destination, mode="wb", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as tar:
                for name, data in {**files, "RELEASE-MANIFEST.json": manifest_bytes}.items():
                    info = tarfile.TarInfo(f"{ARCHIVE_ROOT}/{name}")
                    info.size = len(data)
                    info.mode = manifest["files"].get(name, {}).get("mode", 0o644)
                    info.mtime = timestamp
                    tar.addfile(info, io.BytesIO(data))
    (output / "manifest.json").write_bytes(manifest_bytes)
    (output / "SHA256SUMS").write_text(
        f"{digest(archive.read_bytes())}  {archive.name}\n{digest(manifest_bytes)}  manifest.json\n",
    )
    return verify(archive)


def read_archive(archive: Path) -> tuple[dict, dict[str, bytes]]:
    contents = {}
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            path = PurePosixPath(member.name)
            if not member.isfile() or path.is_absolute() or ".." in path.parts or path.parts[0] != ARCHIVE_ROOT:
                raise ValueError("归档包含非普通文件或越界路径")
            name = str(PurePosixPath(*path.parts[1:]))
            if name in contents:
                raise ValueError("归档包含重复路径")
            stream = tar.extractfile(member)
            assert stream is not None
            contents[name] = stream.read()
    manifest = json.loads(contents.pop("RELEASE-MANIFEST.json"))
    return manifest, contents


def verify(archive: Path) -> dict:
    manifest, contents = read_archive(archive)
    if set(contents) != set(manifest["files"]):
        raise ValueError("归档文件清单不一致")
    for name, data in contents.items():
        expected = manifest["files"][name]
        if digest(data) != expected["sha256"] or len(data) != expected["size"]:
            raise ValueError(f"文件校验失败：{name}")
    if manifest.get("version") != VERSION:
        raise ValueError("归档版本不匹配")
    return {"version": VERSION, "source_commit": manifest["source_commit"],
            "file_count": len(contents), "archive_sha256": digest(archive.read_bytes()), "verified": True}


def restore(archive: Path, destination: Path, *, root: Path = ROOT) -> dict:
    destination = destination.resolve()
    if not destination.is_relative_to(root.resolve()) or destination == root.resolve() or destination.exists():
        raise ValueError("恢复目录必须是项目内尚不存在的独立目录")
    result = verify(archive)
    manifest, contents = read_archive(archive)
    destination.mkdir(parents=True)
    for name, data in contents.items():
        file = destination / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(data)
        file.chmod(manifest["files"][name]["mode"])
    (destination / "RELEASE-MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    for name, expected in manifest["files"].items():
        if digest((destination / name).read_bytes()) != expected["sha256"]:
            raise ValueError(f"恢复后校验失败：{name}")
    return {**result, "restored": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    freeze_cmd = sub.add_parser("freeze")
    freeze_cmd.add_argument("--out", type=Path, default=ROOT / "state/releases/v0.1.0")
    verify_cmd = sub.add_parser("verify")
    verify_cmd.add_argument("archive", type=Path)
    restore_cmd = sub.add_parser("restore")
    restore_cmd.add_argument("archive", type=Path)
    restore_cmd.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        if args.operation == "freeze":
            result = freeze(ROOT, args.out)
        elif args.operation == "verify":
            result = verify(args.archive)
        else:
            result = restore(args.archive, args.destination)
    except (ValueError, KeyError, OSError, tarfile.TarError) as exc:
        print(f"基线操作失败：{type(exc).__name__}；未验证。")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
