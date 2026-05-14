"""从 assets/trial_sequences 下的 JSON 加载 main2 使用的 (起点编码, 目标编码) 试次列表。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Sequence, Set, Tuple

from app.paths import get_nav6_root, trial_sequences_dir


def resolve_trial_sequence_cli_path(arg: str) -> str:
    """
    --trials 参数：绝对路径、相对 navigation6 根、相对 assets/trial_sequences、或相对 cwd。
    """
    raw = Path(arg)
    if raw.is_file():
        return str(raw.resolve())
    root = Path(get_nav6_root())
    ts = Path(trial_sequences_dir())
    for cand in (ts / arg, root / arg, Path.cwd() / arg):
        if cand.is_file():
            return str(cand.resolve())
    raise FileNotFoundError(f"找不到试次表文件: {arg}")


def load_start_goal_pairs_from_sequence_json(path: str) -> List[Tuple[int, int]]:
    """
    读取试次表。每条 trial 支持：
    - ``start`` + ``goal``：单目标路段（与 proposal-5 注入一致）
    - ``targetA`` + ``targetB``：与生成脚本一致；main2 中作为 (起点, 目标) 使用
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    trials = data.get("trials") or []
    out: List[Tuple[int, int]] = []
    for i, rec in enumerate(trials):
        if not isinstance(rec, dict):
            continue
        if "start" in rec and "goal" in rec:
            out.append((int(rec["start"]), int(rec["goal"])))
        elif "targetA" in rec and "targetB" in rec:
            out.append((int(rec["targetA"]), int(rec["targetB"])))
        else:
            raise ValueError(
                f"试次表 {path} 中第 {i + 1} 条缺少 start/goal 或 targetA/targetB 字段"
            )
    if not out:
        raise ValueError(f"试次表为空或无法解析: {path}")
    return out


def validate_pairs_against_station_codes(
    pairs: Sequence[Tuple[int, int]],
    valid_codes: Set[int],
    *,
    path_hint: str = "",
) -> None:
    ctx = f" ({path_hint})" if path_hint else ""
    for i, (a, b) in enumerate(pairs):
        if a not in valid_codes or b not in valid_codes:
            raise ValueError(
                f"试次 {i + 1} 编码 ({a}, {b}) 不在当前地图站点编码集内{ctx}；"
                f"请使用与本图一致的 trial_sequences JSON。"
            )
        if a == b:
            raise ValueError(f"试次 {i + 1} 起点与目标相同 ({a}){ctx}")
