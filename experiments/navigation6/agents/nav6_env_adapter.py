from __future__ import annotations

import json
import os
from collections import deque
from typing import Dict, List, Optional, Set, Tuple

from experiments.navigation6.agents.base_agent import AgentAction
from experiments.navigation6.app.experiment.game import GameNavigation6
from experiments.navigation6.app.experiment.main import build_position_encoding
from experiments.navigation6.app.common.transit_action_display import (
    transit_mode_action_with_direction_label,
)
from experiments.navigation6.app.paths import maps_dir, trial_sequences_dir


GridPos = Tuple[int, int]


def resolve_map_path(filename: str) -> str:
    return os.path.abspath(os.path.join(maps_dir(), filename))


def resolve_trial_sequence_path(map_filename: str) -> str:
    map_id = os.path.splitext(os.path.basename(map_filename))[0]
    return os.path.abspath(os.path.join(trial_sequences_dir(), f"{map_id}.json"))


def load_trial_sequence(map_filename: str) -> List[Tuple[int, int]]:
    seq_path = resolve_trial_sequence_path(map_filename)
    if not os.path.exists(seq_path):
        raise FileNotFoundError(f"缺少试次表：{seq_path}")
    with open(seq_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    trials = payload.get("trials", [])
    out: List[Tuple[int, int]] = []
    for rec in trials:
        out.append((int(rec["targetA"]), int(rec["targetB"])))
    if not out:
        raise ValueError(f"试次表为空：{seq_path}")
    return out


def clear_single_target_in_game(game: GameNavigation6) -> None:
    for room in getattr(game, "rooms", {}).values():
        if getattr(room, "is_target", False):
            room.is_target = False
    game.original_target_pos = None


def build_position_encoding_for_agent(game: GameNavigation6) -> Tuple[Dict[GridPos, int], Dict[int, GridPos]]:
    cell_to_code, code_to_cell, _ = build_position_encoding(game)
    return cell_to_code, code_to_cell


def get_current_code(game: GameNavigation6, cell_to_code: Dict[GridPos, int]) -> int:
    return cell_to_code.get((game.player_x, game.player_y), 0)


def get_available_actions(game: GameNavigation6, cell_to_code: Dict[GridPos, int]) -> List[AgentAction]:
    px, py = game.player_x, game.player_y
    actions: List[AgentAction] = []
    modes = getattr(game, "transit_modes", []) or []
    for line_idx, next_pos in game.get_instant_subway_next_stations(px, py):
        next_code = cell_to_code.get(next_pos, 0)
        if next_code <= 0:
            continue
        m = modes[line_idx] if line_idx < len(modes) else "metro"
        label = transit_mode_action_with_direction_label(m, "next")
        actions.append(AgentAction("instant_transit_next", line_idx, next_code, label))
    for line_idx, prev_pos in game.get_instant_subway_prev_stations(px, py):
        prev_code = cell_to_code.get(prev_pos, 0)
        if prev_code <= 0:
            continue
        m = modes[line_idx] if line_idx < len(modes) else "metro"
        label = transit_mode_action_with_direction_label(m, "prev")
        actions.append(AgentAction("instant_transit_prev", line_idx, prev_code, label))
    return actions


def execute_action(game: GameNavigation6, action: AgentAction) -> bool:
    if action.action_key in ("instant_transit_next", "instant_subway_next"):
        if action.extra is None:
            return False
        return game.instant_subway_to_next_station(int(action.extra))
    if action.action_key in ("instant_transit_prev", "instant_subway_prev"):
        if action.extra is None:
            return False
        return game.instant_subway_to_prev_station(int(action.extra))
    return False


def load_map_json(map_filename: str) -> dict:
    path = resolve_map_path(map_filename)
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


def build_codebook_from_map_data(map_data: dict) -> Tuple[Dict[GridPos, int], Dict[int, GridPos]]:
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


def build_transition_graph_from_map_data(map_data: dict, cell_to_code: Dict[GridPos, int]) -> Dict[int, Set[int]]:
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


def build_neighbors_for_astar(graph_by_code: Dict[int, Set[int]]) -> List[List[int]]:
    """返回 0-indexed 邻接表，供 solve_astar.astar_path 使用。"""
    n = len(graph_by_code)
    neighbors: List[List[int]] = [[] for _ in range(n)]
    for code, next_codes in graph_by_code.items():
        src = code - 1
        for nc in sorted(next_codes):
            neighbors[src].append(nc - 1)
    return neighbors


def shortest_path_len_unweighted(graph_by_code: Dict[int, Set[int]], start_code: int, goal_code: int) -> Optional[int]:
    if start_code == goal_code:
        return 0
    q = deque([(start_code, 0)])
    seen = {start_code}
    while q:
        cur, dist = q.popleft()
        for nxt in graph_by_code.get(cur, ()):
            if nxt in seen:
                continue
            if nxt == goal_code:
                return dist + 1
            seen.add(nxt)
            q.append((nxt, dist + 1))
    return None
