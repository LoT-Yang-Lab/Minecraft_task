"""将 NC_MIX_TASK 项目根目录与子包目录加入 sys.path，供顶层入口脚本使用。"""
from __future__ import annotations

import sys
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def ensure_project_root_on_path() -> Path:
    root = project_root()
    s = str(root)
    if s not in sys.path:
        sys.path.insert(0, s)
    return root


def insert_subpath(relative: str) -> Path:
    """将 `<项目根>/<relative>` 置于 sys.path 最前（若尚未包含）。"""
    ensure_project_root_on_path()
    p = project_root() / relative
    s = str(p.resolve())
    if s not in sys.path:
        sys.path.insert(0, s)
    return p
