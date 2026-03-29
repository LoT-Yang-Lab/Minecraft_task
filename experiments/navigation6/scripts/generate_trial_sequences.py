#!/usr/bin/env python3
"""
为 Navigation6 正式实验生成固定双目标试次序列（按地图）。

默认行为：
- 为 app.experiment.main.EXPERIMENT_MAPS 中配置的地图生成序列；
- 每图生成 27 个 trial；
- 满足每个位置编码在 targetA / targetB 各出现同样次数；
- 每个 trial 满足 d(targetA, targetB) >= min_distance。

用法（项目根目录）：
  python experiments/navigation6/scripts/generate_trial_sequences.py
  python experiments/navigation6/scripts/generate_trial_sequences.py --trials 27 --seed 20260319
  python experiments/navigation6/scripts/generate_trial_sequences.py --maps map_1773511099.json map_1773512012.json
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import random
import sys
from collections import Counter, deque
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


GridPos = Tuple[int, int]


def _bootstrap_path() -> None:
    this_file = Path(__file__).resolve()
    project_root = this_file.parents[3]  # .../Minecraft8.0
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 Navigation6 固定双目标试次序列")
    parser.add_argument(
        "--maps",
        nargs="*",
        default=None,
        help="地图文件名列表（位于 assets/maps）；为空则使用正式实验默认地图。",
    )
    parser.add_argument("--trials", type=int, default=27, help="每张地图生成的 trial 数（默认 27）")
    parser.add_argument("--min-distance", type=int, default=1, help="targetA 与 targetB 的最短路下限（默认 1；小图可再调大）")
    parser.add_argument("--seed", type=int, default=20260319, help="伪随机种子（默认 20260319）")
    parser.add_argument("--max-attempts", type=int, default=5000, help="每张地图最大重试次数")
    parser.add_argument(
        "--distance-metric",
        choices=["manhattan", "action_graph"],
        default="manhattan",
        help="距离度量：manhattan(默认) 或 action_graph(按动作可达图最短路)。",
    )
    return parser.parse_args()


def _load_map_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _station_positions_from_transit(map_data: dict) -> Set[GridPos]:
    out: Set[GridPos] = set()
    for key in ("bus_lines", "metro_lines", "light_rail_lines", "subway_lines"):
        for line in map_data.get(key, []) or []:
            for s in line.get("stations", []) or []:
                if isinstance(s, (list, tuple)) and len(s) >= 2:
                    out.add((int(s[0]), int(s[1])))
    return out


def _build_codebook(map_data: dict) -> Tuple[Dict[GridPos, int], Dict[int, GridPos]]:
    """按 (gx, gy) 字典序构建 1..N 编码，规则与正式实验显示保持一致。"""
    cells: Set[GridPos] = set(tuple(p) for p in map_data.get("single_cells", []))
    obstacle_set: Set[GridPos] = set(tuple(p) for p in map_data.get("obstacle_map", []))
    cells |= _station_positions_from_transit(map_data)

    for room in map_data.get("rooms", []):
        logical = room.get("logical_pos")
        if not isinstance(logical, list) or len(logical) != 2:
            continue
        lx, ly = logical
        for dy in range(3):
            for dx in range(3):
                gx, gy = lx * 3 + dx, ly * 3 + dy
                if (gx, gy) not in obstacle_set:
                    cells.add((gx, gy))

    ordered = sorted(cells, key=lambda c: (c[0], c[1]))
    cell_to_code = {c: idx + 1 for idx, c in enumerate(ordered)}
    code_to_cell = {idx + 1: c for idx, c in enumerate(ordered)}
    return cell_to_code, code_to_cell


def _build_transition_graph(map_data: dict, cell_to_code: Dict[GridPos, int]) -> Dict[int, Set[int]]:
    """
    Navigation6：仅公交/地铁/轻轨站内「下一站」边（与 cogmap / 游戏一致）。
    """
    graph: Dict[int, Set[int]] = {code: set() for code in cell_to_code.values()}

    def add_edge(a: GridPos, b: GridPos) -> None:
        if a in cell_to_code and b in cell_to_code:
            graph[cell_to_code[a]].add(cell_to_code[b])

    loop = True
    all_lines: List[dict] = []
    for key in ("bus_lines", "metro_lines", "light_rail_lines", "subway_lines"):
        all_lines.extend(map_data.get(key, []) or [])

    for line in all_lines:
        path = [tuple(p) for p in line.get("path", [])]
        if not path:
            continue
        stations = set(tuple(s) for s in line.get("stations", []))
        station_indices = [i for i, pos in enumerate(path) if pos in stations]
        if 0 not in station_indices:
            station_indices.insert(0, 0)
        if (len(path) - 1) not in station_indices:
            station_indices.append(len(path) - 1)
        station_indices = sorted(set(station_indices))
        if not station_indices:
            continue
        for j, idx in enumerate(station_indices):
            nxt = j + 1
            if nxt >= len(station_indices):
                if not loop:
                    continue
                nxt = 0
            add_edge(path[idx], path[station_indices[nxt]])

    return graph


def _pairwise_manhattan_distances(code_to_cell: Dict[int, GridPos]) -> Dict[int, Dict[int, int]]:
    distances: Dict[int, Dict[int, int]] = {}
    for a, posa in code_to_cell.items():
        distances[a] = {}
        for b, posb in code_to_cell.items():
            distances[a][b] = abs(posa[0] - posb[0]) + abs(posa[1] - posb[1])
    return distances


def _shortest_path_distances(graph: Dict[int, Set[int]]) -> Dict[int, Dict[int, int]]:
    """在无权无向图上做全源 BFS。不可达记为大数。"""
    inf = 10**9
    undirected: Dict[int, Set[int]] = {node: set() for node in graph.keys()}
    for u, next_nodes in graph.items():
        for v in next_nodes:
            undirected[u].add(v)
            undirected[v].add(u)

    distances: Dict[int, Dict[int, int]] = {}
    for src in undirected.keys():
        d = {node: inf for node in undirected.keys()}
        q = deque([(src, 0)])
        seen = {src}
        while q:
            u, dist = q.popleft()
            d[u] = dist
            for v in undirected.get(u, ()):
                if v in seen:
                    continue
                seen.add(v)
                q.append((v, dist + 1))
        distances[src] = d
    return distances


def _is_valid_pair(a: int, b: int, distances: Dict[int, Dict[int, int]], min_distance: int) -> bool:
    if a == b:
        return False
    dab = distances[a][b]
    if dab >= 10**9:
        return False
    return dab >= min_distance


def _generate_balanced_sequence(
    codes: List[int],
    trials: int,
    min_distance: int,
    distances: Dict[int, Dict[int, int]],
    rng: random.Random,
    max_attempts: int,
) -> Optional[List[Tuple[int, int]]]:
    if trials <= 0 or not codes:
        return None
    n = len(codes)
    if trials % n != 0:
        raise ValueError(f"trials={trials} 不能被节点数 {n} 整除，无法严格平衡 targetA/targetB 频次。")

    per_role_count = trials // n
    a_pool = []
    for c in codes:
        a_pool.extend([c] * per_role_count)

    for _attempt in range(max_attempts):
        rng.shuffle(a_pool)
        a_list = list(a_pool)
        b_remaining = {c: per_role_count for c in codes}
        b_list = [-1] * trials
        unresolved = set(range(trials))

        # 使用 MRV 回溯：优先填候选更少的位置，提高成功率。
        def backtrack() -> bool:
            if not unresolved:
                return True

            # 动态选最难填位置
            best_idx = None
            best_candidates = None
            for idx in unresolved:
                a = a_list[idx]
                cand = [
                    b for b in codes
                    if b_remaining[b] > 0 and _is_valid_pair(a, b, distances, min_distance)
                ]
                if best_candidates is None or len(cand) < len(best_candidates):
                    best_idx = idx
                    best_candidates = cand
                if best_candidates is not None and len(best_candidates) == 0:
                    return False

            assert best_idx is not None and best_candidates is not None
            rng.shuffle(best_candidates)
            unresolved.remove(best_idx)
            for b in best_candidates:
                b_remaining[b] -= 1
                b_list[best_idx] = b
                if backtrack():
                    return True
                b_list[best_idx] = -1
                b_remaining[b] += 1
            unresolved.add(best_idx)
            return False

        if backtrack():
            return list(zip(a_list, b_list))

    return None


def _validate_sequence(
    seq: List[Tuple[int, int]],
    codes: List[int],
    min_distance: int,
    distances: Dict[int, Dict[int, int]],
) -> None:
    a_count = Counter(a for a, _ in seq)
    b_count = Counter(b for _, b in seq)
    for c in codes:
        if a_count[c] != b_count[c]:
            raise ValueError(f"编码 {c} 的 A/B 频次不一致: A={a_count[c]}, B={b_count[c]}")
    for i, (a, b) in enumerate(seq, start=1):
        if not _is_valid_pair(a, b, distances, min_distance):
            raise ValueError(f"trial#{i} 不满足约束: A={a}, B={b}")


def _save_sequence(
    output_path: str,
    map_id: str,
    map_filename: str,
    code_to_cell: Dict[int, GridPos],
    sequence: List[Tuple[int, int]],
    min_distance: int,
    seed: int,
    distance_metric: str,
) -> None:
    payload = {
        "version": "1.0",
        "map_id": map_id,
        "map_file": map_filename,
        "generated_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "generator": {
            "type": "balanced_dual_targets",
            "seed": seed,
            "min_distance": min_distance,
            "distance_metric": distance_metric,
        },
        "total_trials": len(sequence),
        "codebook": [
            {"code": code, "gx": pos[0], "gy": pos[1]}
            for code, pos in sorted(code_to_cell.items(), key=lambda x: x[0])
        ],
        "trials": [
            {"trial_id": i + 1, "targetA": a, "targetB": b}
            for i, (a, b) in enumerate(sequence)
        ],
    }
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def main() -> int:
    _bootstrap_path()
    args = _parse_args()

    from experiments.navigation6.app.experiment.main import EXPERIMENT_MAPS
    from experiments.navigation6.app.paths import maps_dir, trial_sequences_dir

    default_maps = [filename for _, filename in EXPERIMENT_MAPS]
    map_files = args.maps if args.maps else default_maps
    rng = random.Random(args.seed)

    os.makedirs(trial_sequences_dir(), exist_ok=True)
    for map_filename in map_files:
        map_path = os.path.join(maps_dir(), map_filename)
        if not os.path.exists(map_path):
            raise FileNotFoundError(f"地图文件不存在: {map_path}")

        map_data = _load_map_json(map_path)
        cell_to_code, code_to_cell = _build_codebook(map_data)
        if len(code_to_cell) == 0:
            raise ValueError(f"地图 {map_filename} 无可编码节点，无法生成试次表。")
        if args.distance_metric == "action_graph":
            graph = _build_transition_graph(map_data, cell_to_code)
            distances = _shortest_path_distances(graph)
        else:
            distances = _pairwise_manhattan_distances(code_to_cell)
        codes = sorted(code_to_cell.keys())

        seq = _generate_balanced_sequence(
            codes=codes,
            trials=args.trials,
            min_distance=args.min_distance,
            distances=distances,
            rng=rng,
            max_attempts=args.max_attempts,
        )
        if seq is None:
            raise RuntimeError(
                f"地图 {map_filename} 在 max_attempts={args.max_attempts} 内未找到可行序列。"
            )
        _validate_sequence(seq, codes=codes, min_distance=args.min_distance, distances=distances)

        map_id = os.path.splitext(os.path.basename(map_filename))[0]
        out_path = os.path.join(trial_sequences_dir(), f"{map_id}.json")
        _save_sequence(
            output_path=out_path,
            map_id=map_id,
            map_filename=map_filename,
            code_to_cell=code_to_cell,
            sequence=seq,
            min_distance=args.min_distance,
            seed=args.seed,
            distance_metric=args.distance_metric,
        )
        print(f"[OK] {map_filename} -> {out_path} (trials={len(seq)})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

