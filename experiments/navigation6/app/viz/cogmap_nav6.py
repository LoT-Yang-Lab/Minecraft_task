"""
Navigation6 认知地图：从地图构建状态图（邻接矩阵）、图拉普拉斯与谱结构，
并可选计算各节点到目标的图最短距离。供后续策略提取与参数拟合使用。

不依赖参考代码 cogmap 包，仅用 NumPy 实现谱计算。
"""
from __future__ import annotations

import os
from collections import deque
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

# analysis/可视化用：避免在只计算认知地图时写出 rl_data
class _NullRecorder:
    def __init__(self):
        self.memory_buffer = []
        self.episode_count = 0
        self.step_count = 0

    def start_episode(self):
        self.episode_count += 1
        self.step_count = 0

    def log_action(self, *args, **kwargs):
        self.step_count += 1

    def save_to_file(self):
        return

# 延迟导入，避免顶层导入 pygame 等
def _get_game_and_encoding(map_path: str):
    """从地图路径创建 GameNavigation6 并返回 (game, cell_to_code, code_to_cell, target_code)。"""
    from experiments.navigation6.app.experiment.game import GameNavigation6

    resolved = _resolve_map_path(map_path)
    recorder = _NullRecorder()
    game = GameNavigation6(
        recorder,
        map_type="Barbell",
        custom_map_file=resolved,
        enable_experiment=False,
    )
    cell_to_code, code_to_cell, target_code = _build_position_encoding(game)
    return game, cell_to_code, code_to_cell, target_code


def _resolve_map_path(filename: str) -> str:
    """将地图文件名解析为绝对路径；若已是绝对路径则返回原样。"""
    if os.path.isabs(filename) and os.path.exists(filename):
        return filename
    from experiments.navigation6.app.paths import maps_dir
    return os.path.abspath(os.path.join(maps_dir(), filename))


def _build_position_encoding(game) -> Tuple[Dict[Tuple[int, int], int], Dict[int, Tuple[int, int]], int]:
    """与 main.build_position_encoding 一致：单格 ∪ 站点 ∪ 房间格。"""
    walkable: List[Tuple[int, int]] = []
    single_cells = getattr(game, "single_cells", set()) or set()
    obstacle_map = getattr(game, "obstacle_map", {}) or {}
    for c in single_cells:
        if c not in obstacle_map:
            walkable.append(c)
    for pos in game._all_station_positions():
        if pos not in obstacle_map and pos not in walkable:
            walkable.append(pos)
    for rid, room in getattr(game, "rooms", {}).items():
        lx, ly = room.logical_pos
        for dy in range(3):
            for dx in range(3):
                gx, gy = lx * 3 + dx, ly * 3 + dy
                if game._is_walkable(gx, gy) and (gx, gy) not in walkable:
                    walkable.append((gx, gy))
    walkable = sorted(set(walkable), key=lambda c: (c[0], c[1]))
    cell_to_code = {c: i + 1 for i, c in enumerate(walkable)}
    code_to_cell = {i + 1: c for i, c in enumerate(walkable)}
    target_pos = getattr(game, "original_target_pos", None)
    target_code = cell_to_code[target_pos] if target_pos and target_pos in cell_to_code else 0
    return cell_to_code, code_to_cell, target_code


def _neighbor_cells_from_game(game, px: int, py: int, cell_to_code: Dict[Tuple[int, int], int]) -> Set[int]:
    """Navigation6：公交/轻轨双向 + 地铁单向（下一站）转移。"""
    codes: Set[int] = set()
    for _line_idx, pos in game.get_instant_subway_next_stations(px, py):
        if pos in cell_to_code:
            codes.add(cell_to_code[pos])
    for _line_idx, pos in game.get_instant_subway_prev_stations(px, py):
        if pos in cell_to_code:
            codes.add(cell_to_code[pos])
    return codes


