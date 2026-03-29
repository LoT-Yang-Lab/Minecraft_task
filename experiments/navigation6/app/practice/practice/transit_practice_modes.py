"""
练习序列：将 GameNavigation6 的 transit_modes（bus / metro / light_rail）映射为实验抽象类 R/D/C。
与练习文案一致：公交→R、轻轨→D、高铁(地铁)→C。
"""
from typing import List, Optional, Tuple

from experiments.navigation6.app.practice.practice.question_generator import PoolItem

# bus=R, light_rail=D, metro=C（高铁）
TRANSIT_MODE_TO_RDC: dict[str, str] = {
    "bus": "R",
    "light_rail": "D",
    "metro": "C",
}

RDC_MODES: Tuple[str, ...] = ("R", "D", "C")


def load_transit_modes_for_map(map_path: str) -> List[str]:
    """与 Navigation6 地图加载一致的全局线路 mode 列表（每条线一个 bus/metro/light_rail）。"""
    from shared.common.recorder import RLDataRecorder
    from experiments.navigation6.app.experiment.game import GameNavigation6

    rec = RLDataRecorder("Nav6_ModeProbe", task_type="Navigation6_Practice")
    game = GameNavigation6(
        rec,
        map_type="PracticeProbe",
        target_entropy=0.5,
        enable_experiment=False,
        custom_map_file=map_path,
    )
    return list(getattr(game, "transit_modes", []) or [])


def pool_item_to_rdc(item: PoolItem, transit_modes: List[str]) -> Optional[str]:
    """
    从 PoolItem 解析线路索引并得到 R/D/C；无法解析（非即时到站等）返回 None。
    """
    _, _, _, action_key, extra, _ = item
    if action_key not in ("instant_transit_next", "instant_transit_prev") or extra is None:
        return None
    li = int(extra) if not isinstance(extra, int) else extra
    if li < 0 or li >= len(transit_modes):
        return None
    raw = transit_modes[li]
    return TRANSIT_MODE_TO_RDC.get(raw)
