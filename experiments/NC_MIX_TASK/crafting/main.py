#!/usr/bin/env python3
"""
Crafting（九石阵）正式实验入口；项目目录为 experiments/crafting，与 Navigation6 并列。

- 状态为九块可区分的石头（stone_01 … stone_09），无食材、无「色相/形状」叙事。
- 无石块池：每 trial 单一起始态，当前石块仅显示在操作区；订单目标 + 底部三键。
- 宝石图：本目录 assets/stone；可选在任意上级目录放 shared/assets/stone（推荐 stone_01.png … stone_09.png）。
- 药水瓶图：本目录 assets/bottle；可选 shared/assets/bottle（推荐 bottle_01…03.png）。
- Q/E：药水1 回路一正向/逆向 · A/D：药水2 回路二正向/逆向 · W：药水3 九石大环（可循环）。
- 独立运行：在本项目根目录执行 `pip install -r requirements.txt` 后 `python main.py`（或 `python practice_main.py` / `python editor_main.py` / `python run_proposal5_experiment.py`）；代码仅依赖本目录下的 `src/` 与 `data/`，不导入、不读取其它名为 `alchemy` 的旧实验包。
- 正式试次：与 Navigation6 共用 `assets/trial_sequences/<地图 stem>.json` 格式（站点 1–9 对应 stone_01–09）。默认转化地图 `data/maps/builtin_map_a.json` 含 `linked_navigation_map_id`，将自动加载并列目录 `navigation6/assets/trial_sequences/<id>.json`；亦可用 `--trials` 指定任意路径、`--nav-map-id map_xxx` 指定 stem。无关联时回退 `data/trials/trial_list_v1.json`（`crafting_trial_list`）。
- 转化地图编辑器：`python editor_main.py`；JSON 中 potion1/2 存 Q/A 正向边，E/D 由程序推逆向；药水3 为可拖拽控制柄的贝塞尔曲线，偏移写入 `potion3_control_offset`（仅展示用）。
- 启动后先输入被试编号，再在 `data/maps` 中选转化地图；选图后呈现正式任务说明页（Enter/空格开始）；可用 `-p` 跳过编号页，`--transition_map` 跳过选图。
- 练习阶段：`python practice_main.py`。
- Proposal-5 五 session（仅 crafting 试次，与 Navigation6 仅导航对称）：`python run_proposal5_experiment.py --help`；建议固定 `--transition_map data/maps/builtin_map_a.json`。
- 行为数据写入 `rl_data/<时间戳>/`，含每键反应时、订单序号、状态转移、无效键与 R 重置等列，便于建模。
"""

import os
import sys

this_dir = os.path.dirname(os.path.abspath(__file__))
if this_dir not in sys.path:
    sys.path.insert(0, this_dir)

from src.main_crafting import main


if __name__ == "__main__":
    main()
