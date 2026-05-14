#!/usr/bin/env python3
"""混合实验（同进程单窗口）入口。"""
from __future__ import annotations

from common.bootstrap import ensure_project_root_on_path

ensure_project_root_on_path()

from mix.run_mix_experiment import main


if __name__ == "__main__":
    raise SystemExit(main())
