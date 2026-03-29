"""
宏驱动的状态转移可视化：
- 读取 run_macros 输出的 macro_catalog 和 macro_usage
- 连接后得到 (start_state -> end_state) 的边强度
- 输出三类图：
  1) 有向网络图（networkx 可选）
  2) 状态转移热力图
  3) Top-K 转移条形图
- 额外输出 edge_table.csv，便于复核与二次分析

运行示例（项目根目录）：
python -m experiments.navigation6.analysis.visualize_macro_transitions ^
  --macro-catalog experiments/navigation6/outputs/analysis/macros/all_macros.json ^
  --macro-usage experiments/navigation6/outputs/analysis/macros/all_macro_usage.json ^
  --participant-id P01 ^
  --map-id map_1773511099 ^
  --out-dir experiments/navigation6/outputs/analysis/macros/viz_p01_map1
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    HAS_MPL = True
except Exception:
    HAS_MPL = False

try:
    import networkx as nx

    HAS_NX = True
except Exception:
    HAS_NX = False


EdgeKey = Tuple[int, int]


def _read_json(path: str) -> Any:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"文件不存在: {path}")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _to_macro_dict(macro_catalog: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for m in macro_catalog:
        mid = _safe_int(m.get("macro_id", -1), -1)
        if mid < 0:
            continue
        out[mid] = m
    return out


def _iter_usage_rows(
    macro_usage: List[Dict[str, Any]],
    participant_id: Optional[str],
    map_id: Optional[str],
) -> Iterable[Dict[str, Any]]:
    for r in macro_usage:
        pid = str(r.get("participant_id", "") or "")
        mid = str(r.get("map_id", "") or "")
        if participant_id is not None and pid != participant_id:
            continue
        if map_id is not None and mid != map_id:
            continue
        yield r


def build_edge_table(
    macro_catalog: List[Dict[str, Any]],
    macro_usage: List[Dict[str, Any]],
    participant_id: Optional[str],
    map_id: Optional[str],
    normalize: str = "none",
) -> List[Dict[str, Any]]:
    """
    normalize:
      - none: 原始强度 = usage_count 之和
      - sum:  归一化强度 = usage_count / 总 usage_count
      - max:  归一化强度 = usage_count / 最大 usage_count
    """
    macro_by_id = _to_macro_dict(macro_catalog)
    agg: Dict[EdgeKey, Dict[str, Any]] = defaultdict(
        lambda: {
            "raw_strength": 0.0,
            "macro_count": 0,
            "support_weighted_sum": 0.0,
            "len_weighted_sum": 0.0,
            "usage_rows": 0,
        }
    )

    filtered_rows = list(_iter_usage_rows(macro_usage, participant_id=participant_id, map_id=map_id))
    if not filtered_rows:
        return []

    total_usage = 0.0
    max_usage = 0.0
    for r in filtered_rows:
        u = float(_safe_int(r.get("usage_count", 0), 0))
        total_usage += u
        if u > max_usage:
            max_usage = u

    denom = 1.0
    mode = (normalize or "none").strip().lower()
    if mode == "sum":
        denom = total_usage if total_usage > 0 else 1.0
    elif mode == "max":
        denom = max_usage if max_usage > 0 else 1.0

    for r in filtered_rows:
        macro_id = _safe_int(r.get("macro_id", -1), -1)
        usage_count = float(_safe_int(r.get("usage_count", 0), 0))
        if usage_count <= 0:
            continue
        macro = macro_by_id.get(macro_id)
        if not macro:
            continue
        s = _safe_int(macro.get("start_state", 0), 0)
        t = _safe_int(macro.get("end_state", 0), 0)
        if s <= 0 or t <= 0:
            continue

        support = float(_safe_int(macro.get("support", 0), 0))
        seq = macro.get("sequence", [])
        seq_len = len(seq) if isinstance(seq, list) else 0
        w = usage_count / denom

        slot = agg[(s, t)]
        slot["raw_strength"] += w
        slot["macro_count"] += 1
        slot["support_weighted_sum"] += support * w
        slot["len_weighted_sum"] += seq_len * w
        slot["usage_rows"] += 1

    edge_rows: List[Dict[str, Any]] = []
    for (s, t), v in agg.items():
        strength = float(v["raw_strength"])
        if strength <= 0:
            continue
        edge_rows.append(
            {
                "start_state": s,
                "end_state": t,
                "strength": strength,
                "log_strength": math.log1p(strength),
                "macro_count": int(v["macro_count"]),
                "mean_support_w": float(v["support_weighted_sum"] / strength),
                "mean_length_w": float(v["len_weighted_sum"] / strength),
                "usage_rows": int(v["usage_rows"]),
            }
        )

    edge_rows.sort(key=lambda x: x["strength"], reverse=True)
    return edge_rows


def save_edge_csv(rows: List[Dict[str, Any]], out_csv: str) -> None:
    Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "start_state",
        "end_state",
        "strength",
        "log_strength",
        "macro_count",
        "mean_support_w",
        "mean_length_w",
        "usage_rows",
    ]
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def _select_rows(rows: List[Dict[str, Any]], top_n_edges: int) -> List[Dict[str, Any]]:
    if top_n_edges <= 0:
        return rows
    return rows[:top_n_edges]


def plot_network(rows: List[Dict[str, Any]], out_path: str, title: str) -> Optional[str]:
    if not HAS_MPL:
        return "matplotlib 不可用，跳过网络图。"
    if not HAS_NX:
        return "networkx 不可用，跳过网络图。"
    if not rows:
        return "无可绘制边，跳过网络图。"

    G = nx.DiGraph()
    for r in rows:
        s = int(r["start_state"])
        t = int(r["end_state"])
        G.add_edge(s, t, weight=float(r["strength"]))

    if G.number_of_nodes() == 0:
        return "无可绘制节点，跳过网络图。"

    strengths = [float(d["weight"]) for _, _, d in G.edges(data=True)]
    max_w = max(strengths) if strengths else 1.0
    min_w = min(strengths) if strengths else 0.0
    # 线宽仅作为辅助，主编码交给颜色（colorbar）
    widths = [1.2 + 2.2 * (w / max_w if max_w > 0 else 0.0) for w in strengths]

    num_nodes = G.number_of_nodes()
    k_layout = max(0.8, 1.5 + 10.0 / max(1, num_nodes))
    pos = nx.spring_layout(G, seed=42, k=k_layout)
    fig, ax = plt.subplots(figsize=(10, 8))
    nx.draw_networkx_nodes(
        G,
        pos,
        node_size=520,
        node_color="#1f2937",
        edgecolors="#f9fafb",
        linewidths=0.8,
        ax=ax,
    )
    nx.draw_networkx_labels(G, pos, font_size=8, font_color="#f9fafb", ax=ax)
    norm = matplotlib.colors.Normalize(vmin=min_w, vmax=max_w if max_w > min_w else (min_w + 1e-9))
    cmap = plt.cm.coolwarm  # 低值蓝，高值红
    edge_collection = nx.draw_networkx_edges(
        G,
        pos,
        width=widths,
        edge_color=strengths,
        edge_cmap=cmap,
        edge_vmin=norm.vmin,
        edge_vmax=norm.vmax,
        arrows=True,
        arrowsize=14,
        alpha=0.9,
        connectionstyle="arc3,rad=0.08",
        ax=ax,
    )
    # 用 colorbar 显示强度-颜色映射
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Strength")

    ax.set_title(title)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(out_path, dpi=220)
    plt.close(fig)
    return None


def plot_heatmap(rows: List[Dict[str, Any]], out_path: str, title: str) -> Optional[str]:
    if not HAS_MPL:
        return "matplotlib 不可用，跳过热力图。"
    if not rows:
        return "无可绘制边，跳过热力图。"

    states = sorted({int(r["start_state"]) for r in rows} | {int(r["end_state"]) for r in rows})
    idx = {s: i for i, s in enumerate(states)}
    n = len(states)
    mat = [[0.0 for _ in range(n)] for _ in range(n)]

    for r in rows:
        i = idx[int(r["start_state"])]
        j = idx[int(r["end_state"])]
        mat[i][j] += float(r["strength"])

    plt.figure(figsize=(max(6, n * 0.35), max(5, n * 0.35)))
    im = plt.imshow(mat, cmap="YlGnBu", interpolation="nearest", aspect="auto")
    plt.colorbar(im, fraction=0.046, pad=0.04, label="Strength")
    ticks = list(range(n))
    tick_labels = [str(s) for s in states]
    max_ticks = min(n, 40)
    step = 1 if n <= max_ticks else max(1, n // max_ticks)
    show_ticks = ticks[::step]
    show_labels = tick_labels[::step]
    plt.xticks(show_ticks, show_labels, rotation=60, ha="right")
    plt.yticks(show_ticks, show_labels)
    plt.xlabel("End State")
    plt.ylabel("Start State")
    if n > max_ticks:
        title = f"{title} (ticks sampled, n={n})"
    plt.title(title)
    plt.tight_layout()
    plt.savefig(out_path, dpi=220)
    plt.close()
    return None


def plot_topk_bar(rows: List[Dict[str, Any]], out_path: str, title: str, top_k: int) -> Optional[str]:
    if not HAS_MPL:
        return "matplotlib 不可用，跳过 Top-K 条形图。"
    if not rows:
        return "无可绘制边，跳过 Top-K 条形图。"

    top = rows[: max(1, top_k)]
    labels = [f"{r['start_state']}→{r['end_state']}" for r in top]
    vals = [float(r["strength"]) for r in top]

    plt.figure(figsize=(10, max(4, len(top) * 0.35)))
    y = list(range(len(top)))
    plt.barh(y, vals, color="#14b8a6")
    plt.yticks(y, labels)
    plt.gca().invert_yaxis()
    plt.xlabel("Strength")
    plt.title(title)
    plt.tight_layout()
    plt.savefig(out_path, dpi=220)
    plt.close()
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="宏驱动状态转移可视化（网络图/热力图/Top-K）")
    parser.add_argument("--macro-catalog", required=True, help="宏目录 JSON（如 all_macros.json）")
    parser.add_argument("--macro-usage", required=True, help="宏使用 JSON（如 all_macro_usage.json）")
    parser.add_argument("--participant-id", default=None, help="筛选单被试；不填则汇总全部")
    parser.add_argument("--map-id", default=None, help="筛选单地图；不填则汇总全部")
    parser.add_argument(
        "--normalize",
        default="none",
        choices=["none", "sum", "max"],
        help="强度归一化方式：none|sum|max",
    )
    parser.add_argument("--top-n-edges", type=int, default=150, help="图中最多保留多少条边（按强度降序）")
    parser.add_argument("--top-k-bar", type=int, default=20, help="Top-K 条形图的 K")
    parser.add_argument("--out-dir", required=True, help="输出目录")
    args = parser.parse_args()

    catalog = _read_json(args.macro_catalog)
    usage = _read_json(args.macro_usage)
    if not isinstance(catalog, list):
        raise ValueError("macro_catalog JSON 格式错误：应为 list。")
    if not isinstance(usage, list):
        raise ValueError("macro_usage JSON 格式错误：应为 list。")

    edges = build_edge_table(
        macro_catalog=catalog,
        macro_usage=usage,
        participant_id=args.participant_id,
        map_id=args.map_id,
        normalize=args.normalize,
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    edge_csv = str(out_dir / "edge_table.csv")
    save_edge_csv(edges, edge_csv)

    selected = _select_rows(edges, top_n_edges=args.top_n_edges)
    scope = []
    if args.participant_id:
        scope.append(f"participant={args.participant_id}")
    if args.map_id:
        scope.append(f"map={args.map_id}")
    scope_txt = ", ".join(scope) if scope else "all participants/maps"

    warnings: List[str] = []
    w = plot_network(
        rows=selected,
        out_path=str(out_dir / "macro_transition_network.png"),
        title=f"Macro Transition Network ({scope_txt}, normalize={args.normalize})",
    )
    if w:
        warnings.append(w)
    w = plot_heatmap(
        rows=selected,
        out_path=str(out_dir / "macro_transition_heatmap.png"),
        title=f"Macro Transition Heatmap ({scope_txt}, normalize={args.normalize})",
    )
    if w:
        warnings.append(w)
    w = plot_topk_bar(
        rows=edges,
        out_path=str(out_dir / "macro_transition_topk.png"),
        title=f"Top Transitions ({scope_txt}, normalize={args.normalize})",
        top_k=args.top_k_bar,
    )
    if w:
        warnings.append(w)

    summary = {
        "rows_total": len(edges),
        "rows_selected_for_graph": len(selected),
        "normalize": args.normalize,
        "participant_id": args.participant_id,
        "map_id": args.map_id,
        "top_n_edges": args.top_n_edges,
        "top_k_bar": args.top_k_bar,
        "outputs": {
            "edge_table_csv": edge_csv,
            "network_png": str(out_dir / "macro_transition_network.png"),
            "heatmap_png": str(out_dir / "macro_transition_heatmap.png"),
            "topk_png": str(out_dir / "macro_transition_topk.png"),
        },
        "warnings": warnings,
    }
    with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"[OK] 已输出到: {out_dir}")
    print(f"[OK] edge_table.csv 行数: {len(edges)}")
    if warnings:
        print("[WARN]")
        for item in warnings:
            print(f"  - {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

