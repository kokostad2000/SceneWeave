#!/usr/bin/env bash
#
# SQLite 备份（PRD 10：备份恢复方法）。
#
# 事实来源是单个 SQLite 文件；WAL 模式下必须先做检查点，保证备份里包含全部
# 已提交事务。用法：
#
#   scripts/backup_db.sh [源数据库] [目标文件]
#
# 默认源为 backend/sceneweave.db，默认目标为 state/backups/sceneweave-<时间戳>.db
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="${1:-$ROOT_DIR/backend/sceneweave.db}"
STAMP="$(date +%Y%m%d-%H%M%S)"
TARGET="${2:-$ROOT_DIR/state/backups/sceneweave-$STAMP.db}"

if [[ ! -f "$SOURCE" ]]; then
  echo "源数据库不存在：$SOURCE" >&2
  exit 1
fi

mkdir -p "$(dirname "$TARGET")"

# 用 sqlite3 的 .backup，它在事务边界上取一致快照，并自动处理 WAL。
if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$SOURCE" ".backup '$TARGET'"
else
  # 没有 sqlite3 CLI 时退回文件复制（先做检查点，避免丢失 WAL 内容）。
  python3 - "$SOURCE" "$TARGET" <<'PY'
import sqlite3, sys, shutil
source, target = sys.argv[1], sys.argv[2]
conn = sqlite3.connect(source)
conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
conn.close()
shutil.copy2(source, target)
PY
fi

echo "备份完成：$TARGET"
if command -v sqlite3 >/dev/null 2>&1; then
  echo "表与行数："
  sqlite3 "$TARGET" "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;" \
    | while read -r table; do
        printf '  %-24s %s\n' "$table" "$(sqlite3 "$TARGET" "SELECT COUNT(*) FROM \"$table\";")"
      done
fi
echo "恢复方法：停止服务后把备份文件复制回 SCENEWEAVE_DATABASE_URL 指向的路径；启动时会自动执行迁移（幂等）。"
