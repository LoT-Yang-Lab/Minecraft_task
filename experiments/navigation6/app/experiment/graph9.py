"""
Navigation6 新版图结构：9 节点（3×3 网格 + 四角单向环线）。

节点编号 1-9，布局：
  1  2  3
  4  5  6
  7  8  9

连接规则：
- 网格连接（双向）：公交(前/后) 控制行移动，地铁(前/后) 控制列移动
- 环线连接（单向）：1→3→9→7→1（四个角节点顺时针环）

3 种交通工具（5 种动作）：
  公交(前)(Q) / 公交(后)(E)  ─ 行方向移动
  地铁(前)(A) / 地铁(后)(D)  ─ 列方向移动
  环线(W)                    ─ 四角单向环
"""
from __future__ import annotations

import random
from collections import deque
from itertools import permutations
from typing import Dict, List, Optional, Set, Tuple

# ── 节点布局 ──────────────────────────────────────────────
# 3×3 网格，行优先编号 1-9
#   1  2  3
#   4  5  6
#   7  8  9
NODE_IDS = list(range(1, 10))

# (row, col) 从 0 开始
_node_pos: Dict[int, Tuple[int, int]] = {
    1: (0, 0), 2: (0, 1), 3: (0, 2),
    4: (1, 0), 5: (1, 1), 6: (1, 2),
    7: (2, 0), 8: (2, 1), 9: (2, 2),
}

# ── 动作定义 ──────────────────────────────────────────────
ACTION_NAMES = ["公交(前)", "公交(后)", "地铁(前)", "地铁(后)", "环线"]
ACTION_KEYS = {
    "公交(前)": "Q",
    "公交(后)": "E",
    "地铁(前)": "A",
    "地铁(后)": "D",
    "环线": "W",
}

# ── 邻接表 ──────────────────────────────────────────────
# 环线：1→3→9→7→1（顺时针单向）
RING_NEXT: Dict[int, int] = {1: 3, 3: 9, 9: 7, 7: 1}
RING_NODES: Set[int] = set(RING_NEXT.keys())


def _grid_neighbor(node: int, action: str) -> Optional[int]:
    """网格方向移动，返回目标节点或 None（越界）。"""
    r, c = _node_pos[node]
    if action == "公交(前)":
        r -= 1
    elif action == "公交(后)":
        r += 1
    elif action == "地铁(前)":
        c -= 1
    elif action == "地铁(后)":
        c += 1
    else:
        return None
    if 0 <= r <= 2 and 0 <= c <= 2:
        return r * 3 + c + 1
    return None


def get_next_node(node: int, action: str) -> Optional[int]:
    """
    从 node 执行 action，返回到达的节点；若该动作不可用返回 None。
    """
    if action == "环线":
        return RING_NEXT.get(node)  # 非角节点返回 None
    return _grid_neighbor(node, action)


def get_available_actions(node: int) -> List[str]:
    """返回在 node 处所有可执行的动作名列表。"""
    out: List[str] = []
    for act in ACTION_NAMES:
        if get_next_node(node, act) is not None:
            out.append(act)
    return out


# ── 全部有效 (node, action) 对 ────────────────────────────
def all_valid_edges() -> List[Tuple[int, int, str]]:
    """返回 (from_node, to_node, action) 的完整列表。"""
    edges: List[Tuple[int, int, str]] = []
    for n in NODE_IDS:
        for act in ACTION_NAMES:
            dest = get_next_node(n, act)
            if dest is not None:
                edges.append((n, dest, act))
    return edges


def total_valid_actions() -> int:
    """图中所有可执行动作的总数。"""
    return len(all_valid_edges())


# ── BFS 最短距离 ─────────────────────────────────────────
def bfs_distance(start: int, goal: int) -> int:
    """返回从 start 到 goal 的最短步数（BFS）。start==goal 返回 0。"""
    if start == goal:
        return 0
    visited: Set[int] = {start}
    queue: deque[Tuple[int, int]] = deque([(start, 0)])
    while queue:
        cur, dist = queue.popleft()
        for act in ACTION_NAMES:
            nxt = get_next_node(cur, act)
            if nxt is not None and nxt not in visited:
                if nxt == goal:
                    return dist + 1
                visited.add(nxt)
                queue.append((nxt, dist + 1))
    return 999  # 不可达（理论上不会发生）


def shortest_path(start: int, goal: int) -> List[int]:
    """返回从 start 到 goal 的最短路径节点列表（含首尾）。"""
    if start == goal:
        return [start]
    visited: Set[int] = {start}
    queue: deque[Tuple[int, List[int]]] = deque([(start, [start])])
    while queue:
        cur, path = queue.popleft()
        for act in ACTION_NAMES:
            nxt = get_next_node(cur, act)
            if nxt is not None and nxt not in visited:
                new_path = path + [nxt]
                if nxt == goal:
                    return new_path
                visited.add(nxt)
                queue.append((nxt, new_path))
    return [start]  # 不可达


# ── 网格曼哈顿距离（不考虑环路捷径） ─────────────────────
def grid_manhattan_distance(a: int, b: int) -> int:
    """3×3 网格上的曼哈顿距离（仅上下左右，不含环路）。"""
    ra, ca = _node_pos[a]
    rb, cb = _node_pos[b]
    return abs(ra - rb) + abs(ca - cb)


# ── 距离矩阵（BFS，含环路） ──────────────────────────────
def distance_matrix() -> Dict[Tuple[int, int], int]:
    """返回所有节点对之间的最短距离字典（BFS，含环路）。"""
    dm: Dict[Tuple[int, int], int] = {}
    for a in NODE_IDS:
        for b in NODE_IDS:
            dm[(a, b)] = bfs_distance(a, b)
    return dm


def grid_distance_matrix() -> Dict[Tuple[int, int], int]:
    """返回所有节点对之间的网格曼哈顿距离字典（不含环路）。"""
    dm: Dict[Tuple[int, int], int] = {}
    for a in NODE_IDS:
        for b in NODE_IDS:
            dm[(a, b)] = grid_manhattan_distance(a, b)
    return dm


# ── 生成测试试次序列 ──────────────────────────────────────
def generate_test_trials(min_distance: int = 3, max_attempts: int = 200000) -> List[Tuple[int, int]]:
    """
    生成 9 个 trial 的 (start, goal) 序列：
    - 每个节点恰好做一次起点、一次终点
    - 所有 start-goal 距离 >= min_distance
    返回 [(start, goal), ...] 长度 9。

    使用回溯法确保一定能找到解。
    """
    dm = distance_matrix()
    nodes = list(NODE_IDS)  # [1..9]

    # 回溯法：固定随机的 starts 排列，搜索合法的 goals 排列
    starts_list = list(nodes)
    random.shuffle(starts_list)

    used_goals: Set[int] = set()
    result: List[Tuple[int, int]] = []

    def backtrack(idx: int) -> bool:
        if idx == len(starts_list):
            return True
        s = starts_list[idx]
        candidates = [g for g in nodes if g not in used_goals and g != s and dm[(s, g)] >= min_distance]
        random.shuffle(candidates)
        for g in candidates:
            used_goals.add(g)
            result.append((s, g))
            if backtrack(idx + 1):
                return True
            result.pop()
            used_goals.discard(g)
        return False

    if backtrack(0):
        return result

    # 如果当前 starts 排列无解，多试几次不同的 starts 排列
    for _ in range(1000):
        random.shuffle(starts_list)
        used_goals.clear()
        result.clear()
        if backtrack(0):
            return result

    # 最终回退：降低距离要求
    return generate_test_trials(min_distance=min_distance - 1)
