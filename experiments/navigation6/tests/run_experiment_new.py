#!/usr/bin/env python3
"""Run the full five-session proposal-5 experiment for a human participant.

This file is the participant-facing runner for the new proposal-driven
five-session design. It does **not** run an agent. Instead, it reuses
the newer pygame transportation navigation UI implemented in
``experiments.navigation6.main2`` and injects the planned start-goal
sequence session by session.

Behavior:
1. Build the 5-session schedule from ``trial_schedule.py``.
2. Execute only navigation trials.
3. Keep crafting trials as placeholders in metadata, but skip them.
4. Use the same Navigation6 transportation task logic and data log style
   as ``main2()``, while preserving session metadata for later analysis.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parents[3]
_PROJECT_ROOT_STR = str(_PROJECT_ROOT)
if _PROJECT_ROOT_STR not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT_STR)

from experiments.navigation6.main2 import main as nav_main2
from experiments.navigation6.app.paths import trajectory_raw_dir
from experiments.navigation6.tests.trial_schedule import build_session_schedule, save_schedule


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the preplanned five-session Navigation6 transportation experiment"
    )
    parser.add_argument("--order", choices=["navigation-first", "crafting-first"], default="navigation-first")
    parser.add_argument(
        "--start-session",
        type=int,
        default=1,
        help="Resume from a given session number (1-5)",
    )
    parser.add_argument(
        "--schedule-output",
        type=Path,
        default=None,
        help="Optional JSON export path for the generated schedule",
    )
    parser.add_argument(
        "--pause-between-sessions",
        action="store_true",
        help="Pause in the terminal between sessions",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only validate and print the five-session schedule without launching pygame",
    )
    parser.add_argument(
        "--max-sessions",
        type=int,
        default=None,
        help="Optional upper bound on how many sessions to iterate through from start-session",
    )
    return parser.parse_args()


def _prompt(message: str) -> None:
    try:
        input(message)
    except EOFError:
        print("[WARN] 当前运行环境无标准输入，自动跳过终端暂停。")


def _interactive_terminal_available() -> bool:
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except Exception:
        return False


def _navigation_trials_in_runtime_order(session: Dict[str, object]) -> List[Dict[str, object]]:
    combined = session.get("combined_order") or []
    if combined:
        return [item["trial"] for item in combined if item["type"] == "navigation"]
    return list(session.get("navigation_trials", []))


def _crafting_trials_in_runtime_order(session: Dict[str, object]) -> List[Dict[str, object]]:
    combined = session.get("combined_order") or []
    if combined:
        return [item["trial"] for item in combined if item["type"] == "crafting"]
    return list(session.get("crafting_trials", []))


def _pairs_from_trials(trials: Sequence[Dict[str, object]]) -> List[Tuple[int, int]]:
    return [(int(trial["start"]), int(trial["goal"])) for trial in trials]


def _summarize_quota(trials: Sequence[Dict[str, object]]) -> str:
    counts = {"grid": 0, "loop": 0, "tie": 0}
    for trial in trials:
        counts[str(trial["category"])] = counts.get(str(trial["category"]), 0) + 1
    return f"grid={counts.get('grid', 0)}, loop={counts.get('loop', 0)}, tie={counts.get('tie', 0)}"


def _print_session_banner(session: Dict[str, object], nav_trials: Sequence[Dict[str, object]]) -> None:
    print("=" * 88)
    print(
        f"Session {session['session']} | domain={session['domain']} | seed={session['seed']} | "
        f"navigation trials={len(nav_trials)}"
    )
    if nav_trials:
        print(f"Quota summary: {_summarize_quota(nav_trials)}")
    if session["domain"] == "mixed":
        combined = session.get("combined_order") or []
        preview = " ".join(item["type"][0].upper() for item in combined[:16])
        print(f"Mixed order preview (N/C): {preview}")


def _make_experiment_output_dir(order: str) -> str:
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    dirname = f"proposal5_{order.replace('-', '_')}_{stamp}"
    out_dir = Path(trajectory_raw_dir()) / dirname
    out_dir.mkdir(parents=True, exist_ok=True)
    return str(out_dir)


def main() -> int:
    args = _parse_args()
    schedule = build_session_schedule(args.order)
    if args.schedule_output:
        save_schedule(schedule, args.schedule_output)
        print(f"[INFO] Schedule saved to {args.schedule_output}")

    print("Navigation6 proposal-5 五个 session 实验运行器")
    print("说明：仅执行导航试次；合成任务保留在 session 设计中，但在运行时跳过。")
    print("按键：公交 Q/E ｜ 地铁 A/D ｜ 环线 W")
    if args.dry_run:
        print("[INFO] 当前为 dry-run：只检查并打印 schedule，不启动 pygame。")

    start_index = max(0, args.start_session - 1)
    selected_sessions = schedule["sessions"][start_index:]
    if args.max_sessions is not None:
        selected_sessions = selected_sessions[: max(0, args.max_sessions)]
    if not selected_sessions:
        raise ValueError("start-session 超出范围，没有可运行的 session")

    can_pause = args.pause_between_sessions and _interactive_terminal_available()
    if args.pause_between_sessions and not can_pause:
        print("[WARN] --pause-between-sessions 已指定，但当前环境不是交互式终端，将自动忽略暂停。")

    experiment_output_dir = None if args.dry_run else _make_experiment_output_dir(args.order)
    if experiment_output_dir:
        print(f"[INFO] 本次多 session 实验输出目录：{experiment_output_dir}")
        auto_schedule_path = Path(experiment_output_dir) / "full_schedule.json"
        save_schedule(schedule, auto_schedule_path)
        print(f"[INFO] 已自动保存本次完整五阶段 schedule：{auto_schedule_path}")

    for session in selected_sessions:
        nav_trials = _navigation_trials_in_runtime_order(session)
        craft_trials = _crafting_trials_in_runtime_order(session)
        _print_session_banner(session, nav_trials)
        if craft_trials:
            print(f"Crafting placeholders skipped in this session: {len(craft_trials)}")

        if not nav_trials:
            print("本 session 无导航试次，直接跳过。")
            if can_pause:
                _prompt("按 Enter 进入下一个 session ... ")
            continue

        if args.dry_run:
            preview_pairs = _pairs_from_trials(nav_trials[: min(3, len(nav_trials))])
            print(f"[DRY-RUN] Session {session['session']} preview pairs: {preview_pairs}")
            continue

        session_metadata = {
            "order": args.order,
            "session": session["session"],
            "seed": session["seed"],
            "domain": session["domain"],
            "navigation_trials": nav_trials,
            "crafting_placeholders": craft_trials,
            "notes": "Crafting trials skipped; only navigation trials executed in Navigation6 main2 UI.",
        }

        print(
            f"即将启动 Session {session['session']} 的 pygame 测试窗口。"
            "完成该 session 后关闭/退出窗口，将自动继续后续 session。"
        )
        if can_pause:
            _prompt("按 Enter 启动该 session ... ")

        output_path = nav_main2(
            test_trials_override=_pairs_from_trials(nav_trials),
            session_metadata=session_metadata,
            experiment_output_dir=experiment_output_dir,
            participant_id="Navigation6_User",
        )

        if output_path:
            print(f"[INFO] Session {session['session']} 保存完成：{output_path}")

        print(f"Session {session['session']} 完成。")
        if can_pause:
            _prompt("按 Enter 继续下一个 session ... ")

    if experiment_output_dir:
        print(f"全部可运行的 navigation session 已完成。数据已写入：{experiment_output_dir}")
    else:
        print("全部可运行的 navigation session 已完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
