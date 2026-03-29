#!/usr/bin/env python3
"""Navigation6 测试阶段独立入口（地图交通动作版）。

该版本是较新的被试界面：
- 不再使用 Graph9 的“上/下/左/右/环路”动作文案；
- 而是使用交通方式动作：公交、轻轨、高铁；
- 支持由外部脚本注入预先规划好的 (start, goal) 试次序列与 session 元数据。
"""
from __future__ import annotations

import datetime
import os
import random
import re
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import pygame

# .../Minecraft8.0/experiments/navigation6/main2.py -> .../Minecraft8.0
_this_file = Path(__file__).resolve()
_project_root = _this_file.parents[2]
_project_root_str = str(_project_root)
if _project_root_str not in sys.path:
    sys.path.insert(0, _project_root_str)

from experiments.navigation6.app.common.station_names import code_to_station_name
from experiments.navigation6.app.common.trajectory_export import export_navigation_session_to_legacy_xlsx
from experiments.navigation6.app.experiment.main import (
    EXPERIMENT_MAPS,
    _resolve_map_path,
    build_position_encoding,
    execute_action,
    get_available_actions,
)
from experiments.navigation6.app.experiment.game import GameNavigation6
from experiments.navigation6.app.paths import trajectory_raw_dir
from experiments.navigation6.app.practice.practice.practice_ui import (
    MINI_MAP_STATION_ICON_MAX,
    _load_raw_station_icons,
    _scale_station_icon_dict,
    _scale_surface_uniform_to_max_side,
)
from shared.common.recorder import RLDataRecorder


_KEY_TO_TRANSIT_MODE = {
    pygame.K_q: ("bus", "next"),
    pygame.K_e: ("bus", "prev"),
    pygame.K_a: ("light_rail", "next"),
    pygame.K_d: ("light_rail", "prev"),
    pygame.K_w: ("metro", "next"),
}

_MAX_ACTIONS_PER_TRIAL = 10


def _blit_wrapped(
    screen: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    color: Tuple[int, int, int],
    x: int,
    y: int,
    max_width: int,
    line_gap: int = 2,
) -> int:
    if not text.strip():
        return y
    line_h = font.get_linesize() + line_gap
    current = ""
    yy = y
    for ch in text:
        test = current + ch
        w = font.size(test)[0]
        if w <= max_width or not current:
            current = test
        else:
            screen.blit(font.render(current, True, color), (x, yy))
            yy += line_h
            current = ch
    if current:
        screen.blit(font.render(current, True, color), (x, yy))
        yy += line_h
    return yy


def _new_game(map_id: str, map_path: str) -> GameNavigation6:
    rec = RLDataRecorder("Navigation6_Main2", task_type="Navigation6_Main2")
    return GameNavigation6(
        rec,
        map_type=map_id,
        target_entropy=0.5,
        enable_experiment=False,
        custom_map_file=map_path,
    )


def _pick_action_idx_by_mode(
    actions: List[Tuple[str, str, Optional[Union[str, int]]]],
    game: GameNavigation6,
    mode: str,
    want_dir: str,
) -> Optional[int]:
    modes = list(getattr(game, "transit_modes", []) or [])
    for i, (_label, akey, extra) in enumerate(actions):
        if extra is None:
            continue
        li = int(extra) if not isinstance(extra, int) else extra
        if li < 0 or li >= len(modes):
            continue
        dir_name = "next"
        if akey in ("instant_transit_prev", "instant_subway_prev"):
            dir_name = "prev"
        if modes[li] == mode and dir_name == want_dir:
            return i
    return None


def _key_name_for_action(mode: str, action_key: str) -> str:
    is_next = action_key in ("instant_transit_next", "instant_subway_next")
    if mode == "bus":
        return "Q" if is_next else "E"
    if mode == "light_rail":
        return "A" if is_next else "D"
    # 高铁（metro）单向，按键固定 W
    return "W"


def _clean_option_label(label: str) -> str:
    out = re.sub(r"（[^）]*）", "", label)
    out = re.sub(r"\([^)]*\)", "", out)
    return " ".join(out.split())


