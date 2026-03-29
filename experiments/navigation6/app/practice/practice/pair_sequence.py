"""
练习 trial 序列：成对状态链 + 对内 R/D/C 偏置。

仅在题号 (1,2)、(3,4)、…（0-based: 0–1, 2–3, …）对内满足：
上一题 next_code == 下一题 current_code。
方式偏置（DD/DR/DC/DCR）仅作用于上述对内边；跨对边界无状态约束。
"""
from __future__ import annotations

import random
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from experiments.navigation6.app.practice.practice.question_generator import PoolItem
from experiments.navigation6.app.practice.practice.transit_practice_modes import (
    RDC_MODES,
    pool_item_to_rdc,
)


class PairCondition(str, Enum):
    SAME_HEAVY = "same_heavy"
    RD_HEAVY = "rd_heavy"
    C_HEAVY = "c_heavy"
    UNIFORM = "uniform"


PARTICIPANT_CONDITION_CODE: Dict[PairCondition, str] = {
    PairCondition.SAME_HEAVY: "DD",
    PairCondition.RD_HEAVY: "DR",
    PairCondition.C_HEAVY: "DC",
    PairCondition.UNIFORM: "DCR",
}


_EDGE_CATEGORY_WEIGHTS: Dict[PairCondition, Tuple[float, float, float]] = {
    PairCondition.SAME_HEAVY: (0.70, 0.15, 0.15),
    PairCondition.RD_HEAVY: (0.15, 0.70, 0.15),
    PairCondition.C_HEAVY: (0.15, 0.15, 0.70),
}


def parse_pair_condition(s: str) -> PairCondition:
    t = (s or "").strip().lower()
    aliases = {
        "1": PairCondition.SAME_HEAVY,
        "2": PairCondition.RD_HEAVY,
        "3": PairCondition.C_HEAVY,
        "4": PairCondition.UNIFORM,
        "dd": PairCondition.SAME_HEAVY,
        "dr": PairCondition.RD_HEAVY,
        "dc": PairCondition.C_HEAVY,
        "dcr": PairCondition.UNIFORM,
    }
    if t in aliases:
        return aliases[t]
    for c in PairCondition:
        if c.value == t:
            return c
    raise ValueError(
        f"未知 pair_condition={s!r}，应为 same_heavy|rd_heavy|c_heavy|uniform、"
        f"1–4 或中性代号 dd|dr|dc|dcr"
    )


def _valid_next_for_category(prev: str, category: str) -> List[str]:
    if category == "SAME":
        return [prev]
    if category == "DIFF_NO_C":
        if prev == "C":
            return []
        return ["D"] if prev == "R" else ["R"]
    if category == "DIFF_WITH_C":
        if prev == "C":
            return ["R", "D"]
        return ["C"]
    return list(RDC_MODES)


def _sample_next_mode(prev: str, condition: PairCondition, rng: random.Random) -> str:
    if condition == PairCondition.UNIFORM:
        return rng.choice(RDC_MODES)

    w_same, w_rd, w_c = _EDGE_CATEGORY_WEIGHTS[condition]
    cats = ["SAME", "DIFF_NO_C", "DIFF_WITH_C"]
    weights = [w_same, w_rd, w_c]
    options: List[Tuple[str, List[str], float]] = []
    for cat, w in zip(cats, weights):
        nxt = _valid_next_for_category(prev, cat)
        if nxt:
            options.append((cat, nxt, w))
    if not options:
        return rng.choice(RDC_MODES)
    total = sum(o[2] for o in options)
    r = rng.random() * total
    acc = 0.0
    for _, nxt_list, w in options:
        acc += w
        if r <= acc:
            return rng.choice(nxt_list)
    return rng.choice(options[-1][1])


