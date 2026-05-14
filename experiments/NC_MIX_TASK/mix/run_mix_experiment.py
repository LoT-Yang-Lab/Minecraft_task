from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import pygame

from crafting.src.bottle_images import BottleImageCache, collect_bottle_asset_dirs
from crafting.src.main_crafting import WINDOW_H, WINDOW_W
from crafting.src.map_select_crafting import resolve_transition_map_cli_path
from crafting.src.participant_id_crafting import run_participant_id_screen
from crafting.src.rules_io_crafting import load_rule_data_with_transition_map
from crafting.src.session_runner import run_crafting_session
from crafting.src.stone_images import StoneImageCache, collect_stone_asset_dirs
from navigation.session_runner import run_navigation_session

from .mix_session_guidance import run_mix_session_guidance_screen
from .preflight_equivalence import run_equivalence_preflight
from .schedule import build_session_schedule, save_schedule


def _mix_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="NC_MIX_TASK 混合实验（同进程/同窗口）")
    p.add_argument("--order", choices=["navigation-first", "crafting-first"], default="navigation-first")
    p.add_argument("--start-session", type=int, default=1)
    p.add_argument("--max-sessions", type=int, default=None)
    p.add_argument("--participant_id", "-p", type=str, default=None)
    p.add_argument("--nav-map", type=str, default="map_1774095558.json")
    p.add_argument("--transition-map", type=str, default="data/maps/builtin_map_a.json")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def _resolve_nav_map(root: Path, arg: str) -> Path:
    p = Path(arg)
    if p.is_absolute() and p.is_file():
        return p
    candidate = root / "navigation" / "assets" / "maps" / arg
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(f"找不到导航地图: {arg}")


def _collect_trials(session: Dict[str, Any], trial_type: str) -> List[Dict[str, Any]]:
    combined = session.get("combined_order") or []
    if combined:
        return [item["trial"] for item in combined if item["type"] == trial_type]
    key = "navigation_trials" if trial_type == "navigation" else "crafting_trials"
    return list(session.get(key, []))