def _build_adjacency(
    game,
    cell_to_code: Dict[Tuple[int, int], int],
    code_to_cell: Dict[int, Tuple[int, int]],
) -> np.ndarray:
    """构建 N×N 对称邻接矩阵（0/1），下标 0..N-1 对应编码 1..N。"""
    N = len(cell_to_code)
    adj = np.zeros((N, N), dtype=np.int8)
    for cell, code_i in cell_to_code.items():
        idx_i = code_i - 1
        neighbors = _neighbor_cells_from_game(game, cell[0], cell[1], cell_to_code)
        for code_j in neighbors:
            idx_j = code_j - 1
            adj[idx_i, idx_j] = 1
            adj[idx_j, idx_i] = 1
    return adj


def _compute_spectral(adj: np.ndarray) -> Dict[str, np.ndarray]:
    """
    图拉普拉斯 L = D - A，特征分解；特征值从小到大，特征向量按列。
    与参考 cogmap.spectral 一致；将绝对值 < 1e-10 的特征值置为 0。
    """
    N = adj.shape[0]
    if N == 0:
        return {"laplacian": adj, "eigenvalues": np.array([], dtype=float), "eigenvectors": np.zeros((0, 0))}
    A = adj.astype(np.float64)
    D = np.diag(A.sum(axis=1))
    L = D - A
    eigenvalues, eigenvectors = np.linalg.eigh(L)
    eigenvalues[np.abs(eigenvalues) < 1e-10] = 0.0
    return {"laplacian": L, "eigenvalues": eigenvalues, "eigenvectors": eigenvectors}


def _shortest_path_distances(adj: np.ndarray, target_idx: int, N: int) -> Tuple[np.ndarray, Dict[int, int]]:
    """
    从目标节点 target_idx（0-based）出发 BFS，得到每个节点到目标的步数。
    不可达记为 -1。返回 (distance_vector 长度 N, distances_by_code 键为 1..N)。
    """
    distance_vector = np.full(N, -1, dtype=np.int32)
    if target_idx < 0 or target_idx >= N:
        distances_by_code = {i + 1: -1 for i in range(N)}
        return distance_vector, distances_by_code
    distance_vector[target_idx] = 0
    q = deque([target_idx])
    while q:
        u = q.popleft()
        for v in range(N):
            if adj[u, v] and distance_vector[v] == -1:
                distance_vector[v] = distance_vector[u] + 1
                q.append(v)
    distances_by_code = {i + 1: int(distance_vector[i]) for i in range(N)}
    return distance_vector, distances_by_code


def compute_nav6_cogmap(
    map_path: Optional[str] = None,
    game: Optional[Any] = None,
    include_distances: bool = True,
) -> Dict[str, Any]:
    """
    主入口：计算单张 Navigation6 地图的状态图与谱结构。

    参数
    -----
    map_path : str 或 None
        地图 JSON 路径（相对 experiments/navigation6/maps/ 或绝对路径）。
        与 game 二选一。
    game : GameNavigation6 或 None
        已加载的 GameNavigation6 实例；若提供则忽略 map_path。
    include_distances : bool
        是否计算各节点到目标的图最短距离；不可达为 -1。

    返回
    -----
    dict 包含：
      - N, adj, labels, target_code
      - laplacian, eigenvalues, eigenvectors, components（零特征值个数）
      - distance_vector（长度 N）、distances_by_code（code -> 步数），仅当 include_distances 且 target_code 有效时非 None。
    """
    if game is not None:
        cell_to_code, code_to_cell, target_code = _build_position_encoding(game)
    elif map_path:
        game, cell_to_code, code_to_cell, target_code = _get_game_and_encoding(map_path)
    else:
        raise ValueError("必须提供 map_path 或 game 之一")

    N = len(cell_to_code)
    if N == 0:
        return {
            "N": 0,
            "adj": np.zeros((0, 0)),
            "labels": [],
            "target_code": target_code if target_code else None,
            "laplacian": np.zeros((0, 0)),
            "eigenvalues": np.array([]),
            "eigenvectors": np.zeros((0, 0)),
            "components": 0,
            "distance_vector": None,
            "distances_by_code": None,
        }

    adj = _build_adjacency(game, cell_to_code, code_to_cell)
    labels = [f"({code_to_cell[i + 1][0]},{code_to_cell[i + 1][1]})" for i in range(N)]
    spec = _compute_spectral(adj)
    eigenvalues = spec["eigenvalues"]
    components = int((eigenvalues < 1e-6).sum())

    distance_vector = None
    distances_by_code = None
    if include_distances and target_code and target_code >= 1:
        target_idx = target_code - 1
        distance_vector, distances_by_code = _shortest_path_distances(adj, target_idx, N)

    return {
        "N": N,
        "adj": adj,
        "labels": labels,
        "target_code": target_code if target_code else None,
        "laplacian": spec["laplacian"],
        "eigenvalues": eigenvalues,
        "eigenvectors": spec["eigenvectors"],
        "components": components,
        "distance_vector": distance_vector,
        "distances_by_code": distances_by_code,
    }


