"""SQLite 访问层（PRD 1.3、5.4、第 8 节）。

设计要点：

- **短连接**：每次操作打开一个连接，不跨请求共享连接，避免线程问题；
- **显式事务**：写操作使用 ``BEGIN IMMEDIATE``，读操作不开事务；
- 模型网络等待期间不得持有写事务（PRD 5.4）——因此仓储层不暴露“长事务”API，
  调用方只能通过 :meth:`Database.transaction` 在纯本地写入期间持有事务；
- 连接建立时强制 ``PRAGMA foreign_keys = ON``（SQLite 默认关闭）。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .migrator import apply_migrations


class Database:
    """一个 SQLite 数据库文件。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if self.path.parent and str(self.path.parent) not in ("", "."):
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        """打开一个短连接（autocommit；事务由调用方显式开启）。"""

        conn = sqlite3.connect(self.path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """只读或自动提交使用；不开启事务。"""

        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """写事务。异常时回滚。"""

        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:  # pragma: no cover - 事务已结束时忽略回滚失败
                pass
            raise
        finally:
            conn.close()

    def migrate(self) -> list[int]:
        """建立 schema 并应用缺失的迁移，返回新应用的版本号。"""

        with self.connection() as conn:
            # WAL 是持久设置，只需设置一次；它不影响迁移语义。
            conn.execute("PRAGMA journal_mode = WAL")
            return apply_migrations(conn)
