#!/usr/bin/env python3
"""
最短入口：运行 Navigation6 练习阶段 v4（分支可视化）。

用法（项目根运行）：
  python navigation6/scripts/run_practice4.py [args...]
"""
from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    this_file = Path(__file__).resolve()
    project_root = this_file.parents[1]  # navigation6
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

    from practice_main import main as run_practice

    sys.argv = [sys.argv[0], *argv]
    run_practice()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
