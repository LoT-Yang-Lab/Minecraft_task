"""
对每被试/每地图的轨迹，统计各宏出现次数或比例（宏使用强度）。
"""
from typing import List, Dict, Any, Tuple


def _seq_match(seq: List, pattern: Tuple, item_to_key) -> bool:
    """轨迹片段 seq 是否与 pattern 匹配（连续子序列）。"""
    if len(seq) < len(pattern):
        return False
    for i in range(len(seq) - len(pattern) + 1):
        if tuple(item_to_key(seq[i + j]) for j in range(len(pattern))) == pattern:
            return True
    return False


def compute_macro_usage(
    trajectory_rows: List[Dict[str, Any]],
    macro_catalog: List[Dict[str, Any]],
    participant_key: str = "participant_id",
    map_key: str = "map_id",
    sequence_key: str = "sequence",
) -> List[Dict[str, Any]]:
    """
    对 trajectory_rows 按 (participant_id, map_id) 分组，每段转为 (s, s_next) 序列，
    统计每个宏在该段中出现的次数；输出每 (participant_id, map_id, macro_id) 的使用次数。
    trajectory_rows: 含 participant_id, map_id, s, s_next（或 a）；按 episode/step 排序后形成序列。
    macro_catalog: build_macro_catalog 的输出，每项含 "sequence"（tuple 的 list）。
    返回 [{"participant_id", "map_id", "macro_id", "usage_count", "macro_support"}, ...]。
    """
    def row_to_pair(r):
        s = r.get("s", r.get("current_code", 0))
        s_next = r.get("s_next", r.get("participant_choice", 0))
        return (s, s_next)

    # 按 (participant_id, map_id) 分组，每组内按 step 排序得到一段序列
    from collections import defaultdict
    groups: Dict[Tuple[str, str], List[Dict]] = defaultdict(list)
    for r in trajectory_rows:
        pid = r.get(participant_key, "")
        mid = r.get(map_key, "")
        groups[(pid, mid)].append(r)
    for k in groups:
        groups[k].sort(key=lambda x: (x.get("episode", 0), x.get("step", 0)))

    out = []
    for (pid, mid), rows in groups.items():
        seq = [row_to_pair(r) for r in rows]
        for macro in macro_catalog:
            pattern = tuple(tuple(x) if isinstance(x, (list, tuple)) else x for x in macro[sequence_key])
            count = 0
            if len(seq) >= len(pattern):
                for i in range(len(seq) - len(pattern) + 1):
                    if tuple(seq[i + j] for j in range(len(pattern))) == pattern:
                        count += 1
            out.append({
                "participant_id": pid,
                "map_id": mid,
                "macro_id": macro.get("macro_id", -1),
                "usage_count": count,
                "macro_support": macro.get("support", 0),
            })
    return out
