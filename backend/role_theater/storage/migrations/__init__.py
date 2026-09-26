"""SQL 迁移文件包。

迁移文件按文件名前缀的版本号顺序应用；内容一旦应用即记录 checksum，
被修改后会拒绝启动（防止悄悄改写历史迁移）。
"""

from __future__ import annotations
