#!/usr/bin/env python3
"""导航练习入口。"""
from __future__ import annotations

from common.bootstrap import insert_subpath

insert_subpath("navigation")

from practice_main import main as _run  # noqa: E402

if __name__ == "__main__":
    _run()
