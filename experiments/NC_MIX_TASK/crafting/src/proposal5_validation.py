"""Proposal-5：在启动 pygame 前校验 (nav start, nav goal) 在当前转化图上可达且满足最步数。"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from .rules_io_crafting import RuleDataCrafting
from .validation_crafting import bfs_distances_player_moves


def nav_code_to_stone(n: int) -> str:
    return f"stone_{int(n):02d}"


def validate_navigation_trials_on_map(
    rules: RuleDataCrafting,
    navigation_trials: Sequence[Dict[str, Any]],
    *,
    min_distance: int = 2,
) -> None:
    """
    对每个 navigation trial（含 start/goal 整数与可选 pair_id）做 BFS；
    不可达或最短路径 < min_distance 时抛出 ValueError。
    """
    p1 = dict(rules.potion1)
    p1r = dict(rules.potion1_rev)
    p2 = dict(rules.potion2)
    p2r = dict(rules.potion2_rev)
    p3 = dict(rules.potion3)

    for t in navigation_trials:
        pair_id = t.get("pair_id", "?")
        s = nav_code_to_stone(int(t["start"]))
        g = nav_code_to_stone(int(t["goal"]))
        dm = bfs_distances_player_moves(s, p1, p1r, p2, p2r, p3)
        d = dm.get(g)
        if d is None:
            raise ValueError(f"Proposal5 预检失败 pair_id={pair_id}: {s} 无法到达 {g}")
        if d < min_distance:
            raise ValueError(
                f"Proposal5 预检失败 pair_id={pair_id}: {s}->{g} 最短步数 {d} < {min_distance}"
            )


def validate_crafting_trials_on_map(
    rules: RuleDataCrafting,
    crafting_trials: Sequence[Dict[str, Any]],
    *,
    min_distance: int = 2,
) -> None:
    """Crafting 占位试次与导航试次共用 start/goal 编码，BFS 预检逻辑相同。"""
    validate_navigation_trials_on_map(rules, crafting_trials, min_distance=min_distance)
