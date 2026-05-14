"""proposal5_trial_schedule must match Navigation6 golden export."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.proposal5_trial_schedule import build_session_schedule


def _golden_navigation_first_path() -> Path:
    crafting = Path(__file__).resolve().parents[1]
    experiments = crafting.parent
    return (
        experiments
        / "navigation6"
        / "tests"
        / "generated_schedules"
        / "navigation_first_schedule.json"
    )


def test_build_session_schedule_matches_navigation_first_golden() -> None:
    golden_path = _golden_navigation_first_path()
    if not golden_path.is_file():
        pytest.skip(f"Golden schedule not found: {golden_path}")

    with golden_path.open(encoding="utf-8") as f:
        expected = json.load(f)

    got = build_session_schedule("navigation-first")
    assert got == expected


def test_crafting_first_determinism() -> None:
    a = build_session_schedule("crafting-first")
    b = build_session_schedule("crafting-first")
    assert a == b
    assert a["order"] == "crafting-first"
    assert len(a["sessions"]) == 5
