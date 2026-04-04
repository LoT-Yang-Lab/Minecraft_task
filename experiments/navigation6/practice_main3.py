#!/usr/bin/env python3
"""
Navigation6 练习阶段 v3：自由探索模式。

设计目标：
- 被试自由探索地图，不做问答题；
- 每个位置编码点至少访问 min_visits 次（默认 2 次）；
- 一张地图默认练习 rounds 次（默认 2 轮）；
- 仅当当前轮所有点都达到 min_visits，才进入下一轮/完成。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pygame

_this_file = Path(__file__).resolve()
_project_root = _this_file.parents[2]
_project_root_str = str(_project_root)
if _project_root_str not in sys.path:
    sys.path.insert(0, _project_root_str)

from experiments.navigation6.app.experiment.main import (
    EXPERIMENT_MAPS,
    build_position_encoding,
    execute_action,
    get_available_actions,
)
from experiments.navigation6.app.experiment.game import GameNavigation6
from experiments.navigation6.app.common.station_names import code_to_station_name
from experiments.navigation6.app.common.transit_action_display import transit_mode_key_letter
from experiments.navigation6.app.common.transit_curve_geometry import (
    TRANSIT_CURVE_MIN_LEN,
    transit_bezier_control,
    transit_bezier_tangent_at_mid,
    transit_segment_polyline,
)
from experiments.navigation6.app.practice.practice.practice_ui import (
    COLOR_TRANSIT_BUS,
    COLOR_TRANSIT_METRO,
    COLOR_TRANSIT_LIGHT_RAIL,
    COLOR_TRANSIT_UNKNOWN,
    MINI_MAP_STATION_ICON_MAX,
    START_ICON_MAX_PX,
    _load_raw_station_icons,
    _scale_station_icon_dict,
    _scale_surface_uniform_to_max_side,
)
from experiments.navigation6.app.paths import resolve_map_path, practice_raw_dir
from shared.common.recorder import RLDataRecorder


WINDOW_W = 980
WINDOW_H = 640
DEFAULT_MAP_FILE = EXPERIMENT_MAPS[0][1] if EXPERIMENT_MAPS else "map_nav6_sample.json"

_KEY_TO_TRANSIT_MODE = {
    pygame.K_q: ("bus", "next"),
    pygame.K_w: ("bus", "prev"),
    pygame.K_a: ("light_rail", "next"),
    pygame.K_s: ("light_rail", "prev"),
    pygame.K_z: ("metro", "next"),
    pygame.K_x: ("metro", "prev"),
}


@dataclass
class StepLog:
    round_index: int
    step_index: int
    t_sec: float
    from_code: int
    to_code: int
    action_label: str
    action_key: str
    action_extra: Optional[Union[str, int]]
    explore_rate: float
    mastery_rate: float


def _draw_arrow_head(
    screen: pygame.Surface,
    sx1: float,
    sy1: float,
    sx2: float,
    sy2: float,
    color: Tuple[int, int, int],
    arrow_len: int = 8,
    arrow_hw: int = 4,
    at_midpoint: bool = False,
) -> None:
    dx = sx2 - sx1
    dy = sy2 - sy1
    length = (dx * dx + dy * dy) ** 0.5
    if length < 1e-6:
        return
    ux = dx / length
    uy = dy / length
    if at_midpoint:
        tip = ((sx1 + sx2) / 2, (sy1 + sy2) / 2)
    else:
        tip = (sx2, sy2)
    base_center_x = tip[0] - ux * arrow_len
    base_center_y = tip[1] - uy * arrow_len
    base_left = (base_center_x - uy * arrow_hw, base_center_y + ux * arrow_hw)
    base_right = (base_center_x + uy * arrow_hw, base_center_y - ux * arrow_hw)
    pygame.draw.polygon(screen, color, [tip, base_left, base_right])


def _line_color(mode: str) -> Tuple[int, int, int]:
    if mode == "bus":
        return COLOR_TRANSIT_BUS
    if mode == "light_rail":
        return COLOR_TRANSIT_LIGHT_RAIL
    if mode == "metro":
        return COLOR_TRANSIT_METRO
    return COLOR_TRANSIT_UNKNOWN


def _build_transit_specs(game: GameNavigation6) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    modes = list(getattr(game, "transit_modes", []) or [])
    for i, line in enumerate(getattr(game, "subway_lines", []) or []):
        path = list(line.get("path", []))
        if len(path) < 2:
            continue
        mode = modes[i] if i < len(modes) else "metro"
        out.append(
            {
                "line_index": i,
                "mode": mode,
                "path": path,
                "station_indices": list(line.get("station_indices", [])),
                "segment_curve": list(line.get("segment_curve", [])),
                "segment_straight": list(line.get("segment_straight", [])),
            }
        )
    return out


def _collect_active_segments(
    game: GameNavigation6,
    actions: List[Tuple[str, str, Optional[Union[str, int]]]],
    transit_specs: List[Dict[str, Any]],
) -> Dict[Tuple[int, int], set[int]]:
    """
    返回当前可执行动作对应的路径段：
    key=(line_idx, seg_idx), value={+1/-1} 表示该段上的可执行方向。
    """
    out: Dict[Tuple[int, int], set[int]] = {}
    px, py = game.player_x, game.player_y
    pos_cur = (px, py)
    next_by_line = dict(game.get_instant_subway_next_stations(px, py))
    prev_by_line = dict(game.get_instant_subway_prev_stations(px, py))
    spec_by_line = {int(s.get("line_index", -1)): s for s in transit_specs}

    for _label, action_key, extra in actions:
        if extra is None:
            continue
        line_idx = int(extra) if not isinstance(extra, int) else extra
        spec = spec_by_line.get(line_idx)
        if not spec:
            continue
        path = spec.get("path") or []
        st = [int(x) for x in (spec.get("station_indices") or [])]
        if len(path) < 2 or not st:
            continue
        line_loop = False
        i0, i1 = st[0], st[-1]
        if 0 <= i0 < len(path) and 0 <= i1 < len(path):
            line_loop = path[i0] == path[i1]

        target_pos = None
        if action_key in ("instant_transit_next", "instant_subway_next"):
            target_pos = next_by_line.get(line_idx)
            direction_sign = +1
        elif action_key in ("instant_transit_prev", "instant_subway_prev"):
            target_pos = prev_by_line.get(line_idx)
            direction_sign = -1
        else:
            continue
        if target_pos is None:
            continue

        j = None
        for idx, si in enumerate(st):
            if 0 <= si < len(path) and path[si] == pos_cur:
                j = idx
                break
        if j is None:
            continue

        k = None
        for idx, si in enumerate(st):
            if 0 <= si < len(path) and path[si] == target_pos:
                k = idx
                break
        if k is None:
            continue

        start_si = st[j]
        end_si = st[k]
        segs: List[int] = []
        L = len(path)

        if direction_sign > 0:
            if start_si < end_si:
                segs.extend(range(start_si, end_si))
            elif start_si > end_si and line_loop:
                segs.extend(range(start_si, L - 1))
                segs.extend(range(0, end_si))
        else:
            if start_si > end_si:
                segs.extend(range(end_si, start_si))
            elif start_si < end_si and line_loop:
                segs.extend(range(0, start_si))
                segs.extend(range(end_si, L - 1))

        for seg_idx in segs:
            if not (0 <= seg_idx < L - 1):
                continue
            key = (line_idx, seg_idx)
            out.setdefault(key, set()).add(direction_sign)

    return out


def _draw_map_panel(
    screen: pygame.Surface,
    rect: pygame.Rect,
    code_to_cell: Dict[int, Tuple[int, int]],
    transit_specs: List[Dict[str, Any]],
    current_code: int,
    active_segments: Dict[Tuple[int, int], set[int]],
    station_icons_mini: Dict[int, pygame.Surface],
    icon_max_side: int,
) -> None:
    pygame.draw.rect(screen, (36, 38, 46), rect, border_radius=10)
    pygame.draw.rect(screen, (70, 74, 90), rect, 1, border_radius=10)
    if not code_to_cell:
        return

    points = list(code_to_cell.values())
    min_gx = min(p[0] for p in points)
    max_gx = max(p[0] for p in points)
    min_gy = min(p[1] for p in points)
    max_gy = max(p[1] for p in points)
    span_x = max(1, max_gx - min_gx + 1)
    span_y = max(1, max_gy - min_gy + 1)

    pad = 14
    inner_w = rect.w - 2 * pad
    inner_h = rect.h - 2 * pad
    cell_w = inner_w / span_x
    cell_h = inner_h / span_y
    base_x = rect.x + pad
    base_y = rect.y + pad

    def cell_center_float(gx: int, gy: int) -> Tuple[float, float]:
        return (
            base_x + (gx - min_gx + 0.5) * cell_w,
            base_y + (gy - min_gy + 0.5) * cell_h,
        )

    # 线路可视化：仅当前可执行动作对应的段为彩色，其余全部灰色。
    gray = (118, 122, 135)
    for spec in transit_specs:
        path = spec.get("path") or []
        if len(path) < 2:
            continue
        mode = str(spec.get("mode", "metro"))
        line_idx = int(spec.get("line_index", 0))
        sc = spec.get("segment_curve") or []
        st = spec.get("segment_straight") or []
        color_mode = _line_color(mode)
        for i in range(len(path) - 1):
            ax, ay = cell_center_float(path[i][0], path[i][1])
            bx, by = cell_center_float(path[i + 1][0], path[i + 1][1])
            bias = float(sc[i]) if i < len(sc) else 0.0
            straight = bool(st[i]) if i < len(st) else False
            key = (line_idx, i)
            active_dirs = active_segments.get(key, set())
            seg_color = color_mode if active_dirs else gray
            poly = transit_segment_polyline(ax, ay, bx, by, line_idx, i, bias, straight)
            if len(poly) >= 2:
                pts = [(int(round(p[0])), int(round(p[1]))) for p in poly]
                pygame.draw.lines(screen, seg_color, False, pts, 2)
            seg_len = math.hypot(bx - ax, by - ay)
            if straight or seg_len < TRANSIT_CURVE_MIN_LEN:
                if active_dirs:
                    if +1 in active_dirs:
                        _draw_arrow_head(screen, ax, ay, bx, by, seg_color, 8, 4, at_midpoint=True)
                    if -1 in active_dirs:
                        _draw_arrow_head(screen, bx, by, ax, ay, seg_color, 8, 4, at_midpoint=True)
            else:
                cx, cy = transit_bezier_control(ax, ay, bx, by, line_idx, i, bias)
                px, py, ux, uy = transit_bezier_tangent_at_mid(ax, ay, bx, by, cx, cy)
                tip_x, tip_y = px + ux * 4.0, py + uy * 4.0
                bx_a, by_a = px - ux * 9.0, py - uy * 9.0
                if active_dirs:
                    if +1 in active_dirs:
                        _draw_arrow_head(screen, bx_a, by_a, tip_x, tip_y, seg_color, 8, 4, at_midpoint=False)
                    if -1 in active_dirs:
                        _draw_arrow_head(screen, tip_x, tip_y, bx_a, by_a, seg_color, 8, 4, at_midpoint=False)

    # 当前位点：仅显示当前站点水果素材（不再显示“向下”人物素材）。
    cur = code_to_cell.get(current_code)
    if cur:
        cx, cy = cell_center_float(cur[0], cur[1])
        ic = station_icons_mini.get(current_code)
        if ic is not None:
            draw_ic = _scale_surface_uniform_to_max_side(ic, max(8, int(icon_max_side * 1.45)))
            ir = draw_ic.get_rect(center=(int(cx), int(cy)))
            screen.blit(draw_ic, ir)


def _font(size: int) -> pygame.font.Font:
    try:
        return pygame.font.SysFont("SimHei", size)
    except Exception:
        return pygame.font.SysFont("arial", size)


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


def _key_label_for_action(mode: str, action_key: str) -> str:
    if mode == "bus":
        return "Q" if action_key in ("instant_transit_next", "instant_subway_next") else "W"
    if mode == "light_rail":
        return "A" if action_key in ("instant_transit_next", "instant_subway_next") else "S"
    if mode == "metro":
        return "Z" if action_key in ("instant_transit_next", "instant_subway_next") else "X"
    return "?"


def _clean_option_label(label: str) -> str:
    """去掉动作标签里括号按键信息，如 公交（Q） -> 公交。"""
    out = re.sub(r"（[^）]*）", "", label)
    out = re.sub(r"\([^)]*\)", "", out)
    return " ".join(out.split())


def _new_game(map_id: str, map_path: str, seed: Optional[int]) -> GameNavigation6:
    if seed is not None:
        random.seed(seed)
    rec = RLDataRecorder("Navigation6_Practice3", task_type="Navigation6_Practice3")
    return GameNavigation6(
        rec,
        map_type=map_id,
        target_entropy=0.5,
        enable_experiment=False,
        custom_map_file=map_path,
    )


def _draw_wrapped(screen: pygame.Surface, font: pygame.font.Font, text: str, x: int, y: int, width: int, color: Tuple[int, int, int]) -> int:
    if not text:
        return y
    cur = ""
    line_h = font.get_linesize() + 2
    yy = y
    for ch in text:
        t = cur + ch
        if font.size(t)[0] <= width or not cur:
            cur = t
        else:
            screen.blit(font.render(cur, True, color), (x, yy))
            yy += line_h
            cur = ch
    if cur:
        screen.blit(font.render(cur, True, color), (x, yy))
        yy += line_h
    return yy


def _save_result(path: str, payload: Dict[str, Any]) -> str:
    os.makedirs(path, exist_ok=True)
    pid = payload.get("participant_id", "anonymous")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"navigation6_practice3_{pid}_{ts}.json"
    out = os.path.join(path, filename)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Navigation6 练习 v3：自由探索覆盖训练")
    parser.add_argument("--participant_id", "-p", type=str, default=None)
    parser.add_argument("--seed", "-s", type=int, default=None)
    parser.add_argument("--map", "-m", type=str, default=DEFAULT_MAP_FILE, help=f"地图文件名，默认 {DEFAULT_MAP_FILE}")
    parser.add_argument("--rounds", type=int, default=2, help="练习轮数（默认 2）")
    parser.add_argument("--min-visits", type=int, default=2, help="每点至少访问次数（默认 2）")
    args = parser.parse_args()

    participant_id = args.participant_id or os.environ.get("NAVIGATION6_PRACTICE3_PARTICIPANT_ID")
    if not participant_id:
        participant_id = f"anonymous_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    rounds_total = max(1, int(args.rounds))
    min_visits = max(1, int(args.min_visits))
    map_path = resolve_map_path(args.map)
    map_id = os.path.splitext(os.path.basename(map_path))[0]
    if not os.path.exists(map_path):
        print(f"地图文件不存在: {map_path}")
        sys.exit(1)

    pygame.init()
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption("Navigation6 Practice3 - 自由探索覆盖训练")
    clock = pygame.time.Clock()
    font_lg = _font(24)
    font_md = _font(18)
    font_sm = _font(16)
    icon_max_side = START_ICON_MAX_PX
    station_icons_raw = _load_raw_station_icons()
    station_icons_mini = _scale_station_icon_dict(station_icons_raw, MINI_MAP_STATION_ICON_MAX)

    session_t0 = time.time()
    phase = "running"
    running = True
    round_index = 1

    step_logs: List[StepLog] = []
    round_summaries: List[Dict[str, Any]] = []
    round_started_at = time.time()
    step_counter = 0

    game = _new_game(map_id, map_path, args.seed)
    transit_specs = _build_transit_specs(game)
    cell_to_code, code_to_cell, _ = build_position_encoding(game)
    all_codes = sorted(code_to_cell.keys())
    if not all_codes:
        print("地图没有有效编码点，无法进行练习。")
        pygame.quit()
        sys.exit(1)

    visit_counts: Dict[int, int] = {c: 0 for c in all_codes}
    cur_code = cell_to_code.get((game.player_x, game.player_y), 0)
    if cur_code > 0:
        visit_counts[cur_code] += 1

    def _metrics() -> Tuple[float, float, int]:
        n = len(all_codes)
        explored = sum(1 for c in all_codes if visit_counts[c] >= 1)
        mastered = sum(1 for c in all_codes if visit_counts[c] >= min_visits)
        return (explored / n, mastered / n, mastered)

    def _finish_round() -> None:
        nonlocal round_index, visit_counts, game, transit_specs, cell_to_code, code_to_cell, round_started_at, step_counter, phase
        explored_rate, mastery_rate, _ = _metrics()
        round_summaries.append(
            {
                "round_index": round_index,
                "duration_sec": round(time.time() - round_started_at, 3),
                "steps": step_counter,
                "explore_rate": explored_rate,
                "mastery_rate": mastery_rate,
                "min_visits_required": min_visits,
                "visit_counts": {str(k): int(v) for k, v in visit_counts.items()},
            }
        )
        if round_index >= rounds_total:
            phase = "finished"
            return
        round_index += 1
        step_counter = 0
        round_started_at = time.time()
        game = _new_game(map_id, map_path, args.seed)
        transit_specs = _build_transit_specs(game)
        cell_to_code, code_to_cell, _ = build_position_encoding(game)
        visit_counts = {c: 0 for c in all_codes}
        new_code = cell_to_code.get((game.player_x, game.player_y), 0)
        if new_code > 0:
            visit_counts[new_code] += 1
        phase = "round_transition"

    while running:
        screen.fill((28, 30, 36))
        events = pygame.event.get()
        for e in events:
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                running = False

        explored_rate, mastery_rate, mastered_count = _metrics()
        current_code = cell_to_code.get((game.player_x, game.player_y), 0)
        actions = get_available_actions(game, include_bidirectional_for_surface=True)

        active_segments = _collect_active_segments(game, actions, transit_specs)

        map_rect = pygame.Rect(24, 100, 380, 380)
        _draw_map_panel(
            screen=screen,
            rect=map_rect,
            code_to_cell=code_to_cell,
            transit_specs=transit_specs,
            current_code=current_code,
            active_segments=active_segments,
            station_icons_mini=station_icons_mini,
            icon_max_side=icon_max_side,
        )

        text_left = map_rect.right + 18
        text_w = WINDOW_W - text_left - 24
        y = 16
        y = _draw_wrapped(screen, font_lg, "Practice3：自由探索覆盖训练", text_left, y, text_w, (225, 230, 255))
        y += 6
        y = _draw_wrapped(
            screen,
            font_sm,
            f"被试: {participant_id}    地图: {map_id}    轮次: {round_index}/{rounds_total}",
            text_left,
            y,
            text_w,
            (180, 190, 210),
        )
        y += 4
        y = _draw_wrapped(
            screen,
            font_sm,
            f"当前站点: {code_to_station_name(current_code)}  (编码 {current_code})",
            text_left,
            y,
            text_w,
            (180, 230, 180),
        )
        y += 8
        y = _draw_wrapped(
            screen,
            font_md,
            f"探索率(>=1次): {explored_rate:.0%}    覆盖达标(>={min_visits}次): {mastery_rate:.0%}  [{mastered_count}/{len(all_codes)}]",
            text_left,
            y,
            text_w,
            (220, 220, 200),
        )
        y += 8
        y = _draw_wrapped(
            screen,
            font_sm,
            f"规则：每个点至少访问 {min_visits} 次；当前轮达标后进入下一轮，共 {rounds_total} 轮。",
            text_left,
            y,
            text_w,
            (190, 190, 210),
        )
        y += 12

        if phase == "running":
            for e in events:
                if e.type != pygame.KEYDOWN:
                    continue
                chosen_idx: Optional[int] = None
                mapping = _KEY_TO_TRANSIT_MODE.get(e.key)
                if mapping is not None:
                    mode, want_dir = mapping
                    chosen_idx = _pick_action_idx_by_mode(actions, game, mode, want_dir)

                if chosen_idx is None:
                    continue
                action = actions[chosen_idx]
                prev_code = current_code
                ok = execute_action(game, action)
                if not ok:
                    continue
                new_code = cell_to_code.get((game.player_x, game.player_y), 0)
                if new_code > 0:
                    visit_counts[new_code] = visit_counts.get(new_code, 0) + 1
                step_counter += 1
                er, mr, _ = _metrics()
                step_logs.append(
                    StepLog(
                        round_index=round_index,
                        step_index=step_counter,
                        t_sec=round(time.time() - session_t0, 3),
                        from_code=prev_code,
                        to_code=new_code,
                        action_label=action[0],
                        action_key=action[1],
                        action_extra=action[2],
                        explore_rate=er,
                        mastery_rate=mr,
                    )
                )
                if mr >= 1.0:
                    _finish_round()
                    break

        if phase == "round_transition":
            y += 8
            y = _draw_wrapped(
                screen,
                font_md,
                f"第 {round_index - 1} 轮已完成，按 Enter 开始第 {round_index} 轮。",
                text_left,
                y,
                text_w,
                (140, 220, 140),
            )
            for e in events:
                if e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_SPACE):
                    phase = "running"
                    break

        if phase == "finished":
            y += 8
            y = _draw_wrapped(
                screen,
                font_md,
                f"练习完成：共 {rounds_total} 轮均达成每点 >= {min_visits} 次访问。",
                text_left,
                y,
                text_w,
                (140, 220, 140),
            )
            y = _draw_wrapped(screen, font_sm, "按 ESC 退出并保存结果。", text_left, y + 6, text_w, (170, 170, 190))

        y += 12
        y = _draw_wrapped(
            screen,
            font_md,
            "可选动作按键：公交(Q/E)  地铁(A/D)  环线(W)",
            text_left,
            y,
            text_w,
            (210, 210, 225),
        )
        y += 8
        if not actions:
            y = _draw_wrapped(screen, font_sm, "（当前站点无可用交通动作）", text_left, y, text_w, (170, 170, 185))
        else:
            modes = list(getattr(game, "transit_modes", []) or [])
            for i, (label, _action_key, extra) in enumerate(actions):
                mode = "metro"
                if extra is not None:
                    li = int(extra) if not isinstance(extra, int) else extra
                    if 0 <= li < len(modes):
                        mode = modes[li]
                key_letter = _key_label_for_action(mode, _action_key)
                text = f"[{key_letter}] {_clean_option_label(label)}"
                y = _draw_wrapped(screen, font_sm, text, text_left + 12, y, text_w - 12, (225, 220, 205))
                y += 2

        pygame.display.flip()
        clock.tick(30)

    payload = {
        "schema": "navigation6_practice3",
        "participant_id": participant_id,
        "session_start_iso": datetime.fromtimestamp(session_t0).isoformat(),
        "session_end_iso": datetime.now().isoformat(),
        "duration_sec": round(time.time() - session_t0, 3),
        "map_file": os.path.basename(map_path),
        "map_id": map_id,
        "rounds_total": rounds_total,
        "min_visits": min_visits,
        "round_summaries": round_summaries,
        "steps": [s.__dict__ for s in step_logs],
    }
    out = _save_result(practice_raw_dir(), payload)
    print(f"Practice3 数据已保存: {out}")

    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
