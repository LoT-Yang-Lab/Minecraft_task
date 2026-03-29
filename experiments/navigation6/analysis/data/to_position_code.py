"""
将 (map_id, Grid_X, Grid_Y) 转为位置编码 1..N。
依赖地图与 cogmap/游戏逻辑，返回的编码与练习数据中的 current_code 一致。
"""
from typing import Dict, Tuple, Callable, Optional
import os
import sys

# 确保项目根在 path 中，以便导入 experiments / shared
_analysis_dir = os.path.dirname(os.path.abspath(__file__))
_nav5_root = os.path.normpath(os.path.join(_analysis_dir, "..", ".."))
_project_root = os.path.normpath(os.path.join(_nav5_root, "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

class _NullRecorder:
    """
    analysis 侧只为构造 GameNavigation6 而提供的最小 recorder。
    避免在分析阶段意外创建 rl_data 目录或写文件。
    """
    def __init__(self):
        self.memory_buffer = []
        self.episode_count = 0
        self.step_count = 0

    def start_episode(self):
        self.episode_count += 1
        self.step_count = 0

    def log_action(self, *args, **kwargs):
        self.step_count += 1

    def save_to_file(self):
        return


def get_position_encoder_for_map(map_id: str, maps_dir: Optional[str] = None) -> Callable[[int, int], int]:
    """
    返回一个函数 f(gx, gy) -> position_code (1..N)。
    若 (gx, gy) 不在可行走格则返回 0 或抛出 KeyError，此处约定返回 0。

    Args:
        map_id: 地图标识，如 "map_1773511099"，对应 maps/map_1773511099.json
        maps_dir: 地图目录，默认 experiments/navigation6/maps
    """
    if maps_dir is None:
        from experiments.navigation6.app.paths import maps_dir as _maps_dir
        maps_dir = _maps_dir()
    map_file = map_id + ".json" if not map_id.endswith(".json") else map_id
    map_path = os.path.join(maps_dir, map_file)
    if not os.path.isabs(map_path):
        map_path = os.path.abspath(map_path)
    if not os.path.exists(map_path):
        raise FileNotFoundError(f"Map file not found: {map_path}")

    from experiments.navigation6.app.experiment.game import GameNavigation6
    from experiments.navigation6.app.experiment.main import build_position_encoding

    recorder = _NullRecorder()
    game = GameNavigation6(
        recorder,
        map_type=map_id,
        target_entropy=0.5,
        enable_experiment=False,
        custom_map_file=map_path,
    )
    cell_to_code, _, _ = build_position_encoding(game)

    def encoder(gx: int, gy: int) -> int:
        return cell_to_code.get((gx, gy), 0)

    return encoder


def get_position_encoder_cached(maps_dir: Optional[str] = None) -> Callable[[str], Callable[[int, int], int]]:
    """返回一个按 map_id 缓存 encoder 的工厂，避免重复加载同一地图。"""
    cache: Dict[str, Callable[[int, int], int]] = {}

    def get_encoder(map_id: str) -> Callable[[int, int], int]:
        if map_id not in cache:
            cache[map_id] = get_position_encoder_for_map(map_id, maps_dir=maps_dir)
        return cache[map_id]

    return get_encoder