def build_mode_sequence_disjoint_pairs(
    length: int,
    condition: PairCondition,
    rng: random.Random,
) -> Tuple[List[str], bool]:
    """
    每对内 (2k, 2k+1) 独立采样 (m0,m1)：m0 均匀，m1 按条件由 m0 转移。
    奇数长度时最后一格仅 m_last，无对内边。
    返回 (modes, trailing_singleton)。
    """
    if length <= 0:
        return [], False
    modes: List[str] = []
    n_pairs = length // 2
    for _ in range(n_pairs):
        m0 = rng.choice(RDC_MODES)
        m1 = _sample_next_mode(m0, condition, rng)
        modes.extend([m0, m1])
    trailing = length % 2 == 1
    if trailing:
        modes.append(rng.choice(RDC_MODES))
    return modes, trailing


def _edge_triple(prev: str, nxt: str) -> str:
    if prev == nxt:
        return "SAME"
    if "C" not in (prev, nxt):
        return "DIFF_NO_C"
    return "DIFF_WITH_C"


def edge_histograms_from_modes_disjoint(modes: List[str]) -> Dict[str, Any]:
    """仅统计对内边 (modes[2k], modes[2k+1])。"""
    triple: Dict[str, int] = {"SAME": 0, "DIFF_NO_C": 0, "DIFF_WITH_C": 0}
    pair9: Dict[str, int] = {}
    for a in RDC_MODES:
        for b in RDC_MODES:
            pair9[f"{a}{b}"] = 0
    n_pairs = len(modes) // 2
    for k in range(n_pairs):
        p, q = modes[2 * k], modes[2 * k + 1]
        triple[_edge_triple(p, q)] += 1
        pair9[f"{p}{q}"] += 1
    return {
        "edge_triple_counts": triple,
        "edge_pair_counts": pair9,
        "num_internal_edges": n_pairs,
        "histogram_scope": "disjoint_pairs_only",
    }


def bucket_and_index_pool(
    full_pool: List[PoolItem],
    transit_modes: List[str],
) -> Tuple[
    Dict[str, List[PoolItem]],
    Dict[Tuple[int, str], List[PoolItem]],
    Dict[int, List[PoolItem]],
    List[str],
]:
    """分桶 + (current_code, rdc) 索引 + current_code 索引。"""
    buckets: Dict[str, List[PoolItem]] = {x: [] for x in RDC_MODES}
    by_start_mode: Dict[Tuple[int, str], List[PoolItem]] = {}
    by_start: Dict[int, List[PoolItem]] = {}
    warnings: List[str] = []
    for it in full_pool:
        rdc = pool_item_to_rdc(it, transit_modes)
        if rdc is None:
            warnings.append(f"skip_non_instant:{it[0][:48]}")
            continue
        buckets[rdc].append(it)
        c = it[1]
        by_start_mode.setdefault((c, rdc), []).append(it)
        by_start.setdefault(c, []).append(it)
    return buckets, by_start_mode, by_start, warnings


def assign_pool_with_pair_chaining(
    modes: List[str],
    buckets: Dict[str, List[PoolItem]],
    by_start_mode: Dict[Tuple[int, str], List[PoolItem]],
    by_start: Dict[int, List[PoolItem]],
    rng: random.Random,
    max_tries_per_pair: int = 150,
) -> Tuple[List[PoolItem], List[str]]:
    """
    对 (0,1),(2,3),… 满足 first[5]==second[1] 且方式匹配 modes。
    跨对无状态约束。奇数尾单从 modes[-1] 桶抽。
    """
    out: List[PoolItem] = []
    warns: List[str] = []
    nonempty_modes = [m for m in RDC_MODES if buckets[m]]
    if not nonempty_modes:
        return [], ["all_buckets_empty"]

    def pool_for_mode(m: str) -> List[PoolItem]:
        p = buckets.get(m, [])
        if p:
            return p
        fb = rng.choice(nonempty_modes)
        warns.append(f"bucket_empty_mode_{m}_used_{fb}")
        return buckets[fb]

    n_pairs = len(modes) // 2
    for k in range(n_pairs):
        i0, i1 = 2 * k, 2 * k + 1
        m0, m1 = modes[i0], modes[i1]
        pool0 = pool_for_mode(m0)
        first: PoolItem | None = None
        second: PoolItem | None = None
        for _ in range(max_tries_per_pair):
            cand_first = rng.choice(pool0)
            need_start = cand_first[5]
            cand_second = by_start_mode.get((need_start, m1), [])
            if cand_second:
                first, second = cand_first, rng.choice(cand_second)
                break
        if first is None or second is None:
            cand_first = rng.choice(pool0)
            need_start = cand_first[5]
            state_cands = by_start.get(need_start, [])
            if state_cands:
                second = rng.choice(state_cands)
                first = cand_first
                warns.append(f"pair_{k}_mode_fallback_kept_state_need_{need_start}_wanted_m1_{m1}")
            else:
                pool1 = pool_for_mode(m1)
                second = rng.choice(pool1)
                first = cand_first
                warns.append(f"pair_{k}_state_fallback_no_start_{need_start}_wanted_m1_{m1}")
        out.append(first)
        out.append(second)

    if len(modes) % 2 == 1:
        mt = modes[-1]
        poolt = pool_for_mode(mt)
        out.append(rng.choice(poolt))

    return out, warns


