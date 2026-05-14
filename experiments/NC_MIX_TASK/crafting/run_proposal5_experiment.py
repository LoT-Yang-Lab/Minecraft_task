#!/usr/bin/env python3
"""
Crafting（九石阵）Proposal-5 五 session 运行器（日程与 Navigation6 `run_experiment_new.py` 同源）。

仅执行 combined_order 中 type==crafting 的试次；navigation 保留在元数据中但不运行（与导航端跳过 crafting 对称）。
须使用与实验设计一致的转化地图（推荐 `--transition_map data/maps/builtin_map_a.json`）。
单机正式入口另支持通过 `linked_navigation_map_id` / `--trials` 加载与 Navigation6 相同的 trial_sequences；Proposal-5 仍只用日程内 crafting 试次。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

_this_dir = Path(__file__).resolve().parent
if str(_this_dir) not in sys.path:
    sys.path.insert(0, str(_this_dir))

import pygame

from src.config_io_crafting import TrialSpec, trial_list_from_specs
from src.game_crafting import GameCrafting
from src.main_crafting import (
    WINDOW_H,
    WINDOW_W,
    run_crafting_game_loop,
    run_experiment_guidance_screen,
)
from src.map_select_crafting import resolve_transition_map_cli_path, run_transition_map_selection
from src.participant_id_crafting import run_participant_id_screen
from src.proposal5_trial_schedule import build_session_schedule, save_schedule
from src.proposal5_validation import validate_crafting_trials_on_map
from src.recorder import RLDataRecorder
from src.rules_io_crafting import load_rule_data_with_transition_map
from src.bottle_images import BottleImageCache, collect_bottle_asset_dirs
from src.stone_images import StoneImageCache, collect_stone_asset_dirs


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Crafting Proposal-5 五 session（仅 crafting 试次）")
    p.add_argument("--order", choices=["navigation-first", "crafting-first"], default="navigation-first")
    p.add_argument("--start-session", type=int, default=1, help="从第几 session 开始（1–5）")
    p.add_argument("--schedule-output", type=Path, default=None, help="导出 schedule JSON 的路径")
    p.add_argument("--pause-between-sessions", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="只生成并校验 schedule，不启动 pygame")
    p.add_argument("--max-sessions", type=int, default=None)
    p.add_argument(
        "--participant_id",
        "-p",
        type=str,
        default=None,
        help="被试编号；不指定则在首 session 前弹窗输入",
    )
    p.add_argument("--rules", type=str, default=None, help="规则 JSON（默认 data/rules/crafting_rules_v1.json）")
    p.add_argument(
        "--transition_map",
        type=str,
        default=None,
        help="转化地图 JSON；不指定则仅在首阶段弹地图选择",
    )
    p.add_argument(
        "--experiment-output-dir",
        type=str,
        default=None,
        help="本被试输出根目录（默认 rl_data/proposal5_<order>_<timestamp>）",
    )
    return p.parse_args()


def _prompt(message: str) -> None:
    try:
        input(message)
    except EOFError:
        print("[WARN] 无标准输入，跳过终端暂停。")


def _interactive_terminal_available() -> bool:
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except Exception:
        return False


def _crafting_trials_in_runtime_order(session: Dict[str, Any]) -> List[Dict[str, Any]]:
    combined = session.get("combined_order") or []
    if combined:
        return [item["trial"] for item in combined if item["type"] == "crafting"]
    return list(session.get("crafting_trials", []))


def _craft_trials_to_trial_specs(
    craft_trials: Sequence[Dict[str, Any]],
    session_num: int,
    session_seed: int,
) -> List[TrialSpec]:
    specs: List[TrialSpec] = []
    for t in craft_trials:
        s = int(t["start"])
        g = int(t["goal"])
        bi = int(t.get("block_index", t["index"]))
        pair_id = str(t["pair_id"])
        tid = str(t.get("task_id") or f"S{session_num}_b{bi}_{pair_id}")
        stone_s = f"stone_{s:02d}"
        stone_g = f"stone_{g:02d}"
        craft_idx = int(t.get("index", bi))
        seed = session_seed * 1000 + craft_idx
        meta: Dict[str, Any] = {
            "session": session_num,
            "block_index": bi,
            "craft_index": craft_idx,
            "pair_id": pair_id,
            "category": t["category"],
            "nav_start": s,
            "nav_goal": g,
            "d_grid": t["d_grid"],
            "d_loop": t["d_loop"],
            "recipe": t.get("recipe"),
            "task_id": tid,
        }
        specs.append(
            TrialSpec(
                trial_id=tid,
                order_count=1,
                seed=seed,
                raws=[stone_s],
                targets=[stone_g],
                strict_order_targets=True,
                min_distance=2,
                schedule_meta=meta,
            )
        )
    return specs


def _make_experiment_output_dir(order: str, override: str | None) -> Path:
    if override:
        out = Path(override)
        out.mkdir(parents=True, exist_ok=True)
        return out
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    root = _this_dir / "rl_data" / f"proposal5_{order.replace('-', '_')}_{stamp}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _load_caches(root: Path) -> Tuple[StoneImageCache, BottleImageCache]:
    stone_dirs = collect_stone_asset_dirs(root)
    bottle_dirs = collect_bottle_asset_dirs(root)
    return StoneImageCache(stone_dirs), BottleImageCache(bottle_dirs)


def main() -> int:
    args = _parse_args()
    root = _this_dir
    default_rules = str(root / "data" / "rules" / "crafting_rules_v1.json")
    rules_path = args.rules or default_rules

    schedule = build_session_schedule(args.order)
    if args.schedule_output:
        save_schedule(schedule, args.schedule_output)
        print(f"[INFO] Schedule 已写入 {args.schedule_output}")

    if args.dry_run:
        print("[INFO] dry-run：schedule 已校验，未启动 pygame。")
        return 0

    start_index = max(0, args.start_session - 1)
    selected_sessions = schedule["sessions"][start_index:]
    if args.max_sessions is not None:
        selected_sessions = selected_sessions[: max(0, args.max_sessions)]
    if not selected_sessions:
        raise ValueError("start-session 超出范围")

    can_pause = args.pause_between_sessions and _interactive_terminal_available()
    if args.pause_between_sessions and not can_pause:
        print("[WARN] 无法终端暂停，已忽略 --pause-between-sessions。")

    experiment_dir = _make_experiment_output_dir(args.order, args.experiment_output_dir)
    print(f"[INFO] 输出目录：{experiment_dir.resolve()}")
    auto_schedule = experiment_dir / "full_schedule.json"
    save_schedule(schedule, auto_schedule)
    print(f"[INFO] 已保存 full_schedule.json")

    pygame.init()
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    clock = pygame.time.Clock()

    pid = (args.participant_id or "").strip()
    if not pid:
        pygame.display.set_caption("Crafting Proposal-5 — 被试编号")
        pid = run_participant_id_screen(screen, clock) or ""
        if not pid:
            pygame.quit()
            return 1
    pid = str(pid).strip() or "unknown"

    transition_map_path: str | None = None
    if args.transition_map:
        try:
            transition_map_path = resolve_transition_map_cli_path(root, args.transition_map)
        except FileNotFoundError as e:
            print(e)
            pygame.quit()
            return 1
    else:
        pygame.display.set_caption("Crafting Proposal-5 — 选择地图")
        picked = run_transition_map_selection(screen, clock, root)
        if not picked:
            pygame.quit()
            return 1
        transition_map_path = picked

    assert transition_map_path is not None
    map_label = Path(transition_map_path).stem
    pygame.display.set_caption("Crafting Proposal-5 — 说明")
    if not run_experiment_guidance_screen(screen, clock, map_label=map_label):
        pygame.quit()
        return 0

    rules = load_rule_data_with_transition_map(rules_path, transition_map_path)
    img_cache, bottle_cache = _load_caches(root)

    for session in selected_sessions:
        craft_trials = _crafting_trials_in_runtime_order(session)
        sn = int(session["session"])
        if not craft_trials:
            print(f"Session {sn} 无 crafting 试次（纯导航 session），跳过。")
            if can_pause:
                _prompt("按 Enter 继续…")
            continue

        try:
            validate_crafting_trials_on_map(rules, craft_trials, min_distance=2)
        except ValueError as e:
            print(f"[FATAL] 预检失败：{e}")
            pygame.quit()
            return 1

        trial_specs = _craft_trials_to_trial_specs(craft_trials, sn, int(session["seed"]))
        trial_data = trial_list_from_specs(trial_specs, source_path=f"<proposal5_session_{sn}>")

        session_dir = experiment_dir / f"session_{sn:02d}"
        session_dir.mkdir(parents=True, exist_ok=True)
        meta_path = session_dir / "session_metadata.json"
        with meta_path.open("w", encoding="utf-8") as fh:
            json.dump(
                {
                    "order": args.order,
                    "session": sn,
                    "seed": session["seed"],
                    "domain": session["domain"],
                    "crafting_trials": craft_trials,
                    "navigation_trials": session.get("navigation_trials", []),
                    "combined_order": session.get("combined_order"),
                    "notes": "Navigation trials not executed in Crafting runner; schedule preserved for analysis.",
                },
                fh,
                ensure_ascii=False,
                indent=2,
            )

        recorder = RLDataRecorder(
            participant_id=pid,
            task_type="Crafting_Proposal5",
            output_root=str(session_dir),
        )
        game = GameCrafting(
            recorder=recorder,
            rules=rules,
            trial_data=trial_data,
            finite_trials=True,
        )

        pygame.display.set_caption(f"Crafting Proposal-5 — Session {sn}/5")
        print(f"启动 Session {sn}，共 {len(craft_trials)} 个 crafting 试次。")
        if can_pause:
            _prompt("按 Enter 开始该 session …")

        run_crafting_game_loop(
            screen,
            clock,
            game,
            img_cache,
            bottle_cache,
            header_title="Crafting Proposal-5（九石阵）",
            meta_line=None,
            session_meta_prefix=f"Session {sn}/5",
            meta_line2="完成后自动进入下一 session（若仍有）；Esc 退出保存当前进度",
        )

        try:
            recorder.save_to_file()
        except Exception as ex:
            print(f"[WARN] 保存数据失败：{ex}")

        print(f"Session {sn} 结束。")
        if can_pause:
            _prompt("按 Enter 继续下一 session …")

    pygame.quit()
    print(f"全部 session 已完成。数据目录：{experiment_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
