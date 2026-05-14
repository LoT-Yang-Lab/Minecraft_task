"""转化表与内置图一致性、规则加载。"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from src.graph_moves import (
    neighbors_from_potions,
    neighbors_player_moves,
    potion_backward_from_forward,
)
from src.maps_crafting import built_in_potion_tables, get_map
from src.config_io_crafting import load_trial_list_auto
from src.rules_io_crafting import _crafting_root, load_rule_data, load_rule_data_with_transition_map
from src.transition_map_io_crafting import (
    TransitionMapData,
    list_available_transition_maps,
    load_transition_map,
    save_transition_map,
)


def test_builtin_potions_match_graph_neighbors_for_map_a() -> None:
    g = get_map("map_a")
    p1f, p1r, p2f, p2r, p3 = built_in_potion_tables("map_a")
    for sid in [f"stone_{i:02d}" for i in range(1, 10)]:
        assert neighbors_player_moves(sid, g) == neighbors_from_potions(
            sid, p1f, p1r, p2f, p2r, p3
        )


def test_load_builtin_map_a_json() -> None:
    root = _crafting_root()
    path = os.path.join(root, "data", "maps", "builtin_map_a.json")
    tm = load_transition_map(path)
    assert isinstance(tm.potion1, dict)
    assert tm.linked_navigation_map_id == "map_1774095558"
    again = load_transition_map(path)
    assert tm.potion1 == again.potion1


def test_load_trial_list_auto_from_navigation_sequence() -> None:
    root = Path(_crafting_root())
    nav_json = root.parent / "navigation" / "assets" / "trial_sequences" / "map_1774095558.json"
    if not nav_json.is_file():
        import pytest

        pytest.skip(f"Navigation trial_sequences not found: {nav_json}")
    tl = load_trial_list_auto(str(nav_json))
    assert tl.format_label == "nav_sequence"
    assert len(tl.trials) == 27
    assert tl.trials[0].raws == ["stone_01"]
    assert tl.trials[0].targets == ["stone_02"]
    assert tl.trials[0].order_count == 1


def test_save_load_roundtrip() -> None:
    p1f, _p1r, p2f, _p2r, p3 = built_in_potion_tables("map_b")
    data = TransitionMapData(
        map_id="map_b",
        description="t",
        potion1=p1f,
        potion2=p2f,
        potion3=p3,
        potion3_control_offset={"stone_01": (12.5, -30.0)},
    )
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "m.json")
        save_transition_map(path, data)
        back = load_transition_map(path)
    assert back.potion1 == p1f
    assert back.map_id == "map_b"
    assert back.potion3_control_offset["stone_01"] == (12.5, -30.0)


def test_list_available_transition_maps_includes_builtin() -> None:
    root = _crafting_root()
    lst = list_available_transition_maps(root)
    stems = [Path(p).stem for _, p in lst]
    assert "builtin_map_a" in stems


def test_load_rule_data_with_transition_map() -> None:
    root = _crafting_root()
    rules = os.path.join(root, "data", "rules", "crafting_rules_v1.json")
    tm_path = os.path.join(root, "data", "maps", "builtin_map_a.json")
    r = load_rule_data_with_transition_map(rules, tm_path)
    assert r.transition_map_path == os.path.abspath(tm_path)
    tm = load_transition_map(tm_path)
    assert r.potion1 == tm.potion1
    assert r.potion1_rev == potion_backward_from_forward(dict(tm.potion1))
    assert r.potion2_rev == potion_backward_from_forward(dict(tm.potion2))
    assert r.map_id == tm.map_id


def test_default_rules_load_transition_map_path() -> None:
    r = load_rule_data()
    assert r.transition_map_path is not None
    assert os.path.isfile(r.transition_map_path)
    tm = load_transition_map(r.transition_map_path)
    assert r.potion1 == tm.potion1


def test_rules_without_transition_path_uses_builtin() -> None:
    root = _crafting_root()
    rules_path = os.path.join(root, "data", "rules", "crafting_rules_v1.json")
    with open(rules_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    raw.pop("transition_map_path", None)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as tmp:
        json.dump(raw, tmp)
        tmp_path = tmp.name
    try:
        r = load_rule_data(tmp_path)
        b1f, b1r, b2f, b2r, b3 = built_in_potion_tables(r.map_id)
        assert r.potion1 == b1f
        assert r.potion1_rev == b1r
        assert r.potion2 == b2f
        assert r.potion2_rev == b2r
        assert r.potion3 == b3
        assert r.transition_map_path is None
    finally:
        os.unlink(tmp_path)
