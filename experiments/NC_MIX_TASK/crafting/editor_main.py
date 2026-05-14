#!/usr/bin/env python3
"""启动转化地图编辑器。在本项目根目录执行: python editor_main.py"""

from __future__ import annotations

import sys
from pathlib import Path

_this = Path(__file__).resolve().parent
if str(_this) not in sys.path:
    sys.path.insert(0, str(_this))

from src.editor.map_editor_crafting import main

if __name__ == "__main__":
    main()