def main() -> int:
    args = _parse_args()
    root = _mix_root()
    schedule = build_session_schedule(args.order)
    data_root = root / "data"
    nav_data_root = data_root / "navigation"
    craft_data_root = data_root / "crafting"
    mix_data_root = data_root / "mix"
    for p in (data_root, nav_data_root, craft_data_root, mix_data_root):
        p.mkdir(parents=True, exist_ok=True)
    save_schedule(schedule, data_root / "full_schedule.json")

    nav_map = _resolve_nav_map(root, args.nav_map)
    transition_map = resolve_transition_map_cli_path(root / "crafting", args.transition_map)
    run_equivalence_preflight(
        navigation_map_path=str(nav_map),
        transition_map_path=str(transition_map),
        report_path=str(mix_data_root / "preflight_report.json"),
    )

    if args.dry_run:
        print("[DRY-RUN] schedule 与地图预检已完成。")
        return 0

    start_index = max(0, args.start_session - 1)
    selected_sessions = schedule["sessions"][start_index:]
    if args.max_sessions is not None:
        selected_sessions = selected_sessions[: max(0, args.max_sessions)]
    if not selected_sessions:
        raise ValueError("start-session 超出范围")

    pygame.init()
    # 禁用 IME 文本输入模式，确保中文输入法下 Q/W/E/A/D 等字母键
    # 能正常产生 KEYDOWN 事件，而不是被输入法拦截
    pygame.key.stop_text_input()
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    clock = pygame.time.Clock()

    pid = (args.participant_id or "").strip()
    if not pid:
        pygame.display.set_caption("NC Mix — 被试编号")
        pid = run_participant_id_screen(screen, clock) or ""
        if not pid:
            pygame.quit()
            return 1
    pid = pid.strip() or "unknown"

    rules_path = str(root / "crafting" / "data" / "rules" / "crafting_rules_v1.json")
    rules = load_rule_data_with_transition_map(rules_path, transition_map)
    stone_cache = StoneImageCache(collect_stone_asset_dirs(root / "crafting"))
    bottle_cache = BottleImageCache(collect_bottle_asset_dirs(root / "crafting"))

    for session in selected_sessions:
        sn = int(session["session"])
        domain = str(session["domain"])
        session_seed = int(session["seed"])
        if domain == "navigation":
            guidance_kind = "navigation"
        elif domain == "crafting":
            guidance_kind = "crafting"
        else:
            guidance_kind = "mixed"
        combined = list(session.get("combined_order") or [])
        nav_trials = _collect_trials(session, "navigation")
        craft_trials = _collect_trials(session, "crafting")
        if domain == "navigation":
            trial_count_hint = len(nav_trials) if nav_trials else 0
        elif domain == "crafting":
            trial_count_hint = len(craft_trials) if craft_trials else 0
        else:
            trial_count_hint = len(combined) if combined else 0

        if not run_mix_session_guidance_screen(
            screen,
            clock,
            session_num=sn,
            domain=guidance_kind,
            total_trials_in_session=trial_count_hint or None,
        ):
            pygame.quit()
            return 1
        mix_session_dir = mix_data_root / f"session_{sn:02d}"
        mix_session_dir.mkdir(parents=True, exist_ok=True)
        outputs: List[Dict[str, Any]] = []
        session_interrupted = False

        if domain == "navigation":
            out = run_navigation_session(
                screen=screen,
                clock=clock,
                participant_id=pid,
                map_path=str(nav_map),
                nav_trials=nav_trials,
                session_num=sn,
                session_seed=session_seed,
                order=args.order,
                domain=domain,
                output_dir=nav_data_root / f"session_{sn:02d}",
                crafting_trials=craft_trials,
                combined_order=combined,
            )
            outputs.append({"type": "navigation", "output": out})
            session_interrupted = bool(out.get("interrupted", False))
        elif domain == "crafting":
            out = run_crafting_session(
                screen=screen,
                clock=clock,
                pid=pid,
                rules=rules,
                image_cache=stone_cache,
                bottle_cache=bottle_cache,
                craft_trials=craft_trials,
                session_num=sn,
                session_seed=session_seed,
                output_dir=craft_data_root / f"session_{sn:02d}",
                order=args.order,
                domain=domain,
                navigation_trials=nav_trials,
                combined_order=combined,
            )
            outputs.append({"type": "crafting", "output": out})
            session_interrupted = bool(out.get("interrupted", False))
        else:
            # mixed session: run full 24-task combined_order sequence
            total = len(combined)
            nav_idx = 0
            craft_idx = 0
            for idx, item in enumerate(combined, start=1):
                phase = item["type"]
                trial = item["trial"]
                if phase == "navigation":
                    nav_idx += 1
                    out = run_navigation_session(
                        screen=screen,
                        clock=clock,
                        participant_id=pid,
                        map_path=str(nav_map),
                        nav_trials=[trial],
                        session_num=sn,
                        session_seed=session_seed,
                        order=args.order,
                        domain=domain,
                        output_dir=nav_data_root / f"session_{sn:02d}" / f"trial_{nav_idx:02d}",
                        crafting_trials=craft_trials,
                        combined_order=combined,
                        display_trial_progress=(idx, total),
                    )
                    outputs.append({"type": "navigation", "index": nav_idx, "progress": [idx, total], "output": out})
                    if bool(out.get("interrupted", False)):
                        session_interrupted = True
                        break
                else:
                    craft_idx += 1
                    out = run_crafting_session(
                        screen=screen,
                        clock=clock,
                        pid=pid,
                        rules=rules,
                        image_cache=stone_cache,
                        bottle_cache=bottle_cache,
                        craft_trials=[trial],
                        session_num=sn,
                        session_seed=session_seed,
                        output_dir=craft_data_root / f"session_{sn:02d}" / f"trial_{craft_idx:02d}",
                        order=args.order,
                        domain=domain,
                        navigation_trials=nav_trials,
                        combined_order=combined,
                        display_trial_progress=(idx, total),
                    )
                    outputs.append({"type": "crafting", "index": craft_idx, "progress": [idx, total], "output": out})
                    if bool(out.get("interrupted", False)):
                        session_interrupted = True
                        break

        with (mix_session_dir / "session_metadata.json").open("w", encoding="utf-8") as fh:
            json.dump(
                {
                    "order": args.order,
                    "session": sn,
                    "seed": session_seed,
                    "domain": domain,
                    "navigation_trials": nav_trials,
                    "crafting_trials": craft_trials,
                    "combined_order": combined,
                    "outputs": outputs,
                    "session_interrupted": session_interrupted,
                },
                fh,
                ensure_ascii=False,
                indent=2,
            )

        if session_interrupted:
            print(f"[INFO] Session {sn} 被用户中断，自动进入下一 session。")

    pygame.quit()
    print(f"Mix 运行完成。输出目录：{data_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
