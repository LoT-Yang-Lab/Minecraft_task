"""
检验宏使用强度与认知地图上相关状态对距离的关联。
例如：常用宏 (A,B,C) 的被试，其 A–C 的（操作化）距离是否更短。
"""
from typing import List, Dict, Any, Optional
import numpy as np


def macro_distance_correlation(
    macro_usage: List[Dict[str, Any]],
    macro_catalog: List[Dict[str, Any]],
    distance_matrix: np.ndarray,
    catalog_by_id: Optional[Dict[int, Dict]] = None,
) -> List[Dict[str, Any]]:
    """
    macro_usage: compute_macro_usage 的输出，含 participant_id, map_id, macro_id, usage_count。
    macro_catalog: build_macro_catalog 的输出，含 macro_id, start_state, end_state。
    distance_matrix: N×N，下标 0..N-1 对应状态 1..N，即 dist[i-1,j-1] 为状态 i 到 j 的步数。
    返回每个宏的汇总：macro_id, start_state, end_state, 使用该宏的被试数, 平均 usage_count,
    以及这些被试的 start_state–end_state 在图上的平均距离（若可算）。
    """
    if catalog_by_id is None:
        catalog_by_id = {m["macro_id"]: m for m in macro_catalog}
    N = distance_matrix.shape[0]
    results = []
    for macro in macro_catalog:
        mid = macro.get("macro_id", -1)
        start = macro.get("start_state")
        end = macro.get("end_state")
        rows = [r for r in macro_usage if r.get("macro_id") == mid]
        if not rows:
            results.append({
                "macro_id": mid,
                "start_state": start,
                "end_state": end,
                "n_participants": 0,
                "mean_usage": 0.0,
                "mean_graph_distance": None,
            })
            continue
        n = len(rows)
        mean_usage = float(np.mean([r.get("usage_count", 0) for r in rows]))
        # 图上 start -> end 的距离（状态 1-indexed -> 下标 0-indexed）
        mean_dist = None
        if start is not None and end is not None and 1 <= start <= N and 1 <= end <= N:
            d = distance_matrix[start - 1, end - 1]
            mean_dist = float(d) if d >= 0 else None
        results.append({
            "macro_id": mid,
            "start_state": start,
            "end_state": end,
            "n_participants": n,
            "mean_usage": mean_usage,
            "mean_graph_distance": mean_dist,
        })
    return results