def render_and_save_cogmap(
    cogmap_result: Dict[str, Any],
    output_dir: str,
    basename: str = "cogmap",
) -> List[str]:
    """
    根据 compute_nav6_cogmap 的返回结果生成三张 SVG 并写入指定目录。
    目标节点（若有 target_code）在谱嵌入图中高亮。仅在调用时导入 matplotlib。

    Returns
    -------
    写入的 SVG 文件绝对路径列表。
    """
    from experiments.navigation6.app.viz.cogmap_plot_nav6 import (
        render_all_plots,
        save_plots_to_dir,
    )
    adj = cogmap_result["adj"]
    labels = cogmap_result["labels"]
    eigenvalues = cogmap_result["eigenvalues"]
    eigenvectors = cogmap_result["eigenvectors"]
    target_code = cogmap_result.get("target_code")
    highlight_nodes = [target_code - 1] if target_code and target_code >= 1 else None
    meta = {
        "n": cogmap_result["N"],
        "components": cogmap_result["components"],
        "target_code": target_code,
        "map_name": basename,
    }
    svg_dict = render_all_plots(
        adj, labels, eigenvalues, eigenvectors,
        highlight_nodes=highlight_nodes,
        meta=meta,
    )
    return save_plots_to_dir(svg_dict, output_dir, basename=basename)


if __name__ == "__main__":
    import argparse
    import sys
    from pathlib import Path

    # 允许从项目根运行：python experiments/navigation6/src/cogmap_nav6.py ...
    _this_file = Path(__file__).resolve()
    _project_root = _this_file.parents[3]
    _project_root_str = str(_project_root)
    if _project_root_str not in sys.path:
        sys.path.insert(0, _project_root_str)

    # 统一把生成物放在 experiments/navigation6/outputs/ 下（仍可用 -o 覆盖）
    default_output = os.path.join(_project_root_str, "experiments", "navigation6", "outputs", "cogmap")
    parser = argparse.ArgumentParser(description="Navigation6 认知地图：状态图与谱结构")
    parser.add_argument("map_file", nargs="?", default="map_1774095558.json",
                        help="地图 JSON 文件名（相对 maps/）或路径，默认 map_1774095558.json")
    parser.add_argument("-s", "--save-plots", action="store_true", help="保存三张 SVG 到输出目录")
    parser.add_argument("-o", "--output-dir", default=default_output,
                        help=f"SVG 保存目录，默认 {default_output}")
    args = parser.parse_args()

    out = compute_nav6_cogmap(map_path=args.map_file, include_distances=True)
    print("N:", out["N"])
    print("components:", out["components"])
    print("eigenvalues (first 10):", out["eigenvalues"][: min(10, out["N"])].tolist())
    print("target_code:", out["target_code"])
    if out.get("distances_by_code"):
        print("distances_by_code:", out["distances_by_code"])

    if args.save_plots:
        basename = os.path.splitext(os.path.basename(args.map_file))[0]
        paths = render_and_save_cogmap(out, args.output_dir, basename=basename)
        print("Saved SVG:", paths)
