#!/usr/bin/env python3
"""Navigation6 正式实验入口。

默认 `python main.py`：与 crafting 一致 — 被试编号 → 选地图 JSON → 任务说明 → **地图交通** 测试（main2）。

- `--graph9`：使用旧版 9 节点 Graph9 界面（无选图、无本流程）。
- `-p` / `--participant_id`、`--map`、`--no-guidance`、`--trials`：与 `python main2.py` 相同（试次表默认 `assets/trial_sequences/<地图主名>.json`）。

练习：`practice_main.py`；五 session：`tests/run_experiment_new.py`；地图编辑器：`editor_main.py`。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    this_file = Path(__file__).resolve()
    nav6_root = this_file.parent
    nav6_root_str = str(nav6_root)
    if nav6_root_str not in sys.path:
        sys.path.insert(0, nav6_root_str)

    parser = argparse.ArgumentParser(description="Navigation6 正式实验")
    parser.add_argument(
        "--graph9",
        action="store_true",
        help="使用 9 节点 Graph9 界面（不经过选图 / 编号 / 指导语）",
    )
    parser.add_argument(
        "--participant_id",
        "-p",
        default=None,
        help="指定被试编号则跳过编号页（仅地图交通模式）",
    )
    parser.add_argument(
        "--map",
        default=None,
        help="指定地图 JSON 则跳过选图（仅地图交通模式）",
    )
    parser.add_argument(
        "--no-guidance",
        action="store_true",
        help="跳过任务说明（仅地图交通模式）",
    )
    parser.add_argument(
        "--trials",
        default=None,
        help="试次表 JSON（默认使用 assets/trial_sequences/<地图主文件名>.json；可传文件名或路径）",
    )
    args = parser.parse_args()

    if args.graph9:
        from app.experiment.main import main as _graph9_main

        _graph9_main()
        return

    from main2 import main as _main2_main

    _main2_main(
        participant_id=args.participant_id,
        map_path_cli=args.map,
        skip_guidance=args.no_guidance,
        preflight=True,
        trial_sequence_path_cli=args.trials,
    )


if __name__ == "__main__":
    main()
