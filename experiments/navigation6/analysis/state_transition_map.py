"""
策略标注的显著状态转移图（Navigation6）

读取 RLDataRecorder 导出的单被试轨迹（CSV/XLSX），在 Navigation6 地图上构建：
1) 有效状态（覆盖率阈值）；
2) 显著状态转移（bootstrap + BH-FDR）；
3) 边标签为主导规则（动作类别）。

输出：
- graph.json（结构化图数据，稳定可复用）
- graph.graphml（可选，需要 networkx）
- graph.png/pdf（可选，需要 matplotlib + networkx）
- summary.json（参数与摘要）
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


# 确保项目根在 sys.path，便于导入 experiments/shared
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_NAV6_ROOT = os.path.normpath(os.path.join(_THIS_DIR, ".."))          # experiments/navigation6
_PROJECT_ROOT = os.path.normpath(os.path.join(_NAV6_ROOT, "..", ".."))  # repo root
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


try:
    import pandas as pd  # type: ignore

    HAS_PANDAS = True
except Exception:
    HAS_PANDAS = False


try:
    import numpy as np  # type: ignore

    HAS_NUMPY = True
except Exception:
    HAS_NUMPY = False


try:
    import networkx as nx  # type: ignore

    HAS_NETWORKX = True
except Exception:
    HAS_NETWORKX = False


try:
    import matplotlib.pyplot as plt  # type: ignore

    HAS_MPL = True
except Exception:
    HAS_MPL = False


DEFAULT_MAP_STRUCTURE_TO_ID = {
    "地图1774095558": "map_1774095558",
    "Barbell": "Barbell",
}


@dataclass(frozen=True)
class StateKey:
    pos_code: int
    phase: str
    at_station: bool
    dist_bin: str  # near/mid/far/na

    def to_id(self) -> str:
        return f"c{self.pos_code}|ph={self.phase}|st={int(self.at_station)}|d={self.dist_bin}"


def _read_table(path: str) -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    if HAS_PANDAS and p.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(p)  # type: ignore[name-defined]
        return df.to_dict("records")
    with open(p, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _safe_bool(x: Any, default: bool = False) -> bool:
    if isinstance(x, bool):
        return x
    if x is None:
        return default
    s = str(x).strip().lower()
    if s in ("true", "1", "yes", "y"):
        return True
    if s in ("false", "0", "no", "n"):
        return False
    return default


def _action_class(action_type: str, action_detail: str, action_valid: bool) -> str:
    if not action_valid:
        return "Invalid"
    at = (action_type or "").strip()
    ad = (action_detail or "").strip()
    ad_low = ad.lower()
    at_low = at.lower()

    if at_low == "bus":
        return "Bus"
    if at_low == "metro":
        return "Metro"
    if at_low in ("lightrail", "light_rail"):
        return "LightRail"
    if at_low == "subway" or ad_low in ("subway", "instant"):
        return "Metro"
    if at_low == "portal" or ad_low == "portal":
        return "Portal"
    if ad_low == "door":
        return "Door"
    if ad_low == "walk":
        return "Walk"

    # 兼容其他任务（如 collect）
    if at_low in ("up", "down", "left", "right", "nw", "ne", "sw", "se"):
        return "Walk"
    return "Other"


def _ensure_maps_dir(maps_dir: Optional[str]) -> str:
    if maps_dir is None:
        from experiments.navigation6.app.paths import maps_dir as _maps_dir
        return _maps_dir()
    return maps_dir


class _NullRecorder:
    """用于分析构造 GameNavigation6，避免写 rl_data。"""
    def __init__(self):
        self.memory_buffer = []
        self.episode_count = 0
        self.step_count = 0

    def start_episode(self):
        self.episode_count += 1
        self.step_count = 0

    def log_action(self, *args, **kwargs):
        self.step_count += 1

    def save_to_file(self):
        return


@dataclass
class MapContext:
    map_id: str
    map_path: str
    cell_to_code: Dict[Tuple[int, int], int]
    target_pos: Optional[Tuple[int, int]]
    station_positions: set[Tuple[int, int]]
    diameter: int


def _build_position_encoding_without_pygame(game: Any) -> Tuple[Dict[Tuple[int, int], int], Dict[int, Tuple[int, int]], int]:
    """与 app.experiment.main.build_position_encoding 一致（无 pygame）。"""
    obstacle_map = getattr(game, "obstacle_map", {}) or {}
    walkable = [
        c for c in (getattr(game, "single_cells", set()) or set())
        if c not in obstacle_map
    ]
    for pos in game._all_station_positions():
        if pos not in obstacle_map and pos not in walkable:
            walkable.append(pos)
    for _rid, room in getattr(game, "rooms", {}).items():
        lx, ly = room.logical_pos
        for dy in range(3):
            for dx in range(3):
                gx, gy = lx * 3 + dx, ly * 3 + dy
                if game._is_walkable(gx, gy) and (gx, gy) not in walkable:
                    walkable.append((gx, gy))
    walkable = sorted(set(walkable), key=lambda c: (c[0], c[1]))
    cell_to_code = {c: i + 1 for i, c in enumerate(walkable)}
    code_to_cell = {i + 1: c for i, c in enumerate(walkable)}
    target_pos = getattr(game, "original_target_pos", None)
    target_code = cell_to_code[target_pos] if target_pos and target_pos in cell_to_code else 0
    return cell_to_code, code_to_cell, target_code


def load_map_context(map_id: str, maps_dir: Optional[str] = None) -> MapContext:
    maps_dir = _ensure_maps_dir(maps_dir)
    map_file = map_id + ".json" if not map_id.endswith(".json") else map_id
    map_path = os.path.join(maps_dir, map_file)
    map_path = os.path.abspath(map_path)
    if not os.path.exists(map_path):
        raise FileNotFoundError(f"Map file not found: {map_path}")

    from experiments.navigation6.app.experiment.game import GameNavigation6

    recorder = _NullRecorder()
    game = GameNavigation6(
        recorder,
        map_type=map_id,
        target_entropy=0.5,
        enable_experiment=False,
        custom_map_file=map_path,
    )

    cell_to_code, _code_to_cell, _target_code = _build_position_encoding_without_pygame(game)
    target_pos = getattr(game, "original_target_pos", None)
    station_positions = set(game.get_subway_station_positions())
    diameter = int(getattr(game, "get_map_diameter")())

    return MapContext(
        map_id=map_id.replace(".json", ""),
        map_path=map_path,
        cell_to_code=cell_to_code,
        target_pos=target_pos,
        station_positions=station_positions,
        diameter=diameter,
    )


def _dist_bin(manhattan: Optional[int], diameter: int) -> str:
    if manhattan is None:
        return "na"
    if diameter <= 0:
        return "na"
    t1 = max(1, diameter // 3)
    t2 = max(t1 + 1, (2 * diameter) // 3)
    if manhattan <= t1:
        return "near"
    if manhattan <= t2:
        return "mid"
    return "far"


def make_state(
    ctx: MapContext,
    gx: int,
    gy: int,
    phase: str,
) -> Optional[StateKey]:
    code = ctx.cell_to_code.get((gx, gy), 0)
    if code == 0:
        return None
    at_station = (gx, gy) in ctx.station_positions
    if ctx.target_pos is not None:
        man = abs(gx - ctx.target_pos[0]) + abs(gy - ctx.target_pos[1])
    else:
        man = None
    db = _dist_bin(man, ctx.diameter)
    ph = (phase or "").strip() or "unknown"
    return StateKey(code, ph, at_station, db)


def coverage_states(state_ids: Sequence[str], coverage: float) -> set[str]:
    if not state_ids:
        return set()
    counts = Counter(state_ids)
    total = sum(counts.values())
    need = coverage * total
    acc = 0
    out: set[str] = set()
    for sid, c in counts.most_common():
        out.add(sid)
        acc += c
        if acc >= need:
            break
    return out


def bh_fdr(p_values: Dict[str, float], q: float) -> Tuple[set[str], Dict[str, float]]:
    """
    Benjamini–Hochberg FDR.
    输入：候选边 key -> pvalue
    返回：通过的 key 集合，以及每个 key 的 q-value（BH 调整后）
    """
    items = sorted(p_values.items(), key=lambda kv: kv[1])
    m = len(items)
    if m == 0:
        return set(), {}

    qvals: Dict[str, float] = {}
    min_q = 1.0
    # 逆序计算 q-value = min_{j>=i} (m/j)*p_j
    for rank, (k, p) in enumerate(reversed(items), start=1):
        i = m - rank + 1
        val = (m / i) * p
        if val < min_q:
            min_q = val
        qvals[k] = min(1.0, min_q)

    accepted: set[str] = set()
    for i, (k, p) in enumerate(items, start=1):
        if p <= (i / m) * q:
            accepted.add(k)
    return accepted, qvals


def bootstrap_significant_edges(
    edges_by_source: Dict[str, Counter],
    global_target_probs: Dict[str, float],
    B: int,
    fdr_q: float,
    min_out_count: int,
    rng_seed: int,
) -> Tuple[Dict[Tuple[str, str], Dict[str, Any]], Dict[str, Any]]:
    """
    对每个源状态 S：对其所有候选后继做 bootstrap p-value，再做 BH-FDR。
    返回：显著边属性 dict，以及统计摘要。
    """
    rng = None
    if HAS_NUMPY:
        rng = np.random.default_rng(rng_seed)  # type: ignore[name-defined]

    sig_edges: Dict[Tuple[str, str], Dict[str, Any]] = {}
    per_source_stats: Dict[str, Any] = {}

    # 预计算全局后继支持集（保证顺序稳定）
    targets = list(global_target_probs.keys())
    probs = [global_target_probs[t] for t in targets]

    for s, tgt_counts in edges_by_source.items():
        n_out = sum(tgt_counts.values())
        if n_out < min_out_count:
            per_source_stats[s] = {"n_out": n_out, "skipped": True, "reason": "min_out_count"}
            continue

        # 观测概率
        obs_p: Dict[str, float] = {t: (c / n_out) for t, c in tgt_counts.items()}

        # bootstrap：对每个候选 t 统计 null 下 P>=obs 的次数
        exceed = {t: 0 for t in tgt_counts.keys()}

        if HAS_NUMPY and rng is not None:
            # multinomial 一次生成计数，再转概率
            for _ in range(B):
                sample = rng.multinomial(n_out, probs)  # type: ignore[attr-defined]
                for t in exceed.keys():
                    idx = targets.index(t)  # 候选数量通常不大；若需要可优化为 dict 索引
                    p_null = sample[idx] / n_out
                    if p_null >= obs_p[t]:
                        exceed[t] += 1
        else:
            # 无 numpy：朴素采样（慢，但可跑）
            import random

            random.seed(rng_seed)
            # 预构造 CDF
            cdf = []
            acc = 0.0
            for p in probs:
                acc += p
                cdf.append(acc)

            def draw_one() -> str:
                r = random.random()
                for i, v in enumerate(cdf):
                    if r <= v:
                        return targets[i]
                return targets[-1]

            for _ in range(B):
                sample_counts = Counter(draw_one() for _ in range(n_out))
                for t in exceed.keys():
                    p_null = sample_counts[t] / n_out
                    if p_null >= obs_p[t]:
                        exceed[t] += 1

        pvals = {t: (1.0 + exceed[t]) / (B + 1.0) for t in exceed.keys()}
        accepted, qvals = bh_fdr(pvals, q=fdr_q)
        per_source_stats[s] = {
            "n_out": n_out,
            "candidates": len(pvals),
            "accepted": len(accepted),
        }

        for t in accepted:
            sig_edges[(s, t)] = {
                "p_value": pvals[t],
                "q_value": qvals.get(t, pvals[t]),
                "p_obs": obs_p[t],
                "count": int(tgt_counts[t]),
            }

    summary = {
        "sources_total": len(edges_by_source),
        "edges_sig": len(sig_edges),
        "min_out_count": min_out_count,
        "B": B,
        "fdr_q": fdr_q,
    }
    return sig_edges, {"per_source": per_source_stats, "summary": summary}


def build_graph_from_log(
    log_path: str,
    map_id: str,
    maps_dir: Optional[str],
    coverage: float,
    B: int,
    fdr_q: float,
    min_out_count: int,
    rng_seed: int,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    ctx = load_map_context(map_id, maps_dir=maps_dir)
    rows = _read_table(log_path)

    # 过滤该 map 的行，并按 episode/step 排序
    filtered: List[Dict[str, Any]] = []
    for r in rows:
        map_structure = str(r.get("Map_Structure", "") or "")
        mid = DEFAULT_MAP_STRUCTURE_TO_ID.get(map_structure, map_structure)
        mid = mid.replace(".json", "")
        if mid != map_id.replace(".json", ""):
            continue
        filtered.append(r)

    filtered.sort(key=lambda r: (_safe_int(r.get("Episode_ID", 0)), _safe_int(r.get("Step_Index", 0))))
    if len(filtered) < 2:
        raise ValueError("Not enough trajectory rows for this map (need >=2).")

    # 构造 state 序列与动作序列（对齐到 transition）
    state_seq: List[str] = []
    state_meta: Dict[str, StateKey] = {}

    # 注意：RLDataRecorder 的 Phase 字段不固定；这里兼容 Phase/phase
    def get_phase(r: Dict[str, Any]) -> str:
        return str(r.get("Phase", r.get("phase", "")) or "")

    for r in filtered:
        gx = _safe_int(r.get("Grid_X", 0))
        gy = _safe_int(r.get("Grid_Y", 0))
        sk = make_state(ctx, gx, gy, phase=get_phase(r))
        if sk is None:
            state_seq.append("")  # placeholder
            continue
        sid = sk.to_id()
        state_seq.append(sid)
        state_meta[sid] = sk

    # 有效状态：覆盖率筛选
    state_seq_nonempty = [s for s in state_seq if s]
    s_eff = coverage_states(state_seq_nonempty, coverage=coverage)

    # 统计全局状态频率（用于 global null）
    freq_eff = Counter(s for s in state_seq_nonempty if s in s_eff)
    total_eff = sum(freq_eff.values()) or 1
    global_probs = {s: (c / total_eff) for s, c in freq_eff.items()}

    # 转移统计：按相邻行、同 episode 连接
    edges_by_source: Dict[str, Counter] = defaultdict(Counter)
    edge_rule_counts: Dict[Tuple[str, str], Counter] = defaultdict(Counter)
    node_counts = Counter(s for s in state_seq_nonempty if s in s_eff)

    n_transitions = 0
    n_skipped = 0
    for i in range(len(filtered) - 1):
        r = filtered[i]
        rn = filtered[i + 1]
        ep = r.get("Episode_ID")
        if rn.get("Episode_ID") != ep:
            continue
        s = state_seq[i]
        t = state_seq[i + 1]
        if not s or not t:
            n_skipped += 1
            continue
        if s not in s_eff or t not in s_eff:
            n_skipped += 1
            continue

        action_type = str(r.get("Action_Type", "") or "")
        action_detail = str(r.get("Action_Detail", "") or "")
        action_valid = _safe_bool(r.get("Action_Valid", True), default=True)
        cls = _action_class(action_type, action_detail, action_valid)

        edges_by_source[s][t] += 1
        edge_rule_counts[(s, t)][cls] += 1
        n_transitions += 1

    sig_edges, sig_stats = bootstrap_significant_edges(
        edges_by_source=edges_by_source,
        global_target_probs=global_probs,
        B=B,
        fdr_q=fdr_q,
        min_out_count=min_out_count,
        rng_seed=rng_seed,
    )

    # 构建最终 graph dict（只保留显著边）
    nodes_out: List[Dict[str, Any]] = []
    for sid, cnt in node_counts.most_common():
        sk = state_meta.get(sid)
        nodes_out.append({
            "id": sid,
            "count": int(cnt),
            "pos_code": sk.pos_code if sk else None,
            "phase": sk.phase if sk else None,
            "at_station": sk.at_station if sk else None,
            "dist_bin": sk.dist_bin if sk else None,
        })

    edges_out: List[Dict[str, Any]] = []
    for (s, t), attrs in sig_edges.items():
        rule_dist = edge_rule_counts.get((s, t), Counter())
        label = rule_dist.most_common(1)[0][0] if rule_dist else "Other"
        edges_out.append({
            "source": s,
            "target": t,
            "count": attrs["count"],
            "p_obs": attrs["p_obs"],
            "p_value": attrs["p_value"],
            "q_value": attrs["q_value"],
            "label": label,
            "label_dist": dict(rule_dist),
        })

    graph = {
        "name": "策略标注的显著状态转移图",
        "map_id": ctx.map_id,
        "map_path": ctx.map_path,
        "params": {
            "coverage": coverage,
            "bootstrap_B": B,
            "fdr_q": fdr_q,
            "min_out_count": min_out_count,
            "rng_seed": rng_seed,
        },
        "nodes": nodes_out,
        "edges": edges_out,
    }

    summary = {
        "log_path": os.path.abspath(log_path),
        "map_id": ctx.map_id,
        "rows_total": len(rows),
        "rows_filtered": len(filtered),
        "states_total": len(set(state_seq_nonempty)),
        "states_effective": len(s_eff),
        "transitions_used": n_transitions,
        "transitions_skipped": n_skipped,
        "nodes_in_graph": len(nodes_out),
        "edges_in_graph": len(edges_out),
        "bootstrap": sig_stats,
        "deps": {
            "pandas": HAS_PANDAS,
            "numpy": HAS_NUMPY,
            "networkx": HAS_NETWORKX,
            "matplotlib": HAS_MPL,
        },
    }
    return graph, summary


def export_outputs(
    graph: Dict[str, Any],
    summary: Dict[str, Any],
    out_dir: str,
    max_nodes_plot: int,
    export_graphml: bool,
    export_plot: bool,
) -> None:
    outp = Path(out_dir)
    outp.mkdir(parents=True, exist_ok=True)

    (outp / "graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    (outp / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if export_graphml:
        if not HAS_NETWORKX:
            raise RuntimeError("networkx not available, cannot export GraphML.")
        G = nx.DiGraph()
        for n in graph["nodes"]:
            G.add_node(n["id"], **{k: v for k, v in n.items() if k != "id"})
        for e in graph["edges"]:
            G.add_edge(e["source"], e["target"], **{k: v for k, v in e.items() if k not in ("source", "target")})
        nx.write_graphml(G, outp / "graph.graphml")

    if export_plot:
        if not (HAS_NETWORKX and HAS_MPL):
            raise RuntimeError("networkx/matplotlib not available, cannot plot.")
        G = nx.DiGraph()
        nodes = graph["nodes"][:max_nodes_plot] if max_nodes_plot > 0 else graph["nodes"]
        node_set = {n["id"] for n in nodes}
        for n in nodes:
            G.add_node(n["id"], count=n.get("count", 1), label=f"c{n.get('pos_code')}")
        for e in graph["edges"]:
            if e["source"] in node_set and e["target"] in node_set:
                G.add_edge(e["source"], e["target"], weight=e.get("p_obs", 0.0), label=e.get("label", "Other"))

        if G.number_of_nodes() == 0:
            return

        num_nodes = G.number_of_nodes()
        k_layout = max(1.0, 2.0 + 15.0 / max(1, num_nodes))
        pos = nx.spring_layout(G, seed=42, k=k_layout)
        counts = [max(1, int(G.nodes[n].get("count", 1))) for n in G.nodes()]
        maxc = max(counts) if counts else 1
        raw_sizes = [120 + 1200 * (c / maxc) for c in counts]
        sizes = [min(s, 420) for s in raw_sizes]

        # 边宽与颜色按 label
        edges = list(G.edges())
        widths = [1.0 + 6.0 * float(G.edges[e].get("weight", 0.0)) for e in edges]
        edge_label_list = [str(G.edges[e].get("label", "Other")) for e in edges]
        palette = {
            "Walk": "#4C78A8",
            "Door": "#F58518",
            "Bus": "#4C78A8",
            "Metro": "#E8C547",
            "LightRail": "#54A24B",
            "Subway": "#E8C547",
            "Portal": "#B279A2",
            "Invalid": "#E45756",
            "Other": "#9D9DA0",
        }
        colors = [palette.get(l, palette["Other"]) for l in edge_label_list]

        plt.figure(figsize=(12, 10))
        nx.draw_networkx_nodes(G, pos, node_size=sizes, node_color="#222222", edgecolors="#FFFFFF", linewidths=0.8)
        nx.draw_networkx_edges(G, pos, width=widths, edge_color=colors, arrows=True, arrowsize=14, alpha=0.85)

        # 节点标签：只显示 pos_code（避免太长）
        node_labels = {n: str(G.nodes[n].get("label", "")) for n in G.nodes()}
        nx.draw_networkx_labels(G, pos, labels=node_labels, font_size=8, font_color="#FFFFFF")

        # 边标签：按权重的前 25% 分位显示，避免细边多时无标签
        edge_labels = {}
        if edges and widths:
            thresh = np.percentile(widths, 75) if HAS_NUMPY else (max(widths) * 0.5)
            for e, w, l in zip(edges, widths, edge_label_list):
                if w >= max(3.0, thresh):
                    edge_labels[e] = l
        nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=7, font_color="#111111")

        plt.axis("off")
        plt.tight_layout()
        plt.savefig(outp / "graph.png", dpi=200)
        plt.savefig(outp / "graph.pdf")
        plt.close()


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Navigation6: 策略标注的显著状态转移图")
    ap.add_argument("--log", required=True, help="RLDataRecorder 导出的轨迹 CSV/XLSX 文件路径")
    ap.add_argument("--map-id", required=True, help="地图 id，如 map_1773511099（或 Barbell）")
    ap.add_argument("--maps-dir", default=None, help="地图目录（默认 experiments/navigation6/maps）")
    ap.add_argument("--out", required=True, help="输出目录")

    ap.add_argument("--coverage", type=float, default=0.70, help="有效状态覆盖率阈值（默认 0.70）")
    ap.add_argument("--bootstrap-B", type=int, default=2000, help="bootstrap 次数（默认 2000）")
    ap.add_argument("--fdr-q", type=float, default=0.05, help="BH-FDR 阈值（默认 0.05）")
    ap.add_argument("--min-out-count", type=int, default=10, help="源状态出边样本数不足则跳过（默认 10）")
    ap.add_argument("--seed", type=int, default=7, help="随机种子（默认 7）")

    ap.add_argument("--max-nodes-plot", type=int, default=80, help="绘图最多节点数（默认 80；0=全画）")
    ap.add_argument("--no-graphml", action="store_true", help="不导出 GraphML")
    ap.add_argument("--no-plot", action="store_true", help="不导出 PNG/PDF 图")

    args = ap.parse_args(argv)

    graph, summary = build_graph_from_log(
        log_path=args.log,
        map_id=args.map_id,
        maps_dir=args.maps_dir,
        coverage=args.coverage,
        B=args.bootstrap_B,
        fdr_q=args.fdr_q,
        min_out_count=args.min_out_count,
        rng_seed=args.seed,
    )

    export_outputs(
        graph=graph,
        summary=summary,
        out_dir=args.out,
        max_nodes_plot=args.max_nodes_plot,
        export_graphml=(not args.no_graphml),
        export_plot=(not args.no_plot),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

