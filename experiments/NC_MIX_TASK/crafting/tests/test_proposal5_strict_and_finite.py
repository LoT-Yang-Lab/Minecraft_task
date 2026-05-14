"""strict_order_targets 与 finite_trials 行为。"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from src.config_io_crafting import TrialSpec, trial_list_from_specs
from src.game_crafting import GameCrafting
from src.recorder import RLDataRecorder
from src.rules_io_crafting import _crafting_root, load_rule_data_with_transition_map
from src.game_crafting import Action
from src.validation_crafting import choose_reachable_targets_multi_starts


def _find_action(game: GameCrafting, kind: str, param: str, want_next: str) -> Action | None:
    for a in game.get_available_actions():
        if a.kind == kind and a.param == param and a.next_state == want_next:
            return a
    return None


def _builtin_rules():
    root = Path(_crafting_root())
    rules = str(root / "data" / "rules" / "crafting_rules_v1.json")
    tm = str(root / "data" / "maps" / "builtin_map_a.json")
    return load_rule_data_with_transition_map(rules, tm)


def test_strict_requested_rejects_invalid_target() -> None:
    r = _builtin_rules()
    rng = random.Random(0)
    with pytest.raises(ValueError, match="strict_order_targets"):
        choose_reachable_targets_multi_starts(
            requested_targets=["stone_01"],
            raw_states=["stone_01"],
            order_count=1,
            potion1_fwd=r.potion1,
            potion1_rev=r.potion1_rev,
            potion2_fwd=r.potion2,
            potion2_rev=r.potion2_rev,
            potion3=r.potion3,
            rng=rng,
            min_distance=2,
            strict_requested=True,
        )


def test_strict_requested_accepts_valid_pair() -> None:
    r = _builtin_rules()
    rng = random.Random(0)
    # stone_01→stone_05 在 builtin_map_a 上最短步数≥2（非药水3一步直达）
    targets, msgs = choose_reachable_targets_multi_starts(
        requested_targets=["stone_05"],
        raw_states=["stone_01"],
        order_count=1,
        potion1_fwd=r.potion1,
        potion1_rev=r.potion1_rev,
        potion2_fwd=r.potion2,
        potion2_rev=r.potion2_rev,
        potion3=r.potion3,
        rng=rng,
        min_distance=2,
        strict_requested=True,
    )
    assert targets == ["stone_05"]
    assert not msgs


def test_finite_trials_session_complete_after_one_trial(tmp_path) -> None:
    rules = _builtin_rules()
    rec = RLDataRecorder(participant_id="ut", task_type="Test", output_root=str(tmp_path))
    spec = TrialSpec(
        trial_id="one",
        order_count=1,
        seed=42,
        raws=["stone_01"],
        targets=["stone_05"],
        strict_order_targets=True,
        schedule_meta={"session": 1, "block_index": 1, "pair_id": "X"},
    )
    td = trial_list_from_specs([spec])
    game = GameCrafting(recorder=rec, rules=rules, trial_data=td, finite_trials=True)

    a_q = _find_action(game, "ring1_step", "+1", "stone_02")
    assert a_q is not None
    assert game.execute_action(a_q, source_key="Q")
    a_a = _find_action(game, "ring2_step", "+1", "stone_05")
    assert a_a is not None
    assert game.execute_action(a_a, source_key="A")
    assert game.order_complete_overlay_pending
    game.dismiss_order_complete_overlay()
    assert game.session_complete
    assert game.current_trial is None
