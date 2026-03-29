"""
从轨迹/序列中提取频繁子序列。
序列元素为 (s, a) 或 (s, s_next)，输出 n-gram 计数或满足最小支持度的子序列。
"""
from collections import Counter
from typing import List, Tuple, Union, Dict, Any


def _seq_to_tuple(seq: List) -> Tuple:
    """可哈希的序列表示。"""
    return tuple(tuple(x) if isinstance(x, (list, tuple)) else x for x in seq)


def extract_ngrams(
    sequences: List[List[Union[int, Tuple[int, int], Dict[str, Any]]]],
    n: int,
    min_count: int = 1,
) -> List[Tuple[Tuple, int]]:
    """
    从多段序列中统计固定长度 n 的 n-gram 出现次数。
    sequences: 每段为 list of 状态或 (s,a) 或 (s,s_next)；若为 dict 则取 's' 与 's_next' 或 'a'。
    返回 [(ngram_tuple, count), ...]，按 count 降序，且 count >= min_count。
    """
    def item_to_key(x):
        if isinstance(x, dict):
            return (x.get("s"), x.get("s_next", x.get("a")))
        if isinstance(x, (list, tuple)) and len(x) >= 2:
            return (x[0], x[1])
        return x

    counter: Counter = Counter()
    for seq in sequences:
        if len(seq) < n:
            continue
        for i in range(len(seq) - n + 1):
            window = seq[i : i + n]
            key = tuple(item_to_key(w) for w in window)
            counter[key] += 1
    out = [(k, c) for k, c in counter.most_common() if c >= min_count]
    return out


def extract_frequent_sequences(
    sequences: List[List[Union[int, Tuple[int, int], Dict[str, Any]]]],
    min_support: int = 2,
    max_length: int = 10,
    min_length: int = 2,
) -> List[Tuple[Tuple, int]]:
    """
    简单频繁子序列：枚举长度在 [min_length, max_length] 的连续子序列，统计出现次数，保留 >= min_support 的。
    返回 [(subseq_tuple, support), ...]，按 support 降序。
    """
    def item_to_key(x):
        if isinstance(x, dict):
            return (x.get("s"), x.get("s_next", x.get("a")))
        if isinstance(x, (list, tuple)) and len(x) >= 2:
            return (x[0], x[1])
        return x

    counter: Counter = Counter()
    for seq in sequences:
        for length in range(min_length, min(max_length + 1, len(seq) + 1)):
            for i in range(len(seq) - length + 1):
                window = seq[i : i + length]
                key = tuple(item_to_key(w) for w in window)
                counter[key] += 1
    out = [(k, c) for k, c in counter.most_common() if c >= min_support]
    return out
