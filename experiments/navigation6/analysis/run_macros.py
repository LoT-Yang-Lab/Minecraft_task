"""
宏提取线入口：加载轨迹 → 挖掘频繁子序列 → 建宏目录 → 统计每被试/每地图宏使用强度 → 写出 output/macros。
从项目根运行: python -m experiments.navigation6.analysis.run_macros --maps-dir ... --trajectory-dir ...
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
    parser = argparse.ArgumentParser(description="Navigation6 宏提取：轨迹 → 频繁子序列 → 宏目录与使用强度")
    parser.add_argument("--maps-dir", default=None, help="地图目录")
    parser.add_argument("--trajectory-dir", default=None, help="rl_data 根目录（含多子目录的 game_log_*.csv）")
    parser.add_argument("--practice-dir", default=None, help="可选：练习目录，用于从练习序列挖宏")
    parser.add_argument("--map-id", default=None, help="仅处理该 map_id")
    parser.add_argument("--n-gram", type=int, default=3, help="n-gram 长度")
    parser.add_argument("--min-support", type=int, default=2, help="最小支持度")
    parser.add_argument("--output-dir", default=None, help="输出目录，默认 analysis/output/macros")
    args = parser.parse_args()

    # 默认输出到 experiments/navigation6/outputs/analysis/macros
    output_dir = args.output_dir or os.path.join(_nav5_root, "outputs", "analysis", "macros")
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    # 默认地图目录：assets/maps（兼容旧 maps/）
    if args.maps_dir:
        maps_dir = args.maps_dir
    else:
        from experiments.navigation6.app.paths import maps_dir as _maps_dir
        maps_dir = _maps_dir()

    from .data.load_trajectory import load_trajectory_dir, DEFAULT_MAP_STRUCTURE_TO_ID
    from .data.load_practice import load_practice_dir
    from .macros import extract_frequent_sequences, build_macro_catalog, compute_macro_usage

    trajectory_rows = []
    # 默认轨迹目录：data/raw/trajectory（若不存在则 load_trajectory_dir 回退项目根 rl_data）
    trajectory_dir = args.trajectory_dir or os.path.join(_nav5_root, "data", "raw", "trajectory")
    if Path(trajectory_dir).is_dir():
        trajectory_rows = load_trajectory_dir(trajectory_dir, maps_dir=maps_dir)
    if args.map_id:
        trajectory_rows = [r for r in trajectory_rows if r.get("map_id") == args.map_id]

    practice_records = []
    # 默认练习目录：data/raw/practice（若不存在则 load_practice_dir 回退旧 practice_data）
    practice_dir = args.practice_dir or os.path.join(_nav5_root, "data", "raw", "practice")
    if Path(practice_dir).is_dir():
        practice_records = load_practice_dir(practice_dir)
    if args.map_id and practice_records:
        practice_records = [r for r in practice_records if r.get("map_id") == args.map_id]

    # 若仅有练习无轨迹，用练习记录构造带 s/s_next 的“轨迹”行供 usage 统计
    if not trajectory_rows and practice_records:
        for i, r in enumerate(practice_records):
            trajectory_rows.append({
                "participant_id": r.get("participant_id", ""),
                "map_id": r.get("map_id", ""),
                "episode": 0,
                "step": r.get("trial_index", i),
                "s": r.get("current_code", 0),
                "s_next": r.get("participant_choice", 0),
            })

    # 按 (participant_id, map_id) 分段，每段转为 (s, s_next) 序列
    from collections import defaultdict
    segments = defaultdict(list)
    for r in trajectory_rows:
        key = (r.get("participant_id", ""), r.get("map_id", ""))
        segments[key].append(r)
    for k in segments:
        segments[k].sort(key=lambda x: (x.get("episode", 0), x.get("step", 0)))
    sequences = []
    for rows in segments.values():
        seq = [(r.get("s"), r.get("s_next")) for r in rows if r.get("s") and r.get("s_next")]
        if len(seq) >= 2:
            sequences.append(seq)

    if practice_records:
        by_key = defaultdict(list)
        for r in practice_records:
            by_key[(r.get("participant_id"), r.get("map_id"))].append(r)
        for rows in by_key.values():
            rows.sort(key=lambda x: (x.get("trial_index", 0),))
            seq = [(r.get("current_code"), r.get("participant_choice")) for r in rows if r.get("current_code") and r.get("participant_choice")]
            if len(seq) >= 2:
                sequences.append(seq)

    if not sequences:
        print("无轨迹或练习序列，退出")
        return

    frequent = extract_frequent_sequences(sequences, min_support=args.min_support, max_length=10, min_length=2)
    catalog = build_macro_catalog(frequent, min_support=args.min_support)
    usage = compute_macro_usage(trajectory_rows, catalog)

    map_id_out = args.map_id or "all"
    catalog_path = os.path.join(output_dir, f"{map_id_out}_macros.json")
    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    print(f"宏目录已写入 {catalog_path} (共 {len(catalog)} 条)")

    usage_path = os.path.join(output_dir, f"{map_id_out}_macro_usage.json")
    with open(usage_path, "w", encoding="utf-8") as f:
        json.dump(usage, f, ensure_ascii=False, indent=2)
    print(f"宏使用已写入 {usage_path}")


if __name__ == "__main__":
    main()
