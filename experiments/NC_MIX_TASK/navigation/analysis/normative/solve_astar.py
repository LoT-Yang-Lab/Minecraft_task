"""
Navigation6 A* baseline (fully observed shortest path).

Nodes are position codes 1..N (1-indexed for external interfaces).
Edges are derived from cogmap_result["adj"] (0/1 adjacency, assumed symmetric).
Edge cost is 1 for all valid edges.

The main exported helper is `build_astar_next_dict(cogmap_result)` which returns:
  state_code (1..N) -> recommended_next_code (1..N)

Heuristic default uses graph distance to target if available (distance_vector or distances_by_code).
"""

from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


def build_graph_from_adj(adj: Sequence[Sequence[int]]) -> List[List[int]]:
    """
    Build neighbor lists from an NxN adjacency matrix.
    Returns a 0-indexed neighbors list: neighbors[i] -> list of j indices.
    """
    n = len(adj)
    neighbors: List[List[int]] = [[] for _ in range(n)]
    for i in range(n):
        row = adj[i]
        # Be tolerant to numpy arrays and python lists.
        for j in range(n):
            if i == j:
                continue
            if row[j] > 0:
                neighbors[i].append(j)
    return neighbors


def _heuristic_from_cogmap(cogmap_result: Dict, goal_idx: int) -> Optional[List[float]]:
    """
    Try to obtain a consistent, admissible heuristic h(s)=d_graph(s,goal) in steps.
    Returns a 0-indexed list length N, or None if unavailable.
    """
    n = int(cogmap_result.get("N") or 0)
    if n <= 0:
        return None

    dv = cogmap_result.get("distance_vector")
    if isinstance(dv, (list, tuple)) and len(dv) == n:
        # distance_vector is 0-indexed over nodes (code 1..N)
        out: List[float] = []
        for d in dv:
            if d is None:
                out.append(float("inf"))
            else:
                try:
                    dd = float(d)
                except Exception:
                    dd = float("inf")
                out.append(dd if dd >= 0 else float("inf"))
        return out

    # distances_by_code: dict code->distance_to_goal
    dbc = cogmap_result.get("distances_by_code")
    if isinstance(dbc, dict) and len(dbc) > 0:
        out = [float("inf")] * n
        for code_str, d in dbc.items():
            try:
                code = int(code_str)
            except Exception:
                continue
            if not (1 <= code <= n):
                continue
            try:
                dd = float(d)
            except Exception:
                dd = float("inf")
            out[code - 1] = dd if dd >= 0 else float("inf")
        return out

    return None


@dataclass(frozen=True)
class _AStarResult:
    path: List[int]  # 0-indexed node indices, inclusive of start and goal
    cost: int


def astar_path(
    start_idx: int,
    goal_idx: int,
    neighbors: Sequence[Sequence[int]],
    h: Optional[Sequence[float]] = None,
) -> Optional[_AStarResult]:
    """
    A* shortest path on an unweighted graph (edge cost=1).
    Returns path as a list of node indices (0-indexed), or None if unreachable.
    """
    if start_idx == goal_idx:
        return _AStarResult(path=[start_idx], cost=0)

    n = len(neighbors)
    if not (0 <= start_idx < n and 0 <= goal_idx < n):
        return None

    def heuristic(i: int) -> float:
        if h is None:
            return 0.0
        try:
            return float(h[i])
        except Exception:
            return 0.0

    # g_score and came_from
    g = [float("inf")] * n
    g[start_idx] = 0.0
    came_from: Dict[int, int] = {}

    # (f, tie_breaker, node)
    # tie_breaker uses g to prefer deeper nodes when f is equal, to reduce expansions a bit.
    open_heap: List[Tuple[float, float, int]] = []
    heappush(open_heap, (heuristic(start_idx), 0.0, start_idx))

    in_open = [False] * n
    in_open[start_idx] = True

    closed = [False] * n

    while open_heap:
        f_cur, _tie, cur = heappop(open_heap)
        if closed[cur]:
            continue
        closed[cur] = True
        in_open[cur] = False

        if cur == goal_idx:
            # reconstruct
            path = [cur]
            while cur in came_from:
                cur = came_from[cur]
                path.append(cur)
            path.reverse()
            return _AStarResult(path=path, cost=int(g[goal_idx]))

        g_cur = g[cur]
        # Standard A* relaxation
        for nb in neighbors[cur]:
            if closed[nb]:
                continue
            tentative = g_cur + 1.0
            if tentative < g[nb]:
                came_from[nb] = cur
                g[nb] = tentative
                f_nb = tentative + heuristic(nb)
                heappush(open_heap, (f_nb, tentative, nb))
                in_open[nb] = True

    return None


def build_astar_next_dict(cogmap_result: Dict) -> Dict[int, int]:
    """
    Build a deterministic next-step policy based on A* shortest paths to the target.

    Returns:
        dict: state_code (1..N) -> recommended_next_code (1..N)
    """
    n = int(cogmap_result.get("N") or 0)
    target_code = cogmap_result.get("target_code") or cogmap_result.get("target")
    if n <= 0 or not target_code:
        return {}
    try:
        goal_code = int(target_code)
    except Exception:
        return {}
    if not (1 <= goal_code <= n):
        return {}

    adj = cogmap_result.get("adj")
    if adj is None:
        return {}
    neighbors = build_graph_from_adj(adj)
    goal_idx = goal_code - 1

    # Default heuristic: precomputed graph distances to goal if available
    h = _heuristic_from_cogmap(cogmap_result, goal_idx=goal_idx)

    out: Dict[int, int] = {}
    for s_code in range(1, n + 1):
        if s_code == goal_code:
            continue
        start_idx = s_code - 1
        res = astar_path(start_idx=start_idx, goal_idx=goal_idx, neighbors=neighbors, h=h)
        if not res or len(res.path) < 2:
            continue
        next_idx = res.path[1]
        out[s_code] = next_idx + 1
    return out

