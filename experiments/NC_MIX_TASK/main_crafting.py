#!/usr/bin/env python3
"""制作主实验入口：与在 `crafting/` 下执行 `python main.py` 等价。"""
from __future__ import annotations

from common.bootstrap import insert_subpath

insert_subpath("crafting")

import main as _craft_main  # noqa: E402

if __name__ == "__main__":
    _craft_main.main()
