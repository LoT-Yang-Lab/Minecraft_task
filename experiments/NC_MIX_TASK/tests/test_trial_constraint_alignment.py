from __future__ import annotations

from pathlib import Path

from crafting.src.config_io_crafting import load_trial_list_auto
from crafting.src.game_crafting import GameCrafting
from crafting.src.rules_io_crafting import load_rule_data_with_transition_map


class _DummyRecorder:
    def start_episode(self) -> None:
        return

    def log_action(self, *args, **kwargs) -> None:
        return


def test_nav_sequence_can_start_in_crafting() -> None:
    root = Path(__file__).resolve().parents[1]
    rules = load_rule_data_with_transition_map(
        str(root / "crafting" / "data" / "rules" / "crafting_rules_v1.json"),
        str(root / "crafting" / "data" / "maps" / "builtin_map_a.json"),
    )
    trial_list = load_trial_list_auto(
        str(root / "navigation" / "assets" / "trial_sequences" / "map_1773511099.json")
    )
    game = GameCrafting(
        recorder=_DummyRecorder(),
        rules=rules,
        trial_data=trial_list,
        finite_trials=True,
    )
    assert game.current_trial is not None
    assert len(game.order_targets) == 1
