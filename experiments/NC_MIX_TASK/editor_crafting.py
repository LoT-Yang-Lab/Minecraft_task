#!/usr/bin/env python3
"""制作转化地图编辑器入口。"""
from __future__ import annotations

from common.bootstrap import insert_subpath

insert_subpath("crafting")

from editor_main import main as _run  # noqa: E402

if __name__ == "__main__":
    _run()
