#!/usr/bin/env python3
"""导航主实验入口：与在 `navigation/` 下执行 `python main.py` 等价（含 `--graph9` 等 CLI）。"""
from __future__ import annotations

from common.bootstrap import insert_subpath

insert_subpath("navigation")

import main as _nav_main  # noqa: E402

if __name__ == "__main__":
    _nav_main.main()
