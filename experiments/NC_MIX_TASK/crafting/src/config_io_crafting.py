"""
Crafting trial 列表读取（每 trial 单一起始石块 + 订单目标）。
兼容 JSON 里 `raws` 数组：若多项则只取第一项作为起始态。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .stone_space import default_raw_pool, is_valid_state_id, unique_preserve_order


def nav_code_to_stone(n: int) -> str:
    return f"stone_{int(n):02d}"


@dataclass
class TrialSpec:
    trial_id: str
    order_count: int
    seed: Optional[int]
    raws: List[str]
    targets: Optional[List[str]]
    strict_order_targets: bool = False
    min_distance: int = 2
    schedule_meta: Optional[Dict[str, Any]] = field(default=None)


@dataclass
class TrialListData:
    trials: List[TrialSpec]
    source_path: str
    """crafting_trial_list | nav_sequence（与 Navigation6 assets/trial_sequences 同源）"""
    format_label: str = "crafting_trial_list"


def _default_trial_path() -> str:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(here, "data", "trials", "trial_list_v1.json")


def _parse_crafting_trial_list_payload(data: Dict[str, Any], p: str) -> TrialListData:
    schema = data.get("schema")
    if schema != "crafting_trial_list":
        raise ValueError(f"trial 列表 schema 不匹配（期望 crafting_trial_list）: {p}")

    trials: List[TrialSpec] = []
    for i, row in enumerate(data.get("trials", [])):
        if not isinstance(row, dict):
            continue

        trial_id = str(row.get("trial_id") or f"trial_{i + 1:03d}")
        order_count = int(row.get("order_count", 20))
        seed_val = row.get("seed")
        seed = int(seed_val) if seed_val is not None else None

        raws_raw = row.get("raws")
        start_state_id = row.get("start_state_id")

        raws: List[str] = []
        if isinstance(raws_raw, list):
            raws = [str(x) for x in raws_raw if is_valid_state_id(str(x))]
            raws = unique_preserve_order(raws)
        elif start_state_id is not None and is_valid_state_id(str(start_state_id)):
            raws = [str(start_state_id)]

        if not raws:
            raws = [default_raw_pool()[0]]

        if len(raws) > 1:
            raws = [raws[0]]

        targets_raw = row.get("targets")
        targets: Optional[List[str]] = None
        if isinstance(targets_raw, list):
            valid_targets = [str(x) for x in targets_raw if is_valid_state_id(str(x))]
            targets = unique_preserve_order(valid_targets)

        strict_ot = bool(row.get("strict_order_targets", False))
        min_dist = int(row.get("min_distance", 2))
        sm = row.get("schedule_meta")
        schedule_meta: Optional[Dict[str, Any]] = None
        if isinstance(sm, dict):
            schedule_meta = dict(sm)

        trials.append(
            TrialSpec(
                trial_id=trial_id,
                order_count=max(1, order_count),
                seed=seed,
                raws=raws,
                targets=targets,
                strict_order_targets=strict_ot,
                min_distance=max(1, min_dist),
                schedule_meta=schedule_meta,
            )
        )

    if not trials:
        trials = [
            TrialSpec(
                trial_id="trial_001",
                order_count=20,
                seed=None,
                raws=[default_raw_pool()[0]],
                targets=None,
                strict_order_targets=False,
                min_distance=2,
                schedule_meta=None,
            )
        ]

    return TrialListData(trials=trials, source_path=p, format_label="crafting_trial_list")


def load_trial_list(path: Optional[str]) -> TrialListData:
    p = path or _default_trial_path()
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    return _parse_crafting_trial_list_payload(data, p)


def _parse_nav_sequence_pairs(data: Dict[str, Any]) -> List[Tuple[int, int]]:
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
                f"试次表第 {i + 1} 条缺少 start/goal 或 targetA/targetB 字段"
            )
    if not out:
        raise ValueError("Navigation6 风格试次表为空或无法解析 trials")
    return out


def _trial_list_from_nav_sequence_data(data: Dict[str, Any], path: str) -> TrialListData:
    """由已解析的 JSON 对象构建 TrialListData（Navigation6 trial_sequences 结构）。"""
    pairs = _parse_nav_sequence_pairs(data)
    specs: List[TrialSpec] = []
    rows = data.get("trials") or []
    for i, (a, b) in enumerate(pairs):
        if a == b:
            raise ValueError(f"试次 {i + 1} 起点与目标编码相同 ({a})")
        if not (1 <= a <= 9 and 1 <= b <= 9):
            raise ValueError(
                f"试次 {i + 1} 编码 ({a},{b}) 超出九石阵范围 1–9；请检查试次表"
            )
        tid_raw = None
        if i < len(rows) and isinstance(rows[i], dict) and rows[i].get("trial_id") is not None:
            tid_raw = rows[i].get("trial_id")
        tid = f"nav_{tid_raw}" if tid_raw is not None else f"nav_trial_{i + 1:03d}"
        stone_a = nav_code_to_stone(a)
        stone_b = nav_code_to_stone(b)
        specs.append(
            TrialSpec(
                trial_id=tid,
                order_count=1,
                seed=None,
                raws=[stone_a],
                targets=[stone_b],
                strict_order_targets=True,
                min_distance=1,
                schedule_meta={
                    "nav_start": a,
                    "nav_goal": b,
                    "source": "nav_sequence",
                },
            )
        )
    return TrialListData(trials=specs, source_path=os.path.abspath(path), format_label="nav_sequence")


def trial_list_from_nav_sequence_file(path: str) -> TrialListData:
    """
    读取与 Navigation6 ``assets/trial_sequences/*.json`` 相同结构的文件；
    每条 trial → 单订单 TrialSpec（站点编码 1–9 对应 stone_01–09），与 main2 / Proposal-5 单路段语义一致。
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return _trial_list_from_nav_sequence_data(data, path)


def load_trial_list_auto(path: str) -> TrialListData:
    """根据 JSON 内容自动选择 crafting_trial_list 或 Navigation6 trial_sequences 解析。"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    ap = os.path.abspath(path)
    if data.get("schema") == "crafting_trial_list":
        return _parse_crafting_trial_list_payload(data, ap)
    trials_raw = data.get("trials")
    if isinstance(trials_raw, list) and trials_raw:
        first = trials_raw[0]
        if isinstance(first, dict) and (
            ("start" in first and "goal" in first)
            or ("targetA" in first and "targetB" in first)
        ):
            return _trial_list_from_nav_sequence_data(data, ap)
    raise ValueError(
        f"无法识别试次表格式（需 crafting_trial_list 或含 targetA/targetB 的 trials）: {ap}"
    )


def trial_list_from_specs(trials: List[TrialSpec], source_path: str = "<memory>") -> TrialListData:
    """构造内存中的 TrialListData（Proposal-5 runner 等）。"""
    return TrialListData(trials=list(trials), source_path=source_path, format_label="crafting_trial_list")
