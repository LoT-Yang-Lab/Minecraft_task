"""
九块石头上的转化图：行内回路一 + 列内回路二；地图 B 仅第一列有回路二。
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from .stone_space import STONE_IDS


def _sid(s: int, c: str) -> str:
    col = {"A": 0, "B": 1, "C": 2}[c]
    idx = (s - 1) * 3 + col + 1
    return f"stone_{idx:02d}"


def _build_map_a() -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {sid: [] for sid in STONE_IDS}
    for s in [1, 2, 3]:
        out[_sid(s, "A")].append(_sid(s, "B"))
        out[_sid(s, "B")].append(_sid(s, "C"))
        out[_sid(s, "C")].append(_sid(s, "A"))
    for c in ["A", "B", "C"]:
        out[_sid(1, c)].append(_sid(2, c))
        out[_sid(2, c)].append(_sid(3, c))
        out[_sid(3, c)].append(_sid(1, c))
    return out


def _build_map_b() -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {sid: [] for sid in STONE_IDS}
    for s in [1, 2, 3]:
        out[_sid(s, "A")].append(_sid(s, "B"))
        out[_sid(s, "B")].append(_sid(s, "C"))
        out[_sid(s, "C")].append(_sid(s, "A"))
    out[_sid(1, "A")].append(_sid(2, "A"))
    out[_sid(2, "A")].append(_sid(3, "A"))
    out[_sid(3, "A")].append(_sid(1, "A"))
    return out


MAP_A = _build_map_a()
MAP_B = _build_map_b()
MAPS: Dict[str, Dict[str, List[str]]] = {"map_a": MAP_A, "map_b": MAP_B}


def get_map(map_id: str) -> Dict[str, List[str]]:
    return MAPS.get(map_id, MAP_A)


def built_in_potion_tables(
    map_id: str,
) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str], Dict[str, str], Dict[str, str]]:
    """
    回路一/二：Q、A 为 pred,nxt 中的「顺向」一步，E、D 为「逆向」一步；药水3 为大环。
    返回 (potion1_fwd, potion1_rev, potion2_fwd, potion2_rev, potion3)。
    """
    from .graph_moves import ring1_prev_next, ring2_prev_next
    from .stone_space import STONE_IDS, w_cycle_next

    g = get_map(map_id)
    p1f: Dict[str, str] = {}
    p1r: Dict[str, str] = {}
    p2f: Dict[str, str] = {}
    p2r: Dict[str, str] = {}
    p3: Dict[str, str] = {}
    for sid in STONE_IDS:
        pred1, nxt1 = ring1_prev_next(g, sid)
        if nxt1 is not None:
            p1f[sid] = nxt1
        if pred1 is not None:
            p1r[sid] = pred1
        pred2, nxt2 = ring2_prev_next(g, sid)
        if nxt2 is not None:
            p2f[sid] = nxt2
        if pred2 is not None:
            p2r[sid] = pred2
        wn = w_cycle_next(sid)
        if wn is not None:
            p3[sid] = wn
    return p1f, p1r, p2f, p2r, p3
