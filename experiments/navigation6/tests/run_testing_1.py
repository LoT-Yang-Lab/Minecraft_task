#!/usr/bin/env python3
"""Generate and inspect the five-session Navigation6 schedule.

This script is intentionally lightweight so researchers can quickly verify
trial orders (navigation-first vs crafting-first), export them to JSON,
and cross-check the category quotas before wiring them into other
components or running agents.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Iterable, List

import sys

_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parents[3]
_PROJECT_ROOT_STR = str(_PROJECT_ROOT)
if _PROJECT_ROOT_STR not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT_STR)

from experiments.navigation6.tests.trial_schedule import (
    build_session_schedule,
    save_schedule,
)


def _summarize_session(session: dict) -> str:
    nav_trials = session["navigation_trials"]
    craft_trials = session["crafting_trials"]
    nav_counter = Counter(trial["category"] for trial in nav_trials)
    summary = [
        f"Session {session['session']} ({session['domain']}): seed={session['seed']}",
        f"  navigation trials: {len(nav_trials)} -> {dict(nav_counter)}",
        f"  crafting placeholders: {len(craft_trials)}",
    ]
    if session["domain"] == "mixed":
        order_preview = [item["type"][0].upper() for item in session["combined_order"][:12]]
        summary.append(f"  mixed order preview: {' '.join(order_preview)} ...")
    return "\n".join(summary)


def _validate_orders(orders: Iterable[str]) -> List[str]:
    normalized = []
    for order in orders:
        if order not in {"navigation-first", "crafting-first"}:
            raise ValueError("order must be 'navigation-first' or 'crafting-first'")
        normalized.append(order)
    return normalized


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Navigation6 session schedules")
    parser.add_argument(
        "--order",
        choices=["navigation-first", "crafting-first"],
        nargs="*",
        default=["navigation-first", "crafting-first"],
        help="Which high-level order(s) to generate (default: both)",
    )
    parser.add_argument(
        "--output-dir",
        default=Path(__file__).resolve().parent / "generated_schedules",
        type=Path,
        help="Directory to store schedule JSON files",
    )
    args = parser.parse_args()

    orders = _validate_orders(args.order)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    for order in orders:
        schedule = build_session_schedule(order)
        output_path = args.output_dir / f"{order.replace('-', '_')}_schedule.json"
        save_schedule(schedule, output_path)
        print(f"[OK] Saved {order} schedule to {output_path}")
        for session in schedule["sessions"]:
            print(_summarize_session(session))
        print("-")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