def _draw_station_icon(
    screen: pygame.Surface,
    station_icons: Dict[int, pygame.Surface],
    code: int,
    x: int,
    y: int,
    max_side: int = 64,
) -> None:
    icon = station_icons.get(code)
    if icon is not None:
        draw_ic = _scale_surface_uniform_to_max_side(icon, max_side)
        rect = draw_ic.get_rect(topleft=(x, y))
        screen.blit(draw_ic, rect)
        return
    # 回退占位：无素材时画圆点
    pygame.draw.circle(screen, (210, 220, 240), (x + max_side // 2, y + max_side // 2), max_side // 3)


def _build_neighbors(
    game: GameNavigation6,
    all_codes: List[int],
    code_to_cell: Dict[int, Tuple[int, int]],
    cell_to_code: Dict[Tuple[int, int], int],
) -> Dict[int, Set[int]]:
    neighbors: Dict[int, Set[int]] = {c: set() for c in all_codes}
    original_pos = (game.player_x, game.player_y)
    for c in all_codes:
        sx, sy = code_to_cell[c]
        game.player_x, game.player_y = sx, sy
        actions = get_available_actions(game, include_bidirectional_for_surface=True)
        for action in actions:
            ox, oy = game.player_x, game.player_y
            ok = execute_action(game, action)
            if ok:
                nc = cell_to_code.get((game.player_x, game.player_y), 0)
                if nc > 0 and nc != c:
                    neighbors[c].add(nc)
            game.player_x, game.player_y = ox, oy
    game.player_x, game.player_y = original_pos
    return neighbors


def _shortest_distance(neighbors: Dict[int, Set[int]], start: int, goal: int) -> int:
    if start == goal:
        return 0
    q = deque([(start, 0)])
    visited = {start}
    while q:
        cur, d = q.popleft()
        for nxt in neighbors.get(cur, set()):
            if nxt == goal:
                return d + 1
            if nxt not in visited:
                visited.add(nxt)
                q.append((nxt, d + 1))
    return -1


def _generate_test_trials(
    all_codes: List[int],
    neighbors: Dict[int, Set[int]],
    trial_count: int = 9,
    min_distance: int = 2,
) -> List[Tuple[int, int]]:
    pairs: List[Tuple[int, int]] = []
    for s in all_codes:
        for g in all_codes:
            if s == g:
                continue
            d = _shortest_distance(neighbors, s, g)
            if d >= min_distance:
                pairs.append((s, g))
    if not pairs:
        for s in all_codes:
            for g in all_codes:
                if s != g:
                    pairs.append((s, g))
    random.shuffle(pairs)
    if not pairs:
        return []
    out: List[Tuple[int, int]] = []
    while len(out) < trial_count:
        out.append(pairs[len(out) % len(pairs)])
    return out


def main(
    test_trials_override: Optional[List[Tuple[int, int]]] = None,
    session_metadata: Optional[Dict[str, Any]] = None,
    experiment_output_dir: Optional[str] = None,
    participant_id: str = "Navigation6_User",
) -> Optional[str]:
    pygame.init()
    pygame.key.stop_text_input()
    W, H = 800, 700
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Navigation6 Main2 — 地图交通测试")

    font_lg = pygame.font.SysFont("SimHei", 26)
    font_md = pygame.font.SysFont("SimHei", 20)
    font_sm = pygame.font.SysFont("SimHei", 16)
    pad_x = 24
    text_max_w = W - pad_x * 2
    clock = pygame.time.Clock()
    station_icons_raw = _load_raw_station_icons()
    station_icons_mini = _scale_station_icon_dict(station_icons_raw, max(56, MINI_MAP_STATION_ICON_MAX))

    if not EXPERIMENT_MAPS:
        print("未配置可用地图（EXPERIMENT_MAPS 为空）。")
        pygame.quit()
        return None
    map_file = EXPERIMENT_MAPS[0][1]
    map_path = _resolve_map_path(map_file)
    map_id = os.path.splitext(os.path.basename(map_path))[0]
    map_structure = EXPERIMENT_MAPS[0][0]
    if not os.path.exists(map_path):
        print(f"地图文件不存在: {map_path}")
        pygame.quit()
        return None

    # 数据记录机制沿用 main2 风格
    data_root = trajectory_raw_dir()
    os.makedirs(data_root, exist_ok=True)
    session_start = datetime.datetime.now()
    session_log: List[Dict] = []
    trial_summaries: List[Dict[str, Any]] = []

    def log_step(phase, trial_id, step, from_node, action, to_node, is_valid, extra=None):
        entry = {
            "phase": phase,
            "trial_id": trial_id,
            "step": step,
            "timestamp": time.time(),
            "from_node": from_node,
            "action": action,
            "to_node": to_node,
            "is_valid": is_valid,
        }
        if extra:
            entry.update(extra)
        session_log.append(entry)

    def save_session():
        return export_navigation_session_to_legacy_xlsx(
            data_root=data_root,
            session_start=session_start,
            session_end=datetime.datetime.now(),
            map_id=map_id,
            map_structure=map_structure,
            steps=session_log,
            test_trials=test_trials,
            trial_summaries=trial_summaries,
            session_metadata=session_metadata,
            code_to_cell=code_to_cell,
            participant_id=participant_id,
            task_type="Navigation6_Test",
            experiment_output_dir=experiment_output_dir,
        )

    PHASE_TEST = "test"
    PHASE_FINISHED = "finished"
    phase = PHASE_TEST

    game = _new_game(map_id, map_path)
    cell_to_code, code_to_cell, _ = build_position_encoding(game)
    all_codes = sorted(code_to_cell.keys())
    if len(all_codes) < 2:
        print("可用站点不足，无法开始测试。")
        pygame.quit()
        return None

    neighbors = _build_neighbors(game, all_codes, code_to_cell, cell_to_code)
    if test_trials_override:
        test_trials = [(int(s), int(g)) for s, g in test_trials_override]
    else:
        test_trials = _generate_test_trials(all_codes, neighbors, trial_count=9, min_distance=2)
    if not test_trials:
        print("无法生成测试试次。")
        pygame.quit()
        return None

    test_trial_idx = 0
    test_step = 0
    test_trial_steps: List[int] = []
    test_trial_outcomes: List[str] = []
    trial_start_wall_time = time.time()
    trial_first_move_latency_ms: Optional[int] = None
    trial_start_code: int
    s, g = test_trials[0]
    trial_start_code = s
    game.player_x, game.player_y = code_to_cell[s]
    test_goal_node = g

    def _start_trial(start_code: int, goal_code: int) -> None:
        nonlocal test_step, test_goal_node, trial_start_wall_time, trial_first_move_latency_ms, trial_start_code
        trial_start_code = start_code
        test_step = 0
        trial_first_move_latency_ms = None
        trial_start_wall_time = time.time()
        game.player_x, game.player_y = code_to_cell[start_code]
        test_goal_node = goal_code

    def _finalize_current_trial(reached_goal: bool, end_code: int) -> None:
        nonlocal phase, test_trial_idx
        elapsed_ms = int(round((time.time() - trial_start_wall_time) * 1000))
        optimal_distance = _shortest_distance(neighbors, trial_start_code, test_goal_node)
        outcome = "reached_goal" if reached_goal else "action_cap"
        trial_summaries.append(
            {
                "trial_id": test_trial_idx + 1,
                "start": trial_start_code,
                "goal": test_goal_node,
                "path_length": test_step,
                "optimal_distance": optimal_distance,
                "latency_to_first_move_ms": trial_first_move_latency_ms,
                "total_response_time_ms": elapsed_ms,
                "goal_reached": reached_goal,
                "outcome": outcome,
                "final_node": end_code,
                "path_efficiency": (optimal_distance / test_step) if reached_goal and test_step > 0 and optimal_distance > 0 else 0,
            }
        )
        test_trial_steps.append(test_step)
        test_trial_outcomes.append(outcome)
        test_trial_idx += 1
        if test_trial_idx >= len(test_trials):
            phase = PHASE_FINISHED
            return
        next_start, next_goal = test_trials[test_trial_idx]
        _start_trial(next_start, next_goal)

    running = True
    while running:
        events = pygame.event.get()
        for ev in events:
            if ev.type == pygame.QUIT:
                running = False

        for ev in events:
            if ev.type != pygame.KEYDOWN:
                continue
            if ev.key == pygame.K_ESCAPE:
                running = False
                break

            if phase != PHASE_TEST:
                continue
            mapping = _KEY_TO_TRANSIT_MODE.get(ev.key)
            if mapping is None:
                continue
            mode, want_dir = mapping
            actions = get_available_actions(game, include_bidirectional_for_surface=True)
            chosen_idx = _pick_action_idx_by_mode(actions, game, mode, want_dir)
            current_code = cell_to_code.get((game.player_x, game.player_y), 0)
            if chosen_idx is None:
                log_step(
                    PHASE_TEST,
                    test_trial_idx + 1,
                    test_step,
                    current_code,
                    f"{mode}_{want_dir}",
                    None,
                    False,
                    {"goal_node": test_goal_node},
                )
                continue

            action = actions[chosen_idx]
            ok = execute_action(game, action)
            if not ok:
                log_step(
                    PHASE_TEST,
                    test_trial_idx + 1,
                    test_step,
                    current_code,
                    action[0],
                    None,
                    False,
                    {"goal_node": test_goal_node},
                )
                continue

            new_code = cell_to_code.get((game.player_x, game.player_y), 0)
            if trial_first_move_latency_ms is None:
                trial_first_move_latency_ms = int(round((time.time() - trial_start_wall_time) * 1000))
            test_step += 1
            start_code, _goal = test_trials[test_trial_idx]
            log_step(
                PHASE_TEST,
                test_trial_idx + 1,
                test_step,
                current_code,
                action[0],
                new_code,
                True,
                {
                    "goal_node": test_goal_node,
                    "optimal_distance": _shortest_distance(neighbors, start_code, test_goal_node),
                    "action_key": action[1],
                    "action_extra": action[2],
                    "reaction_time_ms": trial_first_move_latency_ms if test_step == 1 else None,
                    "elapsed_trial_time_ms": int(round((time.time() - trial_start_wall_time) * 1000)),
                    "max_actions": _MAX_ACTIONS_PER_TRIAL,
                },
            )
            if new_code == test_goal_node:
                _finalize_current_trial(reached_goal=True, end_code=new_code)
            elif test_step >= _MAX_ACTIONS_PER_TRIAL:
                log_step(
                    PHASE_TEST,
                    test_trial_idx + 1,
                    test_step,
                    new_code,
                    "trial_cap_reached",
                    new_code,
                    True,
                    {
                        "goal_node": test_goal_node,
                        "max_actions": _MAX_ACTIONS_PER_TRIAL,
                        "latency_to_first_move_ms": trial_first_move_latency_ms,
                        "total_response_time_ms": int(round((time.time() - trial_start_wall_time) * 1000)),
                    },
                )
                _finalize_current_trial(reached_goal=False, end_code=new_code)

        screen.fill((28, 28, 32))
        y = 16
        if phase == PHASE_TEST:
            current_code = cell_to_code.get((game.player_x, game.player_y), 0)
            y = _blit_wrapped(screen, font_lg, "测试阶段 — 地图交通导航", (255, 220, 200), pad_x, y, text_max_w)
            y += 6
            y = _blit_wrapped(screen, font_sm, f"地图：{map_id}", (180, 190, 210), pad_x, y, text_max_w)
            y += 4
            y = _blit_wrapped(
                screen,
                font_md,
                f"试次：{test_trial_idx + 1} / {len(test_trials)}",
                (190, 210, 230),
                pad_x,
                y,
                text_max_w,
            )
            y += 4
            cur_text = f"当前位置：{code_to_station_name(current_code)}（编码 {current_code}）"
            cur_surf = font_md.render(cur_text, True, (180, 230, 180))
            screen.blit(cur_surf, (pad_x, y))
            cur_icon_x = min(pad_x + cur_surf.get_width() + 10, W - 70)
            _draw_station_icon(screen, station_icons_mini, current_code, cur_icon_x, y - 6, max_side=40)
            y += max(font_md.get_linesize() + 2, 40) + 2

            goal_text = f"目标位置：{code_to_station_name(test_goal_node)}（编码 {test_goal_node}）"
            goal_surf = font_md.render(goal_text, True, (255, 200, 160))
            screen.blit(goal_surf, (pad_x, y))
            goal_icon_x = min(pad_x + goal_surf.get_width() + 10, W - 70)
            _draw_station_icon(screen, station_icons_mini, test_goal_node, goal_icon_x, y - 6, max_side=40)
            y += max(font_md.get_linesize() + 2, 40) + 2
            y = _blit_wrapped(
                screen,
                font_sm,
                f"本试次已用步数：{test_step} / {_MAX_ACTIONS_PER_TRIAL}",
                (180, 180, 200),
                pad_x,
                y,
                text_max_w,
            )
            y += 10
            y = _blit_wrapped(screen, font_md, "按键：公交 Q/E  ·  轻轨 A/D  ·  高铁 W", (210, 210, 225), pad_x, y, text_max_w)
            y += 6
            y = _blit_wrapped(screen, font_md, "当前可执行动作：", (210, 210, 225), pad_x, y, text_max_w)
            y += 4
            actions = get_available_actions(game, include_bidirectional_for_surface=True)
            if not actions:
                y = _blit_wrapped(screen, font_sm, "  （当前站点无可用交通动作）", (120, 130, 145), pad_x, y, text_max_w)
            else:
                modes = list(getattr(game, "transit_modes", []) or [])
                for label, action_key, extra in actions:
                    mode = "metro"
                    if extra is not None:
                        li = int(extra) if not isinstance(extra, int) else extra
                        if 0 <= li < len(modes):
                            mode = modes[li]
                    key_name = _key_name_for_action(mode, action_key)
                    clean_label = _clean_option_label(label)
                    y = _blit_wrapped(screen, font_sm, f"  [{key_name}] {clean_label}", (225, 225, 210), pad_x, y, text_max_w)
                    y += 2
            y += 10
            _blit_wrapped(screen, font_sm, "ESC：退出（数据会保存）", (140, 140, 160), pad_x, y, text_max_w)
        else:
            y = 60
            y = _blit_wrapped(screen, font_lg, "实验结束", (220, 255, 220), pad_x, y, text_max_w)
            y += 12
            y = _blit_wrapped(
                screen,
                font_md,
                f"已完成 {len(test_trials)} 个导航试次。",
                (200, 220, 210),
                pad_x,
                y,
                text_max_w,
            )
            y += 8
            for i, steps in enumerate(test_trial_steps):
                s0, g0 = test_trials[i]
                opt = _shortest_distance(neighbors, s0, g0)
                outcome = test_trial_outcomes[i] if i < len(test_trial_outcomes) else "unknown"
                y = _blit_wrapped(
                    screen,
                    font_sm,
                    f"  试次 {i + 1}：{code_to_station_name(s0)} → {code_to_station_name(g0)}  步数 {steps}（最短 {opt}，结果 {outcome}）",
                    (190, 200, 210),
                    pad_x,
                    y,
                    text_max_w,
                )
                y += 2
            y += 12
            _blit_wrapped(screen, font_sm, "按 ESC 退出（数据已保存）。", (170, 180, 190), pad_x, y, text_max_w)

        pygame.display.flip()
        clock.tick(30)

    out = save_session()
    print(f"Main2 数据已保存（legacy xlsx）: {out}")
    pygame.quit()
    return out


if __name__ == "__main__":
    main()
