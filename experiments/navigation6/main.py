#!/usr/bin/env python3
"""Navigation6 主程序入口（三类公共交通）。"""
from pathlib import Path

def main() -> None:
    """
    CLI 入口：把项目根加入 sys.path，然后调用 experiments.navigation6.app.experiment.main。
    """
    import sys

    # .../Minecraft8.0/experiments/navigation6/main.py -> .../Minecraft8.0
    this_file = Path(__file__).resolve()
    project_root = this_file.parents[2]
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

    from experiments.navigation6.app.experiment.main import main as _nav6_main

    _nav6_main()

if __name__ == "__main__":
    main()
