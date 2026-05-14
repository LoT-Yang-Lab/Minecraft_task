from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence

import pygame

_ROOT_NC = Path(__file__).resolve().parents[2]
if str(_ROOT_NC) not in sys.path:
    sys.path.insert(0, str(_ROOT_NC))

from mix.trial_display import format_session_trial_line

from .config_io_crafting import TrialSpec, trial_list_from_specs
from .game_crafting import GameCrafting
from .main_crafting import (
    run_crafting_game_loop,
)
from .proposal5_validation import validate_crafting_trials_on_map
from .recorder import RLDataRecorder


def craft_trials_to_trial_specs(
    craft_trials: Sequence[Dict[str, Any]],
    session_num: int,
    session_seed: int,
) -> List[TrialSpec]:
    specs: List[TrialSpec] = []
    for t in craft_trials:
        s = int(t["start"])
        g = int(t["goal"])
        bi = int(t.get("block_index", t.get("index", 0)))
        pair_id = str(t.get("pair_id", "unknown"))
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
            "category": t.get("category", ""),
            "nav_start": s,
            "nav_goal": g,
            "d_grid": t.get("d_grid", ""),
            "d_loop": t.get("d_loop", ""),
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


def run_crafting_session(
    *,
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    pid: str,
    rules,
    image_cache,
    bottle_cache,
    craft_trials: Sequence[Dict[str, Any]],
    session_num: int,
    session_seed: int,
    output_dir: Path,
    order: str,
    domain: str,
    navigation_trials: Sequence[Dict[str, Any]] | None = None,
    combined_order: Sequence[Dict[str, Any]] | None = None,
    display_trial_progress: tuple[int, int] | None = None,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    validate_crafting_trials_on_map(rules, craft_trials, min_distance=2)
    trial_specs = craft_trials_to_trial_specs(craft_trials, session_num, session_seed)
    trial_data = trial_list_from_specs(trial_specs, source_path=f"<mix_session_{session_num}>")
    meta_path = output_dir / "session_metadata.json"
    with meta_path.open("w", encoding="utf-8") as fh:
        json.dump(
            {
                "order": order,
                "session": session_num,
                "seed": session_seed,
                "domain": domain,
                "crafting_trials": list(craft_trials),
                "navigation_trials": list(navigation_trials or []),
                "combined_order": list(combined_order or []),
            },
            fh,
            ensure_ascii=False,
            indent=2,
        )

    recorder = RLDataRecorder(
        participant_id=pid,
        task_type="Crafting_Mix",
        output_root=str(output_dir),
    )
    game = GameCrafting(
        recorder=recorder,
        rules=rules,
        trial_data=trial_data,
        finite_trials=True,
    )
    if display_trial_progress is not None:
        mix_meta = format_session_trial_line(
            session_label=f"Session {session_num}",
            trial_n=display_trial_progress[0],
            trial_n_total=display_trial_progress[1],
            domain_zh="合成",
        )
    else:
        mix_meta = None

    completed = run_crafting_game_loop(
        screen,
        clock,
        game,
        image_cache,
        bottle_cache,
        header_title="NC Mix · 合成",
        meta_line=mix_meta,
        session_meta_prefix=(
            None if display_trial_progress is not None else f"Session {session_num}"
        ),
        meta_line2="Esc 退出并保存当前阶段",
    )
    recorder.save_to_file()
    return {
        "session": session_num,
        "domain": domain,
        "meta_path": str(meta_path),
        "interrupted": (not completed),
    }
