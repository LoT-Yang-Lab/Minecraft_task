from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _stone_ids() -> List[str]:
    return [f"stone_{i:02d}" for i in range(1, 10)]


def _stone_id(i: int) -> str:
    return f"stone_{int(i):02d}"


def _neighbors(
    s: str,
    p1: Dict[str, str],
    p2: Dict[str, str],
    p3: Dict[str, str],
) -> List[str]:
    b1 = {v: k for k, v in p1.items()}
    b2 = {v: k for k, v in p2.items()}
    out: List[str] = []
    for d in (p1, b1, p2, b2, p3):
        nxt = d.get(s)
        if nxt:
            out.append(nxt)
    return list(dict.fromkeys(out))


def _shortest_distance(
    start: str,
    goal: str,
    p1: Dict[str, str],
    p2: Dict[str, str],
    p3: Dict[str, str],
) -> int:
    if start == goal:
        return 0
    q = deque([(start, 0)])
    seen = {start}
    while q:
        cur, d = q.popleft()
        for nxt in _neighbors(cur, p1, p2, p3):
            if nxt == goal:
                return d + 1
            if nxt not in seen:
                seen.add(nxt)
                q.append((nxt, d + 1))
    return -1


def _load_nav_pairs(path: Path) -> List[Tuple[int, int]]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    out: List[Tuple[int, int]] = []
    for rec in data.get("trials", []) or []:
        if not isinstance(rec, dict):
            continue
        if "start" in rec and "goal" in rec:
            out.append((int(rec["start"]), int(rec["goal"])))
        elif "targetA" in rec and "targetB" in rec:
            out.append((int(rec["targetA"]), int(rec["targetB"])))
    return out


def run_equivalence_preflight(
    *,
    navigation_map_path: str,
    transition_map_path: str,
    report_path: str,
) -> Dict[str, Any]:
    nav_path = Path(navigation_map_path).resolve()
    transition_path = Path(transition_map_path).resolve()
    report = {
        "navigation_map_path": str(nav_path),
        "navigation_map_id": nav_path.stem,
        "transition_map_path": str(transition_path),
        "ok": True,
        "checks": [],
        "errors": [],
    }

    with transition_path.open("r", encoding="utf-8") as fh:
        transition = json.load(fh)

    linked = str(transition.get("linked_navigation_map_id", "") or "")
    if linked and linked != nav_path.stem:
        report["ok"] = False
        report["errors"].append(
            f"linked_navigation_map_id={linked} 与导航地图 stem={nav_path.stem} 不一致"
        )
    report["checks"].append({"name": "linked_navigation_map_id", "value": linked or "<empty>"})

    req = set(_stone_ids())
    p1 = dict(transition.get("potion1", {}) or {})
    p2 = dict(transition.get("potion2", {}) or {})
    p3 = dict(transition.get("potion3", {}) or {})
    union_nodes = set(p1.keys()) | set(p1.values()) | set(p2.keys()) | set(p2.values()) | set(p3.keys()) | set(p3.values())
    if not req.issubset(union_nodes):
        report["ok"] = False
        miss = sorted(req - union_nodes)
        report["errors"].append(f"石头节点覆盖不完整，缺失: {miss}")
    report["checks"].append({"name": "node_coverage", "covered": sorted(union_nodes)})

    if len(set(p1.values())) != len(p1.values()):
        report["ok"] = False
        report["errors"].append("potion1 正向映射存在多对一，无法唯一逆向。")
    if len(set(p2.values())) != len(p2.values()):
        report["ok"] = False
        report["errors"].append("potion2 正向映射存在多对一，无法唯一逆向。")

    report["checks"].append({"name": "potion1_edges", "count": len(p1)})
    report["checks"].append({"name": "potion2_edges", "count": len(p2)})
    report["checks"].append({"name": "potion3_edges", "count": len(p3)})

    nav_seq = nav_path.parent.parent / "trial_sequences" / f"{nav_path.stem}.json"
    report["checks"].append({"name": "trial_sequence_path", "value": str(nav_seq)})
    if not nav_seq.is_file():
        report["ok"] = False
        report["errors"].append(f"未找到导航试次表: {nav_seq}")
    else:
        pairs = _load_nav_pairs(nav_seq)
        dist_list: List[int] = []
        unreachable: List[Tuple[int, int, int]] = []
        for idx, (a, b) in enumerate(pairs, start=1):
            d = _shortest_distance(_stone_id(a), _stone_id(b), p1, p2, p3)
            dist_list.append(d)
            if d < 0:
                unreachable.append((idx, a, b))
        lt2_count = sum(1 for d in dist_list if d >= 0 and d < 2)
        report["checks"].append(
            {
                "name": "trial_distance_stats_on_crafting_graph",
                "total_trials": len(pairs),
                "min_distance": min(dist_list) if dist_list else None,
                "max_distance": max(dist_list) if dist_list else None,
                "lt2_count": lt2_count,
                "unreachable_count": len(unreachable),
            }
        )
        if unreachable:
            report["ok"] = False
            report["errors"].append(
                f"存在导航试次在 crafting 图上不可达: {unreachable[:5]}"
            )

    out = Path(report_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    if not report["ok"]:
        raise ValueError("地图等价预检失败；详见 preflight_report.json")
    return report
