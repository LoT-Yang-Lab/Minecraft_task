"""
Crafting 转化地图 JSON：potion1/potion2 存 Q/A 的「正向」一步（源→目标）；E/D 由程序求逆向（目标石不可被多个源指向）。potion3 仍为 W 大环一步。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .stone_space import STONE_IDS, is_valid_state_id

SCHEMA_TRANSITION = "crafting_transition_map"


@dataclass
class TransitionMapData:
    map_id: str
    description: str
    potion1: Dict[str, str]
    potion2: Dict[str, str]
    potion3: Dict[str, str]
    source_path: str = ""
    # 仅编辑器可视化：药水3 贝塞尔控制点相对自动控制点的像素偏移 (dx, dy)
    potion3_control_offset: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    # 可选：与 Navigation6 试次表文件名 stem 对应（不含 .json），用于自动加载 sibling trial_sequences
    linked_navigation_map_id: Optional[str] = None


def _normalize_potion_dict(raw: object, label: str) -> Dict[str, str]:
    if not isinstance(raw, dict):
        raise ValueError(f"{label} 必须是对象")
    out: Dict[str, str] = {}
    for k, v in raw.items():
        ks, vs = str(k), str(v)
        if not is_valid_state_id(ks):
            raise ValueError(f"{label} 含非法键: {ks}")
        if not is_valid_state_id(vs):
            raise ValueError(f"{label}[{ks}] 目标非法: {vs}")
        out[ks] = vs
    return out


def _normalize_potion3_offsets(raw: object) -> Dict[str, Tuple[float, float]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("potion3_control_offset 必须是对象")
    out: Dict[str, Tuple[float, float]] = {}
    for k, v in raw.items():
        ks = str(k)
        if not is_valid_state_id(ks):
            raise ValueError(f"potion3_control_offset 含非法键: {ks}")
        if isinstance(v, (list, tuple)) and len(v) >= 2:
            out[ks] = (float(v[0]), float(v[1]))
        elif isinstance(v, dict):
            out[ks] = (float(v.get("dx", 0)), float(v.get("dy", 0)))
        else:
            raise ValueError(f"potion3_control_offset[{ks}] 格式应为 [dx,dy] 或 {{dx,dy}}")
    return out


def validate_transition_map_data(
    potion1: Dict[str, str],
    potion2: Dict[str, str],
    potion3: Dict[str, str],
) -> List[str]:
    """非致命警告信息（重复键已在 parse 时去重）。"""
    msgs: List[str] = []
    for i, p in enumerate((potion1, potion2, potion3), start=1):
        missing = [s for s in STONE_IDS if s not in p]
        if missing:
            msgs.append(f"药水{i} 在 {len(missing)} 个石上无出边")
    return msgs


def load_transition_map(path: str) -> TransitionMapData:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("schema") != SCHEMA_TRANSITION:
        raise ValueError(
            f"转化地图 schema 期望 {SCHEMA_TRANSITION}: {path}"
        )
    map_id = str(data.get("map_id", "custom"))
    desc = str(data.get("description", ""))
    link_raw = data.get("linked_navigation_map_id")
    linked_nav: Optional[str] = None
    if link_raw is not None and str(link_raw).strip():
        linked_nav = str(link_raw).strip()
    p1 = _normalize_potion_dict(data.get("potion1"), "potion1")
    p2 = _normalize_potion_dict(data.get("potion2"), "potion2")
    p3 = _normalize_potion_dict(data.get("potion3"), "potion3")
    off = _normalize_potion3_offsets(data.get("potion3_control_offset"))
    return TransitionMapData(
        map_id=map_id,
        description=desc,
        potion1=p1,
        potion2=p2,
        potion3=p3,
        source_path=os.path.abspath(path),
        potion3_control_offset=off,
        linked_navigation_map_id=linked_nav,
    )


def save_transition_map(path: str, data: TransitionMapData, version: str = "1.0") -> None:
    payload = {
        "schema": SCHEMA_TRANSITION,
        "version": version,
        "map_id": data.map_id,
        "description": data.description,
        "potion1": dict(sorted(data.potion1.items())),
        "potion2": dict(sorted(data.potion2.items())),
        "potion3": dict(sorted(data.potion3.items())),
    }
    if data.potion3_control_offset:
        payload["potion3_control_offset"] = {
            k: [round(data.potion3_control_offset[k][0], 2), round(data.potion3_control_offset[k][1], 2)]
            for k in sorted(data.potion3_control_offset.keys())
        }
    if data.linked_navigation_map_id:
        payload["linked_navigation_map_id"] = data.linked_navigation_map_id
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def empty_potion_tables() -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
    return {}, {}, {}


def list_available_transition_maps(crafting_root: str) -> List[Tuple[str, str]]:
    """
    扫描 data/maps/*.json，返回 [(显示标签, 绝对路径), ...]（按文件名排序）。
    仅包含 schema 为 crafting_transition_map 的文件。
    """
    d = Path(crafting_root) / "data" / "maps"
    if not d.is_dir():
        return []
    out: List[Tuple[str, str]] = []
    for path in sorted(d.glob("*.json")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("schema") != SCHEMA_TRANSITION:
                continue
            stem = path.stem
            mid = str(data.get("map_id", stem))
            label = f"{stem}  ·  map_id: {mid}"
            out.append((label, str(path.resolve())))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
    return out
