"""
为当前实验用的三张地图批量生成认知地图 SVG（状态图、谱嵌入、特征值）。

用法（在 experiments/navigation6 目录下）：
  python scripts/render_cogmap_three_maps.py

或在项目根（experiments）下：
  python navigation6/scripts/render_cogmap_three_maps.py

输出目录：outputs/cogmap/
每个地图生成三张图：{map_id}_original.svg, _spectral.svg, _eigenvalues.svg
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 保证可导入 experiments.navigation6（需要包含 experiments 的上级目录）
_script_dir = Path(__file__).resolve().parent
_nav6_root = _script_dir.parent
_experiments_root = _nav6_root.parent  # experiments/
_repo_root = _experiments_root.parent   # 含 experiments 的目录
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from experiments.navigation6.app.viz.cogmap_nav6 import (
    compute_nav6_cogmap,
    render_and_save_cogmap,
)

MAP_FILES = [
    "map_1774095558.json",
]

OUTPUT_DIR = os.path.join(_nav6_root, "outputs", "cogmap")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for map_file in MAP_FILES:
        map_id = os.path.splitext(map_file)[0]
        print(f"[{map_id}] 计算认知地图...")
        try:
            cogmap = compute_nav6_cogmap(map_path=map_file, include_distances=True)
            paths = render_and_save_cogmap(cogmap, OUTPUT_DIR, basename=map_id)
            print(f"  -> 已保存: {paths}")
        except Exception as e:
            print(f"  -> 失败: {e}")
            raise
    print("完成。输出目录:", os.path.abspath(OUTPUT_DIR))


if __name__ == "__main__":
    main()
