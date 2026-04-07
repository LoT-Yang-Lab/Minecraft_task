"""Proposal-5 trial scheduling helpers for Navigation6.

This module hardcodes the exact ordered start-goal catalog shown in the
user-provided Tables 3, 4, and 5, then builds five-session schedules that
follow Table 7.

Key choices:
1. The pair catalog is copied directly from the specification rather than
   inferred from the runtime graph.
2. Every 24-slot search block uses quotas 7 grid-dominant, 7 loop-dominant,
   and 10 tie trials.
3. Pair sampling within a category is weighted by multiplicity ``m``.
4. Immediate pair repetitions are disallowed within each 24-slot block.
5. Crafting trials are placeholders only, but keep the same sampled pair
   metadata so the full five-session plan is explicit and exportable.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Literal, Optional, Sequence, Tuple

Category = Literal["grid", "loop", "tie"]


@dataclass(frozen=True)
class PairSpec:
    pair_id: str
    category: Category
    start: int
    goal: int
    d_grid: int
    d_loop: int
    multiplicity: int
    grid_paths: int
    loop_paths: int


DEFAULT_BLOCK_QUOTAS: Dict[Category, int] = {"grid": 7, "loop": 7, "tie": 10}


# Tables 3-5 from the provided proposal material.
_PAIR_ROWS: Dict[Category, List[Tuple[str, int, int, int, int, int]]] = {
    "grid": [
        ("G01", 1, 5, 2, 3, 2),
        ("G02", 1, 7, 2, 3, 1),
        ("G03", 2, 4, 2, 4, 1),
        ("G04", 2, 6, 2, 3, 2),
        ("G05", 2, 8, 2, 3, 1),
        ("G06", 3, 1, 2, 3, 1),
        ("G07", 3, 5, 2, 3, 2),
        ("G08", 4, 2, 2, 3, 2),
        ("G09", 4, 6, 2, 3, 1),
        ("G10", 4, 8, 2, 4, 2),
        ("G11", 5, 1, 2, 3, 2),
        ("G12", 5, 3, 2, 3, 2),
        ("G13", 5, 7, 2, 3, 2),
        ("G14", 5, 9, 2, 3, 2),
        ("G15", 6, 2, 2, 4, 2),
        ("G16", 6, 4, 2, 3, 1),
        ("G17", 6, 8, 2, 3, 2),
        ("G18", 7, 5, 2, 3, 2),
        ("G19", 7, 9, 2, 3, 1),
        ("G20", 8, 2, 2, 3, 1),
        ("G21", 8, 4, 2, 3, 2),
        ("G22", 8, 6, 2, 4, 2),
        ("G23", 9, 3, 2, 3, 1),
        ("G24", 9, 5, 2, 3, 2),
    ],
    "loop": [
        ("L01", 1, 6, 3, 2, 1),
        ("L02", 1, 9, 4, 2, 1),
        ("L03", 2, 9, 3, 2, 1),
        ("L04", 3, 7, 4, 2, 1),
        ("L05", 3, 8, 3, 2, 1),
        ("L06", 4, 3, 3, 2, 1),
        ("L07", 6, 7, 3, 2, 1),
        ("L08", 7, 2, 3, 2, 1),
        ("L09", 7, 3, 4, 2, 1),
        ("L10", 8, 1, 3, 2, 1),
        ("L11", 9, 1, 4, 2, 1),
        ("L12", 9, 4, 3, 2, 1),
    ],
    "tie": [
        ("T01", 1, 8, 3, 3, 4),
        ("T02", 2, 7, 3, 3, 4),
        ("T03", 3, 4, 3, 3, 4),
        ("T04", 4, 9, 3, 3, 4),
        ("T05", 6, 1, 3, 3, 4),
        ("T06", 7, 6, 3, 3, 4),
        ("T07", 8, 3, 3, 3, 4),
        ("T08", 9, 2, 3, 3, 4),
    ],
}

_PAIR_CATALOG: Optional[Dict[Category, List[PairSpec]]] = None
_FULL_PAIR_CATALOG: Optional[Dict[Category, List[PairSpec]]] = None


def _row_to_spec(category: Category, row: Tuple[str, int, int, int, int, int]) -> PairSpec:
    pair_id, start, goal, d_grid, d_loop, multiplicity = row
    if category == "grid":
        grid_paths, loop_paths = multiplicity, 0
    elif category == "loop":
        grid_paths, loop_paths = 0, multiplicity
    else:
        # The tie table only reports a single multiplicity value; we mirror it
        # into both fields so downstream metadata stays self-contained.
        grid_paths, loop_paths = multiplicity, multiplicity
    return PairSpec(
        pair_id=pair_id,
        category=category,
        start=start,
        goal=goal,
        d_grid=d_grid,
        d_loop=d_loop,
        multiplicity=multiplicity,
        grid_paths=grid_paths,
        loop_paths=loop_paths,
    )


def get_pair_catalog() -> Dict[Category, List[PairSpec]]:
    """Return the original 44-pair catalog from Tables 3-5."""
    global _PAIR_CATALOG
    if _PAIR_CATALOG is None:
        _PAIR_CATALOG = {
            category: [_row_to_spec(category, row) for row in rows]
            for category, rows in _PAIR_ROWS.items()
        }
    return _PAIR_CATALOG


# ── Full pair enumeration (all 72 directed pairs on graph9) ──────────────

def _enumerate_all_graph_pairs() -> Dict[Category, List[PairSpec]]:
    """Enumerate ALL 72 directed (start, goal) pairs on the 9-node graph,
    classify each as grid/loop/tie, and return as PairSpec objects.

    Classification rules:
    - **grid**: d_full == d_grid and no shortest path uses the ring edge
    - **loop**: d_full < d_grid (ring provides a genuine shortcut)
    - **tie**: d_full == d_grid but at least one shortest path uses the ring

    This uses BFS on graph9 with and without the ring edges.
    """
    from collections import deque

    # Graph structure from graph9.py
    node_ids = list(range(1, 10))
    node_pos = {
        1: (0, 0), 2: (0, 1), 3: (0, 2),
        4: (1, 0), 5: (1, 1), 6: (1, 2),
        7: (2, 0), 8: (2, 1), 9: (2, 2),
    }
    ring_next = {1: 3, 3: 9, 9: 7, 7: 1}

    def grid_neighbors(n: int) -> List[int]:
        r, c = node_pos[n]
        nbrs: List[int] = []
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr <= 2 and 0 <= nc <= 2:
                nbrs.append(nr * 3 + nc + 1)
        return nbrs

    def full_neighbors(n: int) -> List[int]:
        nbrs = list(grid_neighbors(n))
        if n in ring_next:
            nbrs.append(ring_next[n])
        return nbrs

    def bfs_dist(start: int, goal: int, neighbor_fn) -> int:
        if start == goal:
            return 0
        visited = {start}
        q: deque = deque([(start, 0)])
        while q:
            cur, d = q.popleft()
            for nb in neighbor_fn(cur):
                if nb == goal:
                    return d + 1
                if nb not in visited:
                    visited.add(nb)
                    q.append((nb, d + 1))
        return 999

    def count_shortest_paths(start: int, goal: int, neighbor_fn) -> Tuple[int, int]:
        """Return (distance, path_count) using BFS."""
        if start == goal:
            return 0, 0
        dist_to = {start: 0}
        count_to = {start: 1}
        q: deque = deque([start])
        while q:
            cur = q.popleft()
            for nb in neighbor_fn(cur):
                nd = dist_to[cur] + 1
                if nb not in dist_to:
                    dist_to[nb] = nd
                    count_to[nb] = count_to[cur]
                    q.append(nb)
                elif dist_to[nb] == nd:
                    count_to[nb] += count_to[cur]
        return dist_to.get(goal, 999), count_to.get(goal, 0)

    def has_ring_shortest_path(start: int, goal: int, d_full: int) -> bool:
        """Check if any shortest path from start to goal uses a ring edge."""
        q: deque = deque([(start, False, 0)])
        visited: Dict[Tuple[int, bool], int] = {(start, False): 0}
        while q:
            cur, used_ring, d = q.popleft()
            if d > d_full:
                break
            if cur == goal and d == d_full and used_ring:
                return True
            # Grid moves
            for nb in grid_neighbors(cur):
                state = (nb, used_ring)
                if state not in visited or visited[state] > d + 1:
                    if d + 1 <= d_full:
                        visited[state] = d + 1
                        q.append((nb, used_ring, d + 1))
            # Ring move
            if cur in ring_next:
                nb = ring_next[cur]
                state = (nb, True)
                if state not in visited or visited[state] > d + 1:
                    if d + 1 <= d_full:
                        visited[state] = d + 1
                        q.append((nb, True, d + 1))
        return False

    # Build the existing catalog lookup for (start, goal)
    existing: Dict[Tuple[int, int], Tuple[str, Category]] = {}
    for cat, rows in _PAIR_ROWS.items():
        for row in rows:
            existing[(row[1], row[2])] = (row[0], cat)

    # Counters for new IDs per category
    new_id_counter = {"grid": 24, "loop": 12, "tie": 8}  # continue after existing
    result: Dict[Category, List[PairSpec]] = {"grid": [], "loop": [], "tie": []}

    for s in node_ids:
        for g in node_ids:
            if s == g:
                continue

            d_grid = bfs_dist(s, g, grid_neighbors)
            d_full = bfs_dist(s, g, full_neighbors)

            if d_full < d_grid:
                cat: Category = "loop"
            else:
                # d_full == d_grid; check if any shortest path uses ring
                if has_ring_shortest_path(s, g, d_full):
                    cat = "tie"
                else:
                    cat = "grid"

            # Compute path counts
            _, grid_path_count = count_shortest_paths(s, g, grid_neighbors)
            _, full_path_count = count_shortest_paths(s, g, full_neighbors)

            if cat == "grid":
                multiplicity = grid_path_count
                gp, lp = multiplicity, 0
            elif cat == "loop":
                # loop_paths = full paths - grid paths at same distance
                # but for loop d_full < d_grid, so all shortest paths use ring
                multiplicity = full_path_count
                gp, lp = 0, multiplicity
            else:  # tie
                multiplicity = full_path_count
                gp, lp = grid_path_count, full_path_count - grid_path_count

            if (s, g) in existing:
                pair_id = existing[(s, g)][0]
            else:
                new_id_counter[cat] += 1
                prefix = {"grid": "G", "loop": "L", "tie": "T"}[cat]
                pair_id = f"{prefix}{new_id_counter[cat]:02d}"

            spec = PairSpec(
                pair_id=pair_id,
                category=cat,
                start=s,
                goal=g,
                d_grid=d_grid,
                d_loop=d_full,
                multiplicity=multiplicity,
                grid_paths=gp,
                loop_paths=lp,
            )
            result[cat].append(spec)

    # Sort: existing catalog pairs first (by original order), then new pairs
    for cat in result:
        existing_ids = {row[0] for row in _PAIR_ROWS[cat]}
        existing_list = [p for p in result[cat] if p.pair_id in existing_ids]
        new_list = [p for p in result[cat] if p.pair_id not in existing_ids]
        # Preserve original catalog order for existing pairs
        id_order = {row[0]: i for i, row in enumerate(_PAIR_ROWS[cat])}
        existing_list.sort(key=lambda p: id_order.get(p.pair_id, 999))
        new_list.sort(key=lambda p: (p.start, p.goal))
        result[cat] = existing_list + new_list

    return result


def get_full_pair_catalog() -> Dict[Category, List[PairSpec]]:
    """Return ALL possible pairs on graph9 (72 total), grouped by category.

    Includes the original 44 catalog pairs (first in each list) plus all
    remaining directed pairs that can be formed on the 9-node graph.
    Counts: 48 grid + 16 loop + 8 tie = 72 total.
    """
    global _FULL_PAIR_CATALOG
    if _FULL_PAIR_CATALOG is None:
        _FULL_PAIR_CATALOG = _enumerate_all_graph_pairs()
    return _FULL_PAIR_CATALOG


def _weighted_choice(
    pairs: Sequence[PairSpec],
    rng: random.Random,
    last_pair_id: Optional[str],
) -> PairSpec:
    options = [pair for pair in pairs if pair.pair_id != last_pair_id]
    if not options:
        options = list(pairs)
    weights = [pair.multiplicity for pair in options]
    return rng.choices(options, weights=weights, k=1)[0]


def _build_category_sequence(quotas: Dict[Category, int], rng: random.Random) -> List[Category]:
    remaining = dict(quotas)
    sequence: List[Category] = []
    for _ in range(sum(remaining.values())):
        candidates = [category for category, left in remaining.items() if left > 0]
        weights = [remaining[category] for category in candidates]
        chosen = rng.choices(candidates, weights=weights, k=1)[0]
        sequence.append(chosen)
        remaining[chosen] -= 1
    return sequence


def generate_navigation_trials(
    seed: int,
    trial_count: int,
    quotas: Optional[Dict[Category, int]] = None,
) -> List[Dict[str, object]]:
    quotas = quotas or DEFAULT_BLOCK_QUOTAS
    if sum(quotas.values()) != trial_count:
        raise ValueError("Quota sum must equal trial_count")

    catalog = get_pair_catalog()
    rng = random.Random(seed)
    category_sequence = _build_category_sequence(quotas, rng)

    trials: List[Dict[str, object]] = []
    last_pair_id: Optional[str] = None
    for block_index, category in enumerate(category_sequence, start=1):
        chosen = _weighted_choice(catalog[category], rng, last_pair_id)
        last_pair_id = chosen.pair_id
        trials.append(
            {
                "index": block_index,
                "pair_id": chosen.pair_id,
                "category": chosen.category,
                "start": chosen.start,
                "goal": chosen.goal,
                "d_grid": chosen.d_grid,
                "d_loop": chosen.d_loop,
                "grid_paths": chosen.grid_paths,
                "loop_paths": chosen.loop_paths,
                "multiplicity": chosen.multiplicity,
            }
        )
    return trials


CRAFTING_MOCK_RECIPES = [
    "smelt_ingot",
    "craft_table",
    "brew_potion",
    "assemble_cart",
    "cook_stew",
    "forge_sword",
]


def _make_crafting_trial(
    pair_trial: Dict[str, object],
    rng: random.Random,
    session_number: int,
    craft_index: int,
) -> Dict[str, object]:
    return {
        "index": craft_index,
        "block_index": int(pair_trial["index"]),
        "task_id": f"S{session_number}_craft_{craft_index:02d}",
        "recipe": rng.choice(CRAFTING_MOCK_RECIPES),
        "pair_id": pair_trial["pair_id"],
        "category": pair_trial["category"],
        "start": pair_trial["start"],
        "goal": pair_trial["goal"],
        "d_grid": pair_trial["d_grid"],
        "d_loop": pair_trial["d_loop"],
        "grid_paths": pair_trial["grid_paths"],
        "loop_paths": pair_trial["loop_paths"],
        "multiplicity": pair_trial["multiplicity"],
    }


_NAVIGATION_FIRST = [
    {"session": 1, "domain": "navigation", "seed": 5101},
    {"session": 2, "domain": "crafting", "seed": 5102},
    {"session": 3, "domain": "navigation", "seed": 5103},
    {"session": 4, "domain": "crafting", "seed": 5104},
    {"session": 5, "domain": "mixed", "seed": 5105, "nav_first": True},
]

_CRAFTING_FIRST = [
    {"session": 1, "domain": "crafting", "seed": 5201},
    {"session": 2, "domain": "navigation", "seed": 5202},
    {"session": 3, "domain": "crafting", "seed": 5203},
    {"session": 4, "domain": "navigation", "seed": 5204},
    {"session": 5, "domain": "mixed", "seed": 5205, "nav_first": False},
]


def _session_template(order: str) -> List[Dict[str, object]]:
    if order == "navigation-first":
        return _NAVIGATION_FIRST
    if order == "crafting-first":
        return _CRAFTING_FIRST
    raise ValueError("order must be 'navigation-first' or 'crafting-first'")


def _alternate_types(length: int, nav_first: bool) -> List[str]:
    first = "navigation" if nav_first else "crafting"
    second = "crafting" if nav_first else "navigation"
    return [first if idx % 2 == 0 else second for idx in range(length)]


def build_session_schedule(order: str) -> Dict[str, object]:
    sessions: List[Dict[str, object]] = []

    for spec in _session_template(order):
        session_number = int(spec["session"])
        seed = int(spec["seed"])
        domain = str(spec["domain"])
        pair_block = generate_navigation_trials(seed=seed, trial_count=24, quotas=DEFAULT_BLOCK_QUOTAS)
        crafting_rng = random.Random(seed + 100_000)

        session_entry: Dict[str, object] = {
            "session": session_number,
            "domain": domain,
            "seed": seed,
        }

        navigation_trials: List[Dict[str, object]] = []
        crafting_trials: List[Dict[str, object]] = []
        combined_order: List[Dict[str, object]] = []

        if domain == "navigation":
            navigation_trials = [{**trial, "block_index": int(trial["index"])} for trial in pair_block]
            combined_order = [{"type": "navigation", "trial": trial} for trial in navigation_trials]

        elif domain == "crafting":
            for craft_index, pair_trial in enumerate(pair_block, start=1):
                craft_trial = _make_crafting_trial(pair_trial, crafting_rng, session_number, craft_index)
                crafting_trials.append(craft_trial)
                combined_order.append({"type": "crafting", "trial": craft_trial})

        elif domain == "mixed":
            nav_index = 0
            craft_index = 0
            task_types = _alternate_types(len(pair_block), bool(spec.get("nav_first", True)))
            for pair_trial, task_type in zip(pair_block, task_types):
                if task_type == "navigation":
                    nav_index += 1
                    nav_trial = {
                        **pair_trial,
                        "index": nav_index,
                        "block_index": int(pair_trial["index"]),
                    }
                    navigation_trials.append(nav_trial)
                    combined_order.append({"type": "navigation", "trial": nav_trial})
                else:
                    craft_index += 1
                    craft_trial = _make_crafting_trial(pair_trial, crafting_rng, session_number, craft_index)
                    crafting_trials.append(craft_trial)
                    combined_order.append({"type": "crafting", "trial": craft_trial})
        else:
            raise ValueError(f"Unsupported domain: {domain}")

        session_entry["navigation_trials"] = navigation_trials
        session_entry["crafting_trials"] = crafting_trials
        session_entry["combined_order"] = combined_order
        sessions.append(session_entry)

    catalog = get_pair_catalog()
    return {
        "order": order,
        "sessions": sessions,
        "catalog_sizes": {category: len(pairs) for category, pairs in catalog.items()},
        "default_block_quotas": DEFAULT_BLOCK_QUOTAS,
    }


def save_schedule(schedule: Dict[str, object], output_path: Path | str) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(schedule, fh, ensure_ascii=False, indent=2)