#!/usr/bin/env python3
"""
最短入口：运行 Navigation6 正式实验（轨迹记录）。

用法（项目根运行）：
  python experiments/navigation6/scripts/run_experiment.py
"""
from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    this_file = Path(__file__).resolve()
    project_root = this_file.parents[3]  # .../Minecraft8.0
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

    from experiments.navigation6.main import main as exp_main

    sys.argv = [sys.argv[0], *argv]
    exp_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

