from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import pygame

from .main2 import main as run_navigation_main2


def pairs_from_trials(trials: Sequence[Dict[str, Any]]) -> List[Tuple[int, int]]:
    return [(int(trial["start"]), int(trial["goal"])) for trial in trials]


def run_navigation_session(
    *,
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    participant_id: str,
    map_path: str,
    nav_trials: Sequence[Dict[str, Any]],
    session_num: int,
    session_seed: int,
    order: str,
    domain: str,
    output_dir: Path,
    crafting_trials: Sequence[Dict[str, Any]] | None = None,
    combined_order: Sequence[Dict[str, Any]] | None = None,
    display_trial_progress: Tuple[int, int] | None = None,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "order": order,
        "session": session_num,
        "seed": session_seed,
        "domain": domain,
        "navigation_trials": list(nav_trials),
        "crafting_trials": list(crafting_trials or []),
        "combined_order": list(combined_order or []),
        "notes": "Run by NC_MIX_TASK orchestrator",
        "mix_ui": {
            "title": "NC Mix · 导航",
            "meta_line2": "Esc 退出并保存当前阶段",
        },
    }
    result = run_navigation_main2(
        test_trials_override=pairs_from_trials(nav_trials),
        session_metadata=metadata,
        experiment_output_dir=str(output_dir),
        participant_id=participant_id,
        preflight=False,
        map_path_cli=map_path,
        skip_guidance=True,
        external_screen=screen,
        external_clock=clock,
        manage_pygame=False,
        auto_exit_on_finish=True,
        display_trial_progress=display_trial_progress,
        return_run_state=True,
    )
    if isinstance(result, dict):
        return {"output": result.get("output"), "interrupted": bool(result.get("interrupted", False))}
    return {"output": result, "interrupted": False}
