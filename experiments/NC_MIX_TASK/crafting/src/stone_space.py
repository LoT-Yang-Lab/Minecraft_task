"""
Crafting：九块互不相同的石头（状态 ID：stone_01 … stone_09）。
图拓扑仍对应原 3×3 双回路，但呈现与文案不再使用「颜色/形状」语义。
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Tuple

STONE_IDS: List[str] = [f"stone_{i:02d}" for i in range(1, 10)]

_NUM_CN = ("一", "二", "三", "四", "五", "六", "七", "八", "九")
_DISPLAY = {f"stone_{i:02d}": f"石块{_NUM_CN[i - 1]}" for i in range(1, 10)}


def stone_index(state_id: str) -> Optional[int]:
    if not state_id.startswith("stone_"):
        return None
    tail = state_id[6:]
    try:
        n = int(tail)
    except ValueError:
        return None
    if 1 <= n <= 9:
        return n
    return None


def stone_row_col(state_id: str) -> Optional[Tuple[int, int]]:
    """0-based (row, col)，与建图时 3×3 排布一致。"""
    idx = stone_index(state_id)
    if idx is None:
        return None
    z = idx - 1
    return z // 3, z % 3


def is_valid_state_id(state_id: str) -> bool:
    return state_id in STONE_IDS


def display_name(state_id: str) -> str:
    return _DISPLAY.get(state_id, state_id)


def w_cycle_next(state_id: str) -> Optional[str]:
    """
    魔法药水3：沿固定大环前进一步（stone_01→…→stone_09→stone_01），与地图上的回路一/二无关。
    """
    idx = stone_index(state_id)
    if idx is None:
        return None
    nxt = (idx % 9) + 1
    return f"stone_{nxt:02d}"


def default_raw_pool() -> List[str]:
    return list(STONE_IDS)


def unique_preserve_order(items: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out
