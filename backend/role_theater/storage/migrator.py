"""数据库迁移（PRD 第 8 节：迁移现在就做）。

规则：

- 迁移文件为 ``role_theater/storage/migrations/NNN_name.sql``，按版本号顺序应用；
- 每个迁移在**一个事务**内执行完毕（DDL 在 SQLite 中可事务化），失败整体回滚；
- 已应用迁移的 checksum 会被记录并校验，内容被改动即拒绝启动；
- 重复运行是幂等的，只应用缺失的版本。
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import resources

MIGRATIONS_PACKAGE = "role_theater.storage.migrations"
MIGRATIONS_SUFFIX = ".sql"

_MIGRATION_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INTEGER PRIMARY KEY,
    name       TEXT    NOT NULL,
    checksum   TEXT    NOT NULL,
    applied_at TEXT    NOT NULL
)
"""


class MigrationError(RuntimeError):
    """迁移失败。"""


class MigrationChecksumError(MigrationError):
    """已应用的迁移内容被修改——拒绝继续启动。"""


@dataclass(frozen=True)
class Migration:
    """一个迁移文件。"""

    version: int
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.encode("utf-8")).hexdigest()


def _parse_version(filename: str) -> tuple[int, str]:
    stem = filename[: -len(MIGRATIONS_SUFFIX)]
    prefix, _, remainder = stem.partition("_")
    try:
        version = int(prefix)
    except ValueError as exc:  # pragma: no cover - 文件名写错时给出明确错误
        raise MigrationError(f"迁移文件名必须以数字版本开头：{filename}") from exc
    return version, remainder or stem


def discover_migrations() -> list[Migration]:
    """按版本号升序返回全部迁移。"""

    root = resources.files(MIGRATIONS_PACKAGE)
    migrations: list[Migration] = []
    for entry in root.iterdir():
        if not entry.name.endswith(MIGRATIONS_SUFFIX):
            continue
        version, name = _parse_version(entry.name)
        migrations.append(Migration(version=version, name=name, sql=entry.read_text(encoding="utf-8")))

    migrations.sort(key=lambda item: item.version)
    versions = [item.version for item in migrations]
    if len(set(versions)) != len(versions):
        raise MigrationError(f"迁移版本号重复：{versions}")
    return migrations


def split_statements(sql: str) -> list[str]:
    """按完整语句切分 SQL。

    使用 ``sqlite3.complete_statement`` 而不是简单 ``split(";")``，
    以免破坏字符串字面量与注释中的分号。
    """

    statements: list[str] = []
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            if statement:
                statements.append(statement)
            buffer = ""
    trailing = buffer.strip()
    if trailing:
        statements.append(trailing)
    return statements


def ensure_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute(_MIGRATION_TABLE)


def applied_migrations(conn: sqlite3.Connection) -> dict[int, str]:
    ensure_migration_table(conn)
    rows = conn.execute("SELECT version, checksum FROM schema_migrations").fetchall()
    return {int(row["version"]): str(row["checksum"]) for row in rows}


def apply_migrations(conn: sqlite3.Connection, *, now: datetime | None = None) -> list[int]:
    """应用尚未执行的迁移，返回本次新应用的版本号列表。"""

    applied = applied_migrations(conn)
    timestamp = (now or datetime.now(UTC)).isoformat()
    newly_applied: list[int] = []

    for migration in discover_migrations():
        recorded = applied.get(migration.version)
        if recorded is not None:
            if recorded != migration.checksum:
                raise MigrationChecksumError(
                    f"迁移 {migration.version:03d}_{migration.name} 的内容已被修改"
                    f"（记录 {recorded[:12]}…，当前 {migration.checksum[:12]}…）；"
                    "请新增一个迁移文件，而不是改写已应用的迁移"
                )
            continue

        conn.execute("BEGIN IMMEDIATE")
        try:
            for statement in split_statements(migration.sql):
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_migrations (version, name, checksum, applied_at)"
                " VALUES (?, ?, ?, ?)",
                (migration.version, migration.name, migration.checksum, timestamp),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        newly_applied.append(migration.version)

    return newly_applied