def _eligible_instant_items(buckets: Dict[str, List[PoolItem]]) -> List[PoolItem]:
    out: List[PoolItem] = []
    for m in RDC_MODES:
        out.extend(buckets.get(m, []))
    return out


def assign_pool_with_pair_chaining_test_coverage(
    modes: List[str],
    buckets: Dict[str, List[PoolItem]],
    by_start_mode: Dict[Tuple[int, str], List[PoolItem]],
    by_start: Dict[int, List[PoolItem]],
    rng: random.Random,
    eligible: List[PoolItem],
    max_tries_per_pair: int = 280,
) -> Tuple[List[PoolItem], List[str], Dict[str, Any]]:
    """
    与 assign_pool_with_pair_chaining 相同的成对内链式与方式约束，但优先消耗 eligible 中尚未出现的池项，
    使测试序列在长度允许时尽量覆盖每条 instant_transit（R/D/C）边各至少一次；不足长度或结构无解时允许重复并记警告。
    """
    out: List[PoolItem] = []
    warns: List[str] = []
    unused: Set[PoolItem] = set(eligible)
    nonempty_modes = [m for m in RDC_MODES if buckets[m]]
    if not nonempty_modes:
        return [], ["all_buckets_empty"], {
            "eligible_instant_transit_items": 0,
            "test_question_count": len(modes),
            "uncovered_count": 0,
            "uncovered_qid_prefixes": [],
        }

    if len(modes) < len(eligible):
        warns.append(
            f"test_questions_lt_eligible_edges_len_{len(modes)}_eligible_{len(eligible)}"
        )

    def pool_for_mode(m: str) -> List[PoolItem]:
        p = buckets.get(m, [])
        if p:
            return p
        fb = rng.choice(nonempty_modes)
        warns.append(f"bucket_empty_mode_{m}_used_{fb}")
        return buckets[fb]

    def pick_pair(k: int, m0: str, m1: str) -> Tuple[PoolItem, PoolItem]:
        pool0 = pool_for_mode(m0)
        first: Optional[PoolItem] = None
        second: Optional[PoolItem] = None
        for _ in range(max_tries_per_pair):
            pool0u = [x for x in pool0 if x in unused]
            src0 = pool0u if pool0u else pool0
            cand_first = rng.choice(src0)
            need_start = cand_first[5]
            sec_all = by_start_mode.get((need_start, m1), [])
            if not sec_all:
                continue
            sec_u = [x for x in sec_all if x in unused and x is not cand_first]
            if sec_u:
                first, second = cand_first, rng.choice(sec_u)
                break
            first, second = cand_first, rng.choice(sec_all)
            break
        if first is None or second is None:
            cand_first = rng.choice(pool0)
            need_start = cand_first[5]
            state_cands = by_start.get(need_start, [])
            if state_cands:
                second = rng.choice(state_cands)
                first = cand_first
                warns.append(f"pair_{k}_mode_fallback_kept_state_need_{need_start}_wanted_m1_{m1}")
            else:
                pool1 = pool_for_mode(m1)
                second = rng.choice(pool1)
                first = cand_first
                warns.append(f"pair_{k}_state_fallback_no_start_{need_start}_wanted_m1_{m1}")
        return first, second

    n_pairs = len(modes) // 2
    for k in range(n_pairs):
        m0, m1 = modes[2 * k], modes[2 * k + 1]
        first, second = pick_pair(k, m0, m1)
        out.append(first)
        out.append(second)
        for it in (first, second):
            unused.discard(it)

    if len(modes) % 2 == 1:
        mt = modes[-1]
        poolt = pool_for_mode(mt)
        uu = [x for x in poolt if x in unused]
        pick = rng.choice(uu if uu else poolt)
        out.append(pick)
        unused.discard(pick)

    cov_meta: Dict[str, Any] = {
        "eligible_instant_transit_items": len(eligible),
        "test_question_count": len(modes),
        "uncovered_count": len(unused),
        "uncovered_qid_prefixes": [x[0][:48] for x in list(unused)[:24]],
    }
    if unused:
        warns.append(f"test_uncovered_edges_{len(unused)}")
    return out, warns, cov_meta


