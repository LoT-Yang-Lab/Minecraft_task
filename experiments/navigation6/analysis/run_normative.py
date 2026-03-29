"""
规范策略线入口：加载认知地图 → 构建 InternalModel → 求解 QMDP → 加载练习/轨迹 → 对比 → 输出一致率等。
从项目根运行: python -m experiments.navigation6.analysis.run_normative --maps-dir ... --practice-dir ...
"""
import argparse
import json
import os
import sys
from pathlib import Path

# 项目根
_analysis_dir = os.path.dirname(os.path.abspath(__file__))
_nav5_root = os.path.normpath(os.path.join(_analysis_dir, ".."))
_project_root = os.path.normpath(os.path.join(_nav5_root, ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def main():
    parser = argparse.ArgumentParser(description="Navigation6 规范策略：cogmap → QMDP → 行为对比")
    parser.add_argument("--maps-dir", default=None, help="地图目录，默认 experiments/navigation6/maps")
    parser.add_argument("--practice-dir", default=None, help="练习 JSON 目录（可选；如仅做熟悉训练可不提供）")
    parser.add_argument("--rl-data", default=None, help="rl_data 根目录（可选）")
    parser.add_argument("--map-id", default=None, help="仅处理该 map_id；默认处理所有可用地图")
    parser.add_argument("--output-dir", default=None, help="输出目录，默认 analysis/output/normative")
    parser.add_argument(
        "--baseline",
        default="both",
        choices=["qmdp", "astar", "both"],
        help="对照基线：qmdp（原逻辑）/ astar（最短路）/ both（两者都跑）",
    )
    parser.add_argument(
        "--infer",
        action="store_true",
        help="输出推断友好的一致率摘要：被试聚合 + participant-cluster bootstrap CI（推荐正式实验轨迹使用）",
    )
    parser.add_argument(
        "--mixed-effects",
        action="store_true",
        help="在正式实验轨迹上一并拟合混合效应（被试聚类的 logit）并输出 baseline 的 OR/CI（路线B）",
    )
    parser.add_argument("--bootstrap-n", type=int, default=2000, help="cluster bootstrap 重采样次数（--infer 生效）")
    parser.add_argument("--bootstrap-seed", type=int, default=0, help="cluster bootstrap 随机种子（--infer 生效）")
    parser.add_argument("--alpha", type=float, default=0.05, help="置信水平：CI=(alpha/2, 1-alpha/2)（--infer 生效）")
    args = parser.parse_args()

    # 默认地图目录：assets/maps（兼容旧 maps/）
    if args.maps_dir:
        maps_dir = args.maps_dir
    else:
        from experiments.navigation6.app.paths import maps_dir as _maps_dir
        maps_dir = _maps_dir()
    # 默认输出到 experiments/navigation6/outputs/analysis/normative，避免混在 analysis 源码目录下
    output_dir = args.output_dir or os.path.join(_nav5_root, "outputs", "analysis", "normative")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    from experiments.navigation6.app.viz.cogmap_nav6 import compute_nav6_cogmap
    from .data.load_practice import load_practice_dir
    from .data.load_trajectory import load_trajectory_dir, DEFAULT_MAP_STRUCTURE_TO_ID
    from .normative import (
        build_internal_model_from_cogmap,
        solve_qmdp_for_map,
        get_optimal_next_dict,
        export_policy_to_dict,
        build_astar_next_dict,
        compare_practice_to_policy,
        compare_trajectory_to_policy,
        summarize_trajectory_consistency_inference,
    )
    from .normative.mixed_effects import (
        build_consistency_long_table,
        fit_mixed_logit,
    )

    map_files = list(Path(maps_dir).glob("*.json"))
    if args.map_id:
        map_files = [p for p in map_files if p.stem == args.map_id]
    if not map_files:
        print("未找到地图文件")
        return

    # 练习数据（可选）：若仅用于熟悉任务，可不提供也不影响正式实验轨迹分析
    practice_records = []
    practice_dir = args.practice_dir
    if practice_dir:
        if Path(practice_dir).is_dir():
            practice_records = load_practice_dir(practice_dir)

    trajectory_rows = []
    # 默认轨迹数据目录：data/raw/trajectory（若不存在则 load_trajectory_dir 会回退项目根 rl_data）
    rl_data_dir = args.rl_data or os.path.join(_nav5_root, "data", "raw", "trajectory")
    if Path(rl_data_dir).is_dir():
        trajectory_rows = load_trajectory_dir(rl_data_dir, maps_dir=maps_dir)

    # 可视化所需的聚合容器（分别为 QMDP 与 A*）
    qmdp_consistency_by_map = []          # [(map_id, practice_rate, trajectory_rate)]
    qmdp_phase_consistency_by_map = []    # [(map_id, {'learning': rate, 'test': rate})]
    astar_consistency_by_map = []         # [(map_id, practice_rate, trajectory_rate)]
    astar_phase_consistency_by_map = []   # [(map_id, {'learning': rate, 'test': rate})]

    for map_path in map_files:
        map_id = map_path.stem
        map_str = os.path.abspath(map_path)
        try:
            cogmap = compute_nav6_cogmap(map_path=map_str, include_distances=True)
        except Exception as e:
            print(f"[{map_id}] cogmap 失败: {e}")
            continue
        precs = [r for r in practice_records if r.get("map_id") == map_id]
        trajs = [r for r in trajectory_rows if r.get("map_id") == map_id]
        if args.baseline in ("qmdp", "both"):
            model, _ = build_internal_model_from_cogmap(cogmap)
            policy = solve_qmdp_for_map(model)
            optimal_next = get_optimal_next_dict(policy)
            policy_dict = export_policy_to_dict(policy)

            out_path = os.path.join(output_dir, f"{map_id}_policy.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(policy_dict, f, ensure_ascii=False, indent=2)
            print(f"[{map_id}] QMDP 策略已写入 {out_path}")

            summary = {"map_id": map_id, "baseline": "qmdp", "practice": None, "trajectory": None}
            if precs:
                practice_result = compare_practice_to_policy(precs, optimal_next)
                summary["practice"] = practice_result
                print(f"[{map_id}] QMDP 练习一致率: {practice_result.get('consistency_rate', 0):.2%} (n={practice_result.get('total', 0)})")
            if trajs:
                traj_result = compare_trajectory_to_policy(trajs, optimal_next)
                summary["trajectory"] = traj_result
                print(f"[{map_id}] QMDP 轨迹一致率: {traj_result.get('consistency_rate', 0):.2%} (steps={traj_result.get('total_steps', 0)})")
                if args.infer:
                    summary["trajectory_inference"] = summarize_trajectory_consistency_inference(
                        trajs,
                        optimal_next,
                        n_boot=args.bootstrap_n,
                        alpha=args.alpha,
                        seed=args.bootstrap_seed,
                    )
                if args.mixed_effects and trajs:
                    long_rows = build_consistency_long_table(trajs, optimal_qmdp=optimal_next, optimal_astar=None)
                    mm_res = fit_mixed_logit(long_rows)
                    summary["mixed_effects"] = {
                        "enabled": mm_res.enabled,
                        "model": mm_res.model,
                        "baseline_name": mm_res.baseline_name,
                        "warning": mm_res.warning,
                        "fixed_effects": {
                            name: {
                                "coef": eff.coef,
                                "se": eff.se,
                                "z": eff.z,
                                "p": eff.p,
                                "ci_low": eff.ci_low,
                                "ci_high": eff.ci_high,
                                "or": eff.or_value,
                                "or_ci_low": eff.or_ci_low,
                                "or_ci_high": eff.or_ci_high,
                            }
                            for name, eff in mm_res.fixed_effects.items()
                        },
                    }
            sum_path = os.path.join(output_dir, f"{map_id}_summary.json")
            with open(sum_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)

            # 聚合用于可视化的数据（QMDP）
            prac_rate = summary["practice"]["consistency_rate"] if summary.get("practice") else None
            traj_rate = summary["trajectory"]["consistency_rate"] if summary.get("trajectory") else None
            qmdp_consistency_by_map.append((map_id, prac_rate, traj_rate))
            if summary.get("practice") and isinstance(summary["practice"].get("by_phase"), dict):
                bp = summary["practice"]["by_phase"]
                learning_rate = (bp.get("learning", {}) or {}).get("rate")
                test_rate = (bp.get("test", {}) or {}).get("rate")
                qmdp_phase_consistency_by_map.append((map_id, {"learning": learning_rate, "test": test_rate}))

        if args.baseline in ("astar", "both"):
            astar_next = build_astar_next_dict(cogmap)
            a_summary = {"map_id": map_id, "baseline": "astar", "practice": None, "trajectory": None}
            if precs:
                practice_result = compare_practice_to_policy(precs, astar_next)
                a_summary["practice"] = practice_result
                print(f"[{map_id}] A* 练习一致率: {practice_result.get('consistency_rate', 0):.2%} (n={practice_result.get('total', 0)})")
            if trajs:
                traj_result = compare_trajectory_to_policy(trajs, astar_next)
                a_summary["trajectory"] = traj_result
                print(f"[{map_id}] A* 轨迹一致率: {traj_result.get('consistency_rate', 0):.2%} (steps={traj_result.get('total_steps', 0)})")
                if args.infer:
                    a_summary["trajectory_inference"] = summarize_trajectory_consistency_inference(
                        trajs,
                        astar_next,
                        n_boot=args.bootstrap_n,
                        alpha=args.alpha,
                        seed=args.bootstrap_seed,
                    )
                if args.mixed_effects and trajs:
                    long_rows = build_consistency_long_table(trajs, optimal_qmdp=None, optimal_astar=astar_next)
                    mm_res = fit_mixed_logit(long_rows)
                    a_summary["mixed_effects"] = {
                        "enabled": mm_res.enabled,
                        "model": mm_res.model,
                        "baseline_name": mm_res.baseline_name,
                        "warning": mm_res.warning,
                        "fixed_effects": {
                            name: {
                                "coef": eff.coef,
                                "se": eff.se,
                                "z": eff.z,
                                "p": eff.p,
                                "ci_low": eff.ci_low,
                                "ci_high": eff.ci_high,
                                "or": eff.or_value,
                                "or_ci_low": eff.or_ci_low,
                                "or_ci_high": eff.or_ci_high,
                            }
                            for name, eff in mm_res.fixed_effects.items()
                        },
                    }
            a_sum_path = os.path.join(output_dir, f"{map_id}_astar_summary.json")
            with open(a_sum_path, "w", encoding="utf-8") as f:
                json.dump(a_summary, f, ensure_ascii=False, indent=2)

            # 聚合用于可视化的数据（A*）
            prac_rate = a_summary["practice"]["consistency_rate"] if a_summary.get("practice") else None
            traj_rate = a_summary["trajectory"]["consistency_rate"] if a_summary.get("trajectory") else None
            astar_consistency_by_map.append((map_id, prac_rate, traj_rate))
            if a_summary.get("practice") and isinstance(a_summary["practice"].get("by_phase"), dict):
                bp = a_summary["practice"]["by_phase"]
                learning_rate = (bp.get("learning", {}) or {}).get("rate")
                test_rate = (bp.get("test", {}) or {}).get("rate")
                astar_phase_consistency_by_map.append((map_id, {"learning": learning_rate, "test": test_rate}))

    # 生成可视化：一致率柱状图（总）与分阶段柱状图
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.font_manager as fm
        # 中文字体：避免地图名等中文显示为方框
        _font_names = ("Microsoft YaHei", "SimHei", "SimSun", "Noto Sans CJK SC", "WenQuanYi Micro Hei")
        _chinese_font = None
        try:
            for name in _font_names:
                for f in fm.fontManager.ttflist:
                    if getattr(f, "name", None) == name:
                        _chinese_font = name
                        break
                if _chinese_font:
                    break
        except Exception:
            pass
        if _chinese_font:
            plt.rcParams["font.sans-serif"] = [_chinese_font, "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False

        def _plot_total(consistency_by_map, filename: str, title: str):
            if not consistency_by_map:
                return
            labels = [m for (m, _, _) in consistency_by_map]
            prac = [(p if p is not None else 0.0) for (_, p, _) in consistency_by_map]
            traj = [(t if t is not None else 0.0) for (_, _, t) in consistency_by_map]
            x = list(range(len(labels)))
            width = 0.35
            fig_h = 5 if len(labels) > 10 else 4
            fig, ax = plt.subplots(figsize=(max(6, len(labels) * 1.2), fig_h))
            ax.bar([i - width / 2 for i in x], prac, width, label="Practice")
            ax.bar([i + width / 2 for i in x], traj, width, label="Trajectory")
            ax.set_ylim(0, 1.0)
            ax.set_ylabel("Consistency rate")
            ax.set_title(title)
            ax.set_xticks(x)
            ax.set_xticklabels(labels, rotation=30, ha="right")
            ax.legend()
            fig.tight_layout()
            fig.savefig(os.path.join(output_dir, filename))
            plt.close(fig)

        def _plot_phase(phase_consistency_by_map, filename: str, title: str):
            if not phase_consistency_by_map:
                return
            labels = [m for (m, _) in phase_consistency_by_map]
            learning = [((d or {}).get("learning") or 0.0) for (_, d) in phase_consistency_by_map]
            testing = [((d or {}).get("test") or 0.0) for (_, d) in phase_consistency_by_map]
            x = list(range(len(labels)))
            width = 0.35
            fig_h = 5 if len(labels) > 10 else 4
            fig, ax = plt.subplots(figsize=(max(6, len(labels) * 1.2), fig_h))
            ax.bar([i - width / 2 for i in x], learning, width, label="Learning")
            ax.bar([i + width / 2 for i in x], testing, width, label="Test")
            ax.set_ylim(0, 1.0)
            ax.set_ylabel("Consistency rate")
            ax.set_title(title)
            ax.set_xticks(x)
            ax.set_xticklabels(labels, rotation=30, ha="right")
            ax.legend()
            fig.tight_layout()
            fig.savefig(os.path.join(output_dir, filename))
            plt.close(fig)

        # QMDP 图（保持原文件名，兼容旧用法）
        if args.baseline in ("qmdp", "both"):
            _plot_total(qmdp_consistency_by_map, "consistency_by_map.svg", "QMDP policy consistency by map")
            _plot_phase(qmdp_phase_consistency_by_map, "phase_consistency_by_map.svg", "QMDP practice consistency by phase (learning/test)")

        # A* 图（单独文件名，避免覆盖）
        if args.baseline in ("astar", "both"):
            _plot_total(astar_consistency_by_map, "consistency_by_map_astar.svg", "A* shortest-path consistency by map")
            _plot_phase(astar_phase_consistency_by_map, "phase_consistency_by_map_astar.svg", "A* practice consistency by phase (learning/test)")
    except Exception as e:
        print(f"[viz] 规范策略可视化失败：{e}")


if __name__ == "__main__":
    main()
