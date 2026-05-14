"""
将频繁子序列整理为宏目录：宏 ID、状态/动作序列、支持度、起止状态等。
"""
from typing import List, Tuple, Any, Dict


def build_macro_catalog(
    frequent_pairs: List[Tuple[Tuple, int]],
    min_support: int = 2,
) -> List[Dict[str, Any]]:
    """
    frequent_pairs: [(subseq_tuple, support), ...]，来自 extract_ngrams 或 extract_frequent_sequences。
    返回宏列表，每项为 {"macro_id": i, "sequence": [...], "support": k, "start_state": s, "end_state": s'}。
    若序列元素为 (s, s_next)，则 start_state 取首元素 s，end_state 取末元素 s_next（或末元素若为单值）。
    """
    catalog = []
    for i, (seq_tuple, support) in enumerate(frequent_pairs):
        if support < min_support:
            continue
        sequence = list(seq_tuple)
        start_state = None
        end_state = None
        if sequence:
            first = sequence[0]
            last = sequence[-1]
            if isinstance(first, (list, tuple)) and len(first) >= 1:
                start_state = first[0]
            else:
                start_state = first
            if isinstance(last, (list, tuple)) and len(last) >= 2:
                end_state = last[1]
            elif isinstance(last, (list, tuple)) and len(last) == 1:
                end_state = last[0]
            else:
                end_state = last
        catalog.append({
            "macro_id": i,
            "sequence": sequence,
            "support": support,
            "start_state": start_state,
            "end_state": end_state,
        })
    return catalog
