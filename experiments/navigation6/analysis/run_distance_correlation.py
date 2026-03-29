"""
宏与认知地图距离联结入口：加载 cogmap、宏目录与宏使用 → 操作化距离 → 宏–距离相关 → 写出 output/distance。
从项目根运行: python -m experiments.navigation6.analysis.run_distance_correlation --maps-dir ... --macro-usage ... --macro-catalog ...
"""
import argparse
import json
import os
import sys
from pathlib import Path

_analysis_dir = os.path.dirname(os.path.abspath(__file__))
_nav5_root = os.path.normpath(os.path.join(_analysis_dir, ".."))
_project_root = os.path.normpath(os.path.join(_nav5_root, ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def main():
    parser = argparse.ArgumentParser(description="Navigation6 宏–距离相关分析")
    parser.add_argument("--maps-dir", default=None, help="地图目录")
    parser.add_argument("--macro-usage", default=None, help="宏使用 JSON 路径（如 output/macros/all_macro_usage.json）")
    parser.add_argument("--macro-catalog", default=None, help="宏目录 JSON 路径（如 output/macros/all_macros.json）")
    parser.add_argument("--map-id", default=None, help="仅处理该 map_id")
    parser.add_argument("--output-dir", default=None, help="输出目录，默认 analysis/output/distance")
    args = parser.parse_args()

    # 默认地图目录：assets/maps（兼容旧 maps/）
    if args.maps_dir:
        maps_dir = args.maps_dir
    else:
        from experiments.navigation6.app.paths import maps_dir as _maps_dir
        maps_dir = _maps_dir()
    # 默认输出到 experiments/navigation6/outputs/analysis/distance
    output_dir = args.output_dir or os.path.join(_nav5_root, "outputs", "analysis", "distance")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    if not args.macro_usage or not Path(args.macro_usage).exists():
        print("请提供存在的 --macro-usage 文件")
        return
    if not args.macro_catalog or not Path(args.macro_catalog).exists():
        print("请提供存在的 --macro-catalog 文件")
        return

    with open(args.macro_usage, "r", encoding="utf-8") as f:
        macro_usage = json.load(f)
    with open(args.macro_catalog, "r", encoding="utf-8") as f:
        macro_catalog = json.load(f)

    from experiments.navigation6.app.viz.cogmap_nav6 import compute_nav6_cogmap
    from .distance import graph_distance_matrix, macro_distance_correlation

    map_files = list(Path(maps_dir).glob("*.json"))
    if args.map_id:
        map_files = [p for p in map_files if p.stem == args.map_id]

    all_results = []
    for map_path in map_files:
        map_id = map_path.stem
        try:
            cogmap = compute_nav6_cogmap(map_path=str(map_path), include_distances=True)
        except Exception as e:
            print(f"[{map_id}] cogmap 失败: {e}")
            continue
        dist_mat = graph_distance_matrix(cogmap)
        results = macro_distance_correlation(macro_usage, macro_catalog, dist_mat)
        all_results.append({"map_id": map_id, "macro_distance_results": results})
        out_path = os.path.join(output_dir, f"{map_id}_macro_distance.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"map_id": map_id, "results": results}, f, ensure_ascii=False, indent=2)
        print(f"[{map_id}] 宏–距离结果已写入 {out_path}")

        # 可视化：距离–使用散点图（每宏一个点）
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            points = []
            for row in results:
                d = row.get("mean_graph_distance")
                u = row.get("mean_usage")
                if d is None or u is None:
                    continue
                points.append((d, u, str(row.get("macro_id")), float(u)))
            if points:
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]
                fig, ax = plt.subplots(figsize=(5, 4))
                ax.scatter(xs, ys, alpha=0.75)
                ax.set_xlabel("Mean graph distance (start→end)")
                ax.set_ylabel("Mean usage count")
                ax.set_title(f"Macro usage vs. graph distance ({map_id})")
                # 按使用量选最多 8 个点标注，并用交替偏移减轻重叠
                sorted_by_usage = sorted(enumerate(points), key=lambda t: -t[1][3])
                offsets = [(5, 5), (-5, 5), (5, -5), (-5, -5), (8, 0), (0, 8), (-8, 0), (0, -8)]
                for k, (i, (xi, yi, lbl, _)) in enumerate(sorted_by_usage[:8]):
                    xytext = offsets[k % len(offsets)]
                    ax.annotate(lbl, (xi, yi), textcoords="offset points", xytext=xytext, fontsize=8, alpha=0.8)
                fig.tight_layout()
                fig.savefig(os.path.join(output_dir, f"{map_id}_macro_distance_scatter.svg"))
                plt.close(fig)
        except Exception as e:
            print(f"[viz] 宏–距离可视化失败（{map_id}）：{e}")

    summary_path = os.path.join(output_dir, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"汇总已写入 {summary_path}")


if __name__ == "__main__":
    main()
