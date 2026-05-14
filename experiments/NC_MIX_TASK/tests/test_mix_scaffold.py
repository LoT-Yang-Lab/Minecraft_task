from __future__ import annotations

from pathlib import Path

from mix.preflight_equivalence import run_equivalence_preflight
from mix.schedule import build_session_schedule


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_mix_schedule_has_five_sessions() -> None:
    sched = build_session_schedule("navigation-first")
    assert "sessions" in sched
    assert len(sched["sessions"]) == 5


def test_preflight_default_maps_pass(tmp_path: Path) -> None:
    root = _project_root()
    report = tmp_path / "preflight_report.json"
    out = run_equivalence_preflight(
        navigation_map_path=str(root / "navigation" / "assets" / "maps" / "map_1774095558.json"),
        transition_map_path=str(root / "crafting" / "data" / "maps" / "builtin_map_a.json"),
        report_path=str(report),
    )
    assert out["ok"] is True
    assert report.is_file()


def test_top_level_entrypoints_exist() -> None:
    root = _project_root()
    expected = [
        "practice_navigation.py",
        "practice_crafting.py",
        "main_navigation.py",
        "main_crafting.py",
        "editor_navigation.py",
        "editor_crafting.py",
        "run_mix.py",
    ]
    for name in expected:
        assert (root / name).is_file(), name
