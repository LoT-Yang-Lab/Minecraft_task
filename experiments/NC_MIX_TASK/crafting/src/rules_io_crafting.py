"""
Crafting 规则 JSON：map_id + 可选 transition_map_path（显式三药水表）；无路径时使用内置图生成表。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from .graph_moves import potion_backward_from_forward
from .maps_crafting import MAPS, built_in_potion_tables
from .transition_map_io_crafting import load_transition_map


def _potion12_reverse_from_forward(
    p1: Dict[str, str], p2: Dict[str, str], context: str
) -> Tuple[Dict[str, str], Dict[str, str]]:
    """JSON 中 potion1/2 为 Q/A 正向一步；由此推导 E/D 逆向表。目标石不可被多个源指向。"""
    try:
        r1 = potion_backward_from_forward(p1)
        r2 = potion_backward_from_forward(p2)
    except ValueError as e:
        raise ValueError(f"{context}: {e}") from e
    return r1, r2


@dataclass
class RuleDataCrafting:
    map_id: str
    source_path: str
    potion1: Dict[str, str]
    potion1_rev: Dict[str, str]
    potion2: Dict[str, str]
    potion2_rev: Dict[str, str]
    potion3: Dict[str, str]
    transition_map_path: Optional[str] = None
    """已解析的转化表文件绝对路径；未使用外部文件时为 None。"""
    transition_map_source: Optional[str] = None


def _crafting_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _default_rule_path() -> str:
    return os.path.join(_crafting_root(), "data", "rules", "crafting_rules_v1.json")


def _resolve_transition_map_path(rules_file: str, rel: str) -> str:
    if os.path.isabs(rel):
        return rel
    root = _crafting_root()
    cand = os.path.normpath(os.path.join(root, rel))
    if os.path.isfile(cand):
        return cand
    cand2 = os.path.normpath(os.path.join(os.path.dirname(rules_file), rel))
    if os.path.isfile(cand2):
        return cand2
    raise FileNotFoundError(
        f"找不到转化地图文件: {rel}（已尝试 crafting 根与规则目录）"
    )


def load_rule_data(path: Optional[str] = None) -> RuleDataCrafting:
    p = path or _default_rule_path()
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    schema = data.get("schema")
    if schema != "crafting":
        raise ValueError(f"规则文件 schema 不匹配（期望 crafting）: {p}")
    mid = str(data.get("map_id", "map_a"))
    if mid not in MAPS:
        mid = "map_a"

    rel_tm = data.get("transition_map_path")
    if rel_tm:
        tm_abs = _resolve_transition_map_path(p, str(rel_tm))
        tm = load_transition_map(tm_abs)
        p1r, p2r = _potion12_reverse_from_forward(
            tm.potion1, tm.potion2, f"转化地图 {tm_abs}"
        )
        return RuleDataCrafting(
            map_id=mid,
            source_path=p,
            potion1=dict(tm.potion1),
            potion1_rev=p1r,
            potion2=dict(tm.potion2),
            potion2_rev=p2r,
            potion3=dict(tm.potion3),
            transition_map_path=tm_abs,
            transition_map_source=tm.source_path,
        )

    p1f, p1r, p2f, p2r, p3 = built_in_potion_tables(mid)
    return RuleDataCrafting(
        map_id=mid,
        source_path=p,
        potion1=p1f,
        potion1_rev=p1r,
        potion2=p2f,
        potion2_rev=p2r,
        potion3=p3,
        transition_map_path=None,
        transition_map_source=None,
    )


def load_rule_data_with_transition_map(
    rules_path: Optional[str],
    transition_map_abs: str,
) -> RuleDataCrafting:
    """
    读取规则 JSON（map_id 等元数据），三药水表与路径以用户选定的转化地图为准。
    """
    p = rules_path or _default_rule_path()
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("schema") != "crafting":
        raise ValueError(f"规则文件 schema 不匹配（期望 crafting）: {p}")

    tm = load_transition_map(transition_map_abs)
    mid = str(tm.map_id) if tm.map_id else str(data.get("map_id", "map_a"))
    tm_abs = os.path.abspath(transition_map_abs)
    p1r, p2r = _potion12_reverse_from_forward(
        tm.potion1, tm.potion2, f"转化地图 {tm_abs}"
    )

    return RuleDataCrafting(
        map_id=mid,
        source_path=p,
        potion1=dict(tm.potion1),
        potion1_rev=p1r,
        potion2=dict(tm.potion2),
        potion2_rev=p2r,
        potion3=dict(tm.potion3),
        transition_map_path=tm_abs,
        transition_map_source=tm.source_path,
    )
