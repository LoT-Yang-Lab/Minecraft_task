"""
将「认知地图距离」操作化：图最短路径步数、或从选择数据估计的状态间倾向。
"""
from typing import Dict, Any, List
import numpy as np


def graph_distance_matrix(cogmap_result: Dict[str, Any]) -> np.ndarray:
    """
    从 cogmap 的邻接矩阵计算任意两状态间最短路径步数（Floyd-Warshall）。
    返回 N×N 矩阵，d[i,j] 为状态 i 到 j 的步数；不可达为 -1 或 inf。
    状态下标 0..N-1 对应位置编码 1..N。
    """
    adj = np.asarray(cogmap_result["adj"], dtype=np.float64)
    N = adj.shape[0]
    d = np.where(adj > 0, 1.0, np.inf)
    np.fill_diagonal(d, 0.0)
    for k in range(N):
        d = np.minimum(d, d[:, k : k + 1] + d[k : k + 1, :])
    d[np.isinf(d)] = -1.0
    return d


def choice_based_proximity(
    practice_records: List[Dict[str, Any]],
    state_key: str = "current_code",
    choice_key: str = "participant_choice",
    N: int = 0,
) -> np.ndarray:
    """
    从练习数据估计「从状态 i 选到状态 j」的频次，作为 (i,j) 的接近度代理。
    返回 N×N 矩阵，prox[i,j] = 在状态 i 时选择 j 的次数（或比例）；未出现为 0。
    状态 1-indexed；若 N==0 则从记录中推断最大 code。
    """
    if not practice_records:
        return np.zeros((max(N, 1), max(N, 1)))
    if N <= 0:
        codes = set()
        for r in practice_records:
            codes.add(r.get(state_key, 0))
            codes.add(r.get(choice_key, 0))
        N = max(codes) if codes else 1
    prox = np.zeros((N + 1, N + 1))
    for r in practice_records:
        s = r.get(state_key, 0)
        c = r.get(choice_key, 0)
        if 0 < s <= N and 0 < c <= N:
            prox[s, c] += 1.0
    return prox
