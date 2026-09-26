"""存储层：SQLite 连接、迁移与数据访问。"""

from __future__ import annotations

from .analysis_repo import AnalysisRepository
from .database import Database
from .migrator import (
    Migration,
    MigrationChecksumError,
    MigrationError,
    apply_migrations,
    discover_migrations,
)
from .runtime_repo import RuntimeRepository
from .scenes_repo import SceneRepository
from .templates_repo import TemplateRepository

__all__ = [
    "AnalysisRepository",
    "Database",
    "Migration",
    "MigrationChecksumError",
    "MigrationError",
    "RuntimeRepository",
    "SceneRepository",
    "TemplateRepository",
    "apply_migrations",
    "discover_migrations",
]
