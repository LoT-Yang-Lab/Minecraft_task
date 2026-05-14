"""
Crafting：用被试真实可操作步做 BFS 距离，筛选订单目标。
一步邻居与 GameCrafting 的药水表一致（药水1/2 含 Q/A 正向与 E/D 逆向）。
"""

from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Set, Tuple

from .graph_moves import neighbors_from_potions


def bfs_distances_player_moves(
    start_state: str,
    potion1_fwd: Dict[str, str],
    potion1_rev: Dict[str, str],
    potion2_fwd: Dict[str, str],
    potion2_rev: Dict[str, str],
    potion3: Dict[str, str],
) -> Dict[str, int]:
    dist: Dict[str, int] = {start_state: 0}
    q = deque([start_state])
    while q:
        cur = q.popleft()
        d = dist[cur]
        for nxt in neighbors_from_potions(
            cur,
            potion1_fwd,
            potion1_rev,
            potion2_fwd,
            potion2_rev,
            potion3,
        ):
            if nxt not in dist:
                dist[nxt] = d + 1
                q.append(nxt)
    return dist


def choose_reachable_targets_multi_starts(
    requested_targets: Optional[List[str]],
    raw_states: List[str],
    order_count: int,
    potion1_fwd: Dict[str, str],
    potion1_rev: Dict[str, str],
    potion2_fwd: Dict[str, str],
    potion2_rev: Dict[str, str],
    potion3: Dict[str, str],
    rng,
    min_distance: int = 3,
    strict_requested: bool = False,
) -> Tuple[List[str], List[str]]:
    """
    返回 (valid_targets, messages)。
    game 侧通常传入 min_distance=2（双起点同时约束）。
    strict_requested=True 且 requested_targets 非空时：禁止随机替换目标；不满足距离则抛出 ValueError。
    """
    if order_count <= 0:
        return [], []

    if not raw_states:
        raise ValueError("raw_states 不能为空")

    dist_maps: List[Dict[str, int]] = [
        bfs_distances_player_moves(
            raw,
            potion1_fwd,
            potion1_rev,
            potion2_fwd,
            potion2_rev,
            potion3,
        )
        for raw in raw_states
    ]

    candidate_pool: Optional[Set[str]] = None
    for raw, dist in zip(raw_states, dist_maps):
        good = {s for s, d in dist.items() if d >= min_distance and s != raw}
        candidate_pool = good if candidate_pool is None else (candidate_pool & good)

    candidate_pool_final: List[str] = sorted(candidate_pool) if candidate_pool else []
    if not candidate_pool_final:
        raise ValueError(
            f"No valid targets with min_distance={min_distance} for all raws. raws={raw_states}"
        )

    def _is_valid_target(t: str) -> bool:
        for dist in dist_maps:
            d = dist.get(t)
            if d is None or d < min_distance:
                return False
        return True

    requested_targets = requested_targets or []

    valid: List[str] = []
    msgs: List[str] = []

    if strict_requested and requested_targets:
        if order_count > len(requested_targets):
            raise ValueError(
                f"strict_order_targets: 需要 {order_count} 个显式目标，仅提供 {len(requested_targets)} 个"
            )
        for t in requested_targets[:order_count]:
            if not _is_valid_target(t):
                raise ValueError(
                    f"strict_order_targets: 目标 {t!r} 从 raws {raw_states} 不可达或最短路径 < {min_distance}"
                )
            valid.append(t)
        return valid, msgs

    for t in requested_targets[:order_count]:
        if _is_valid_target(t):
            valid.append(t)
        else:
            rt = rng.choice(candidate_pool_final)
            valid.append(rt)
            msgs.append(f"订单目标 {t} 不满足对所有 raw 的距离>= {min_distance}，已替换为 {rt}")

    while len(valid) < order_count:
        valid.append(rng.choice(candidate_pool_final))

    return valid, msgs
