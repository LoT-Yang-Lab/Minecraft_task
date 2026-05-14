#!/usr/bin/env python3
"""地图编辑器入口：在本项目根目录执行 `python editor_main.py`。"""
from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from app.editor.map_editor_nav6 import main

if __name__ == "__main__":
    main()