def build_sequenced_pools(
    full_pool: List[PoolItem],
    transit_modes: List[str],
    learning_length: int,
    test_length: int,
    condition: PairCondition,
    rng: random.Random,
) -> Tuple[List[PoolItem], List[PoolItem], Dict[str, Any]]:
    buckets, by_start_mode, by_start, bw = bucket_and_index_pool(full_pool, transit_modes)

    learn_modes, learn_trail = build_mode_sequence_disjoint_pairs(learning_length, condition, rng)

    eligible = _eligible_instant_items(buckets)
    if test_length <= len(learn_modes):
        test_modes = learn_modes[:test_length]
        test_trail = test_length % 2 == 1
        test_mode_source = "learning_prefix"
    else:
        extra_modes, _ = build_mode_sequence_disjoint_pairs(
            test_length - len(learn_modes), condition, random.Random(rng.randint(0, 2**31 - 1))
        )
        test_modes = learn_modes + extra_modes
        test_trail = test_length % 2 == 1
        test_mode_source = "learning_prefix_plus_generated"

    learning_pool, lw = assign_pool_with_pair_chaining(
        learn_modes, buckets, by_start_mode, by_start, rng
    )
    test_assign_rng = random.Random(rng.randint(0, 2**31 - 1))
    test_pool, tw, test_cov = assign_pool_with_pair_chaining_test_coverage(
        test_modes, buckets, by_start_mode, by_start, test_assign_rng, eligible
    )

    diag: Dict[str, Any] = {
        "pair_chain_spec": "disjoint_pairs_2k_2k1",
        "bucket_sizes": {k: len(v) for k, v in buckets.items()},
        "bucket_warnings": bw,
        "pair_assignment_warnings": {"learning": lw, "test": tw},
        "learning_assign_warnings": lw,
        "test_assign_warnings": tw,
        "learning_mode_sequence": learn_modes,
        "test_mode_sequence": test_modes,
        "test_mode_sequence_source": test_mode_source,
        "trailing_singleton_learning": learn_trail,
        "trailing_singleton_test": test_trail,
        "edge_histogram_learning": edge_histograms_from_modes_disjoint(learn_modes),
        "edge_histogram_test": edge_histograms_from_modes_disjoint(test_modes),
        "test_instant_transit_coverage": test_cov,
    }
    return learning_pool, test_pool, diag


# 兼容旧测试名：分桶逻辑与 bucket_and_index_pool 的 warnings 一致
def bucket_pool_by_rdc(
    full_pool: List[PoolItem],
    transit_modes: List[str],
) -> Tuple[Dict[str, List[PoolItem]], List[str]]:
    buckets, _, _, warnings = bucket_and_index_pool(full_pool, transit_modes)
    return buckets, warnings
