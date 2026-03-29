"""
将练习记录 / 轨迹与最优策略对比，计算一致率与路径效率。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import random


def compare_practice_to_policy(
    practice_records: List[Dict[str, Any]],
    optimal_next_by_state: Dict[int, int],
    state_key: str = "current_code",
    choice_key: str = "participant_choice",
) -> Dict[str, Any]:
    """
    practice_records: 来自 load_practice 的扁平记录，含 current_code, participant_choice。
    optimal_next_by_state: state (1-indexed) -> 推荐下一站 (1-indexed)；可由 export_policy_to_dict 得到。
    返回: {"total": N, "match": k, "consistency_rate": k/N, "by_phase": {...}}
    """
    total = 0
    match = 0
    by_phase: Dict[str, Dict[str, int]] = {}
    for r in practice_records:
        s = r.get(state_key, 0)
        choice = r.get(choice_key, 0)
        if s <= 0:
            continue
        total += 1
        opt = optimal_next_by_state.get(s)
        if opt is not None and choice == opt:
            match += 1
        phase = r.get("phase", "")
        if phase not in by_phase:
            by_phase[phase] = {"total": 0, "match": 0}
        by_phase[phase]["total"] += 1
        if opt is not None and choice == opt:
            by_phase[phase]["match"] += 1
    rate = (match / total) if total else 0.0
    for p, v in by_phase.items():
        v["rate"] = (v["match"] / v["total"]) if v["total"] else 0.0
    return {
        "total": total,
        "match": match,
        "consistency_rate": rate,
        "by_phase": by_phase,
    }


@dataclass(frozen=True)
class _GroupAgg:
    total: int
    match: int


def _agg_by_key_binary_match(
    rows: Iterable[Dict[str, Any]],
    group_key: str,
    state_key: str,
    choice_key: str,
    optimal_next_by_state: Dict[int, int],
) -> Dict[str, _GroupAgg]:
    """
    Aggregate match/total by a grouping key (e.g., participant_id).
    A row is a match when choice == optimal_next_by_state[s].
    """
    tmp: Dict[str, Tuple[int, int]] = {}
    for r in rows:
        g = r.get(group_key, "")
        if not g:
            continue
        s = r.get(state_key, 0)
        if not isinstance(s, int):
            try:
                s = int(s)
            except Exception:
                continue
        if s <= 0:
            continue
        choice = r.get(choice_key, 0)
        if not isinstance(choice, int):
            try:
                choice = int(choice)
            except Exception:
                choice = 0
        opt = optimal_next_by_state.get(s)
        total, match = tmp.get(g, (0, 0))
        total += 1
        if opt is not None and choice == opt:
            match += 1
        tmp[g] = (total, match)
    return {g: _GroupAgg(total=t, match=m) for g, (t, m) in tmp.items()}


def _weighted_rate(aggs: Iterable[_GroupAgg]) -> float:
    total = 0
    match = 0
    for a in aggs:
        total += int(a.total)
        match += int(a.match)
    return (match / total) if total else 0.0


def _cluster_bootstrap_ci(
    per_cluster: Dict[str, _GroupAgg],
    *,
    seed: int = 0,
    n_boot: int = 2000,
    alpha: float = 0.05,
) -> Dict[str, Any]:
    """
    Cluster bootstrap over clusters (e.g., participant_id) for the pooled weighted rate.
    Returns a percentile CI; avoids treating steps as i.i.d.
    """
    keys = list(per_cluster.keys())
    point = _weighted_rate(per_cluster.values())
    if len(keys) < 2:
        return {
            "method": "cluster_bootstrap",
            "cluster_key_count": len(keys),
            "n_boot": 0,
            "alpha": alpha,
            "point": point,
            "ci_low": None,
            "ci_high": None,
        }
    rng = random.Random(seed)
    boot: List[float] = []
    B = max(1, int(n_boot))
    for _ in range(B):
        sample = [per_cluster[rng.choice(keys)] for _ in range(len(keys))]
        boot.append(_weighted_rate(sample))
    boot.sort()
    lo_idx = int((alpha / 2) * len(boot))
    hi_idx = int((1 - alpha / 2) * len(boot)) - 1
    lo_idx = max(0, min(lo_idx, len(boot) - 1))
    hi_idx = max(0, min(hi_idx, len(boot) - 1))
    return {
        "method": "cluster_bootstrap",
        "cluster_key_count": len(keys),
        "n_boot": len(boot),
        "alpha": alpha,
        "point": point,
        "ci_low": float(boot[lo_idx]),
        "ci_high": float(boot[hi_idx]),
    }


def summarize_trajectory_consistency_inference(
    trajectory_rows: List[Dict[str, Any]],
    optimal_next_by_state: Dict[int, int],
    *,
    participant_key: str = "participant_id",
    state_key: str = "s",
    next_key: str = "s_next",
    n_boot: int = 2000,
    alpha: float = 0.05,
    seed: int = 0,
) -> Dict[str, Any]:
    """
    Inference-friendly summary for trajectory consistency using cluster bootstrap by participant.
    """
    per_p = _agg_by_key_binary_match(
        trajectory_rows,
        group_key=participant_key,
        state_key=state_key,
        choice_key=next_key,
        optimal_next_by_state=optimal_next_by_state,
    )
    overall = _weighted_rate(per_p.values())
    ci = _cluster_bootstrap_ci(per_p, seed=seed, n_boot=n_boot, alpha=alpha)
    participant_rates = [
        {
            "participant_id": pid,
            "total_steps": agg.total,
            "match": agg.match,
            "rate": (agg.match / agg.total) if agg.total else 0.0,
        }
        for pid, agg in sorted(per_p.items(), key=lambda kv: kv[0])
    ]
    return {
        "total_steps": sum(a.total for a in per_p.values()),
        "match": sum(a.match for a in per_p.values()),
        "overall_weighted_rate": overall,
        "participant_count": len(per_p),
        "participant_rates": participant_rates,
        "bootstrap_ci": ci,
    }


def compare_trajectory_to_policy(
    trajectory_rows: List[Dict[str, Any]],
    optimal_next_by_state: Dict[int, int],
    state_key: str = "s",
    next_key: str = "s_next",
) -> Dict[str, Any]:
    """
    轨迹每行含 s, s_next（0-indexed 或 1-indexed 需一致）。optimal_next_by_state 为 1-indexed。
    若轨迹用 0-indexed，则比较时 s+1 -> optimal_next_by_state[s+1] 与 s_next+1。
    此处约定轨迹的 s, s_next 为 1-indexed（与 load_trajectory 中 encoder 返回一致）。
    返回: {"total_steps": N, "match": k, "consistency_rate": k/N, "path_ratio": actual/optimal 若可算}
    """
    total = 0
    match = 0
    for r in trajectory_rows:
        s = r.get(state_key, 0)
        s_next = r.get(next_key, 0)
        if s <= 0:
            continue
        total += 1
        opt = optimal_next_by_state.get(s)
        if opt is not None and s_next == opt:
            match += 1
    rate = (match / total) if total else 0.0
    return {
        "total_steps": total,
        "match": match,
        "consistency_rate": rate,
    }
