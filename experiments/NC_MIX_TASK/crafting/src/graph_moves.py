"""
在石头图上分解两条有向回路：回路一（同行）与回路二（同列），供药水1/2 与距离校验。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .stone_space import stone_row_col, w_cycle_next


def potion_backward_from_forward(forward: Dict[str, str]) -> Dict[str, str]:
    """
    由「正向一步」表求 E/D 用的逆向：若 forward[src]==dst，则 backward[dst]=src。
    若同一 dst 被多个 src 指向则无法定义唯一逆向，抛出 ValueError。
    """
    backward: Dict[str, str] = {}
    for src, dst in forward.items():
        if dst in backward:
            raise ValueError(
                f"正向表中 {dst} 被多个源指向，无法唯一确定逆向一步"
            )
        backward[dst] = src
    return backward


def ring1_prev_next(g: Dict[str, List[str]], cur: str) -> Tuple[Optional[str], Optional[str]]:
    """回路一：与当前石同行、另一列上的前驱/后继（有向）。"""
    rc = stone_row_col(cur)
    if rc is None:
        return None, None
    row, col = rc
    nxt: Optional[str] = None
    for v in g.get(cur, []):
        r2, c2 = stone_row_col(v) or (-1, -1)
        if r2 == row and c2 != col:
            nxt = v
            break
    pred: Optional[str] = None
    for u, outs in g.items():
        if cur in outs:
            r2, c2 = stone_row_col(u) or (-1, -1)
            if r2 == row and c2 != col:
                pred = u
                break
    return pred, nxt


def ring2_prev_next(g: Dict[str, List[str]], cur: str) -> Tuple[Optional[str], Optional[str]]:
    """回路二：与当前石同列、另一行上的前驱/后继（有向）。"""
    rc = stone_row_col(cur)
    if rc is None:
        return None, None
    row, col = rc
    nxt: Optional[str] = None
    for v in g.get(cur, []):
        r2, c2 = stone_row_col(v) or (-1, -1)
        if c2 == col and r2 != row:
            nxt = v
            break
    pred: Optional[str] = None
    for u, outs in g.items():
        if cur in outs:
            r2, c2 = stone_row_col(u) or (-1, -1)
            if c2 == col and r2 != row:
                pred = u
                break
    return pred, nxt


def neighbors_from_potions(
    state_id: str,
    potion1_fwd: Dict[str, str],
    potion1_rev: Dict[str, str],
    potion2_fwd: Dict[str, str],
    potion2_rev: Dict[str, str],
    potion3: Dict[str, str],
) -> List[str]:
    """与 GameCrafting 一致：Q/A 正向、E/D 逆向、W 药水3。"""
    out: List[str] = []
    for d in (
        potion1_fwd,
        potion1_rev,
        potion2_fwd,
        potion2_rev,
        potion3,
    ):
        nxt = d.get(state_id)
        if nxt:
            out.append(nxt)
    return list(dict.fromkeys(out))


def neighbors_player_moves(state_id: str, g: Dict[str, List[str]]) -> List[str]:
    """
    由邻接图 + 行列几何 + 九石大环推导一步邻居（与 built_in_potion_tables 一致）。
    含回路一/二的前向与后向一步 + 药水3 大环。
    """
    p1p, n1 = ring1_prev_next(g, state_id)
    p2p, n2 = ring2_prev_next(g, state_id)
    wn = w_cycle_next(state_id)
    out: List[str] = []
    for x in (n1, p1p, n2, p2p, wn):
        if x:
            out.append(x)
    return list(dict.fromkeys(out))
