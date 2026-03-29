#!/usr/bin/env python3
"""
Navigation6 练习阶段 v4：自由探索 + 分支可视化。

与 practice_main3 的唯一区别：
- 不展示整张地图；
- 只展示当前站点 + 当前可执行动作分支（彩色线）+ 末端问号。
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
MIN_TRIAL_DURATION_SEC = 5 * 60

_KEY_TO_TRANSIT_MODE = {
    pygame.K_q: ("bus", "next"),
    pygame.K_e: ("bus", "prev"),
    pygame.K_a: ("light_rail", "next"),
    pygame.K_d: ("light_rail", "prev"),
    pygame.K_w: ("metro", "next"),
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


def _font(size: int) -> pygame.font.Font:
    try:
        return pygame.font.SysFont("SimHei", size)
    except Exception:
        return pygame.font.SysFont("arial", size)


def _line_color(mode: str) -> Tuple[int, int, int]:
    if mode == "bus":
        return COLOR_TRANSIT_BUS
    if mode == "light_rail":
        return COLOR_TRANSIT_LIGHT_RAIL
    if mode == "metro":
        return COLOR_TRANSIT_METRO
    return COLOR_TRANSIT_UNKNOWN


def _new_game(map_id: str, map_path: str, seed: Optional[int]) -> GameNavigation6:
    if seed is not None:
        random.seed(seed)
    rec = RLDataRecorder("Navigation6_Practice4", task_type="Navigation6_Practice4")
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


def _key_label_for_action(mode: str, action_key: str) -> str:
    if mode == "bus":
        return "Q" if action_key in ("instant_transit_next", "instant_subway_next") else "E"
    if mode == "light_rail":
        return "A" if action_key in ("instant_transit_next", "instant_subway_next") else "D"
    if mode == "metro":
        return "W"
    return "?"


def _clean_option_label(label: str) -> str:
    out = re.sub(r"（[^）]*）", "", label)
    out = re.sub(r"\([^)]*\)", "", out)
    return " ".join(out.split())


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
    filename = f"navigation6_practice4_{pid}_{ts}.json"
    out = os.path.join(path, filename)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return out


def _build_branch_specs(
    game: GameNavigation6,
    actions: List[Tuple[str, str, Optional[Union[str, int]]]],
) -> List[Dict[str, Any]]:
    """
    每个可执行动作对应一个分支。
    返回项含：action_idx, mode, action_key, color。
    """
    out: List[Dict[str, Any]] = []
    modes = list(getattr(game, "transit_modes", []) or [])
    for i, (_label, action_key, extra) in enumerate(actions):
        if extra is None:
            continue
        li = int(extra) if not isinstance(extra, int) else extra
        mode = modes[li] if 0 <= li < len(modes) else "metro"
        out.append(
            {
                "action_idx": i,
                "mode": mode,
                "action_key": action_key,
                "color": _line_color(mode),
            }
        )
    return out


def _draw_branch_panel(
    screen: pygame.Surface,
    rect: pygame.Rect,
    current_code: int,
    branch_specs: List[Dict[str, Any]],
    station_icons_mini: Dict[int, pygame.Surface],
    icon_max_side: int,
) -> None:
    pygame.draw.rect(screen, (36, 38, 46), rect, border_radius=10)
    pygame.draw.rect(screen, (70, 74, 90), rect, 1, border_radius=10)

    cx = rect.centerx
    cy = rect.centery + 8

    if not branch_specs:
        ic = station_icons_mini.get(current_code)
        if ic is not None:
            draw_ic = _scale_surface_uniform_to_max_side(ic, max(8, int(icon_max_side * 1.55)))
            ir = draw_ic.get_rect(center=(cx, cy))
            screen.blit(draw_ic, ir)
        else:
            pygame.draw.circle(screen, (210, 220, 240), (cx, cy), 14)
        txt = _font(16).render("当前站点无可执行动作", True, (170, 175, 188))
        tr = txt.get_rect(center=(cx, rect.bottom - 24))
        screen.blit(txt, tr)
        return

    # 均匀扇形分布分支（上半区），避免遮挡中心图标
    n = len(branch_specs)
    start_deg = -150.0
    end_deg = -30.0
    if n == 1:
        angles = [(-90.0)]
    else:
        step = (end_deg - start_deg) / (n - 1)
        angles = [start_deg + i * step for i in range(n)]

    len1 = min(rect.w, rect.h) * 0.17
    len2 = min(rect.w, rect.h) * 0.22
    fnt_q = _font(24)
    fnt_i = _font(13)

    for spec, deg in zip(branch_specs, angles):
        rad = math.radians(deg)
        ux, uy = math.cos(rad), math.sin(rad)
        x1, y1 = cx + ux * len1, cy + uy * len1
        x2, y2 = cx + ux * (len1 + len2), cy + uy * (len1 + len2)
        color = spec["color"]

        pygame.draw.line(screen, color, (cx, cy), (int(x1), int(y1)), 4)
        pygame.draw.line(screen, color, (int(x1), int(y1)), (int(x2), int(y2)), 4)
        pygame.draw.circle(screen, color, (int(x2), int(y2)), 14)

        # 末端问号
        q_surf = fnt_q.render("?", True, (26, 28, 34))
        q_rect = q_surf.get_rect(center=(int(x2), int(y2) - 1))
        screen.blit(q_surf, q_rect)

        # 分支编号（对应右侧列表顺序）
        idx_text = fnt_i.render(str(spec["action_idx"] + 1), True, (230, 232, 238))
        idx_rect = idx_text.get_rect(center=(int(x1), int(y1)))
        screen.blit(idx_text, idx_rect)

    # 当前站点图片后绘制，确保覆盖在线条之上
    ic = station_icons_mini.get(current_code)
    if ic is not None:
        draw_ic = _scale_surface_uniform_to_max_side(ic, max(8, int(icon_max_side * 1.55)))
        ir = draw_ic.get_rect(center=(cx, cy))
        screen.blit(draw_ic, ir)
    else:
        pygame.draw.circle(screen, (210, 220, 240), (cx, cy), 14)


def main() -> None:
    parser = argparse.ArgumentParser(description="Navigation6 练习 v4：自由探索分支可视化")
    parser.add_argument("--participant_id", "-p", type=str, default=None)
    parser.add_argument("--seed", "-s", type=int, default=None)
    parser.add_argument("--map", "-m", type=str, default=DEFAULT_MAP_FILE, help=f"地图文件名，默认 {DEFAULT_MAP_FILE}")
    parser.add_argument("--rounds", type=int, default=2, help="练习轮数（默认 2）")
    parser.add_argument("--min-visits", type=int, default=2, help="每点至少访问次数（默认 2）")
    parser.add_argument("--min-trial-seconds", type=int, default=MIN_TRIAL_DURATION_SEC, help="每轮最短练习时长（秒，默认 300）")
    args = parser.parse_args()

    participant_id = args.participant_id or os.environ.get("NAVIGATION6_PRACTICE4_PARTICIPANT_ID") or ""

    rounds_total = max(1, int(args.rounds))
    min_visits = max(1, int(args.min_visits))
    min_trial_seconds = max(1, int(args.min_trial_seconds))
    selected_map_file = args.map

    pygame.init()
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption("Navigation6 Practice4 - 自由探索分支可视化")
    clock = pygame.time.Clock()
    font_lg = _font(24)
    font_md = _font(18)
    font_sm = _font(16)
    icon_max_side = START_ICON_MAX_PX
    station_icons_raw = _load_raw_station_icons()
    station_icons_mini = _scale_station_icon_dict(station_icons_raw, MINI_MAP_STATION_ICON_MAX)

    def _prompt_participant_id(initial_value: str) -> Optional[str]:
        text = initial_value
        while True:
            screen.fill((28, 30, 36))
            y = 40
            y = _draw_wrapped(screen, font_lg, "被试编号", 28, y, WINDOW_W - 56, (230, 235, 255))
            y += 6
            y = _draw_wrapped(
                screen,
                font_sm,
                "请输入唯一编号（示例：P001）  ·  Enter确认  Esc退出",
                28,
                y,
                WINDOW_W - 56,
                (190, 198, 214),
            )
            y += 14
            box = pygame.Rect(28, y, WINDOW_W - 56, 52)
            pygame.draw.rect(screen, (42, 46, 56), box, border_radius=8)
            pygame.draw.rect(screen, (92, 98, 118), box, 2, border_radius=8)
            shown = text if text else "在此输入编号"
            color = (232, 236, 245) if text else (150, 155, 168)
            surf = font_md.render(shown, True, color)
            screen.blit(surf, (box.x + 14, box.y + 14))
            pygame.display.flip()

            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    return None
                if e.type != pygame.KEYDOWN:
                    continue
                if e.key == pygame.K_ESCAPE:
                    return None
                if e.key == pygame.K_RETURN:
                    if text.strip():
                        return text.strip()
                    continue
                if e.key == pygame.K_BACKSPACE:
                    text = text[:-1]
                    continue
                if e.unicode and e.unicode.isprintable():
                    text += e.unicode
            clock.tick(30)

    def _prompt_map_choice(initial_map: str) -> Optional[str]:
        if not EXPERIMENT_MAPS:
            return None
        idx = 0
        initial_name = os.path.basename(initial_map) if initial_map else ""
        for i, (_name, filename) in enumerate(EXPERIMENT_MAPS):
            if filename == initial_name:
                idx = i
                break
        while True:
            screen.fill((28, 30, 36))
            y = 30
            y = _draw_wrapped(screen, font_lg, "选择地图", 28, y, WINDOW_W - 56, (230, 235, 255))
            y += 6
            y = _draw_wrapped(
                screen,
                font_sm,
                "上下键切换  ·  Enter确认  ·  数字键1-9直选",
                28,
                y,
                WINDOW_W - 56,
                (190, 198, 214),
            )
            y += 12
            for i, (name, filename) in enumerate(EXPERIMENT_MAPS):
                selected = i == idx
                c = (240, 245, 170) if selected else (215, 220, 235)
                prefix = ">" if selected else " "
                row = f"{prefix} {i + 1}. {name}  [{filename}]"
                y = _draw_wrapped(screen, font_sm, row, 38, y, WINDOW_W - 76, c)
                y += 3
            y += 10
            _draw_wrapped(screen, font_sm, "Esc 退出", 28, y, WINDOW_W - 56, (150, 155, 168))
            pygame.display.flip()

            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    return None
                if e.type != pygame.KEYDOWN:
                    continue
                if e.key == pygame.K_ESCAPE:
                    return None
                if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    return EXPERIMENT_MAPS[idx][1]
                if e.key == pygame.K_UP:
                    idx = (idx - 1) % len(EXPERIMENT_MAPS)
                elif e.key == pygame.K_DOWN:
                    idx = (idx + 1) % len(EXPERIMENT_MAPS)
                elif pygame.K_1 <= e.key <= pygame.K_9:
                    n = e.key - pygame.K_1
                    if 0 <= n < len(EXPERIMENT_MAPS):
                        idx = n
                        return EXPERIMENT_MAPS[idx][1]
            clock.tick(30)

    pid = _prompt_participant_id(participant_id)
    if pid is None:
        pygame.quit()
        sys.exit(0)
    participant_id = pid

    chosen_map_file = _prompt_map_choice(selected_map_file)
    if chosen_map_file is None:
        pygame.quit()
        sys.exit(0)
    selected_map_file = chosen_map_file
    map_path = resolve_map_path(selected_map_file)
    map_id = os.path.splitext(os.path.basename(map_path))[0]
    if not os.path.exists(map_path):
        print(f"地图文件不存在: {map_path}")
        pygame.quit()
        sys.exit(1)

    session_t0 = time.time()
    phase = "running"
    running = True
    round_index = 1
    intro_done = False

    step_logs: List[StepLog] = []
    round_summaries: List[Dict[str, Any]] = []
    round_started_at = time.time()
    step_counter = 0

    game = _new_game(map_id, map_path, args.seed)
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
        nonlocal round_index, visit_counts, game, cell_to_code, code_to_cell, round_started_at, step_counter, phase
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

        if not intro_done:
            screen.fill((28, 30, 36))
            title = _font(28)
            body = _font(18)
            y = 34
            y = _draw_wrapped(screen, title, "练习说明", 28, y, WINDOW_W - 56, (230, 235, 255))
            y += 10
            y = _draw_wrapped(
                screen,
                body,
                "请在自由探索中尽量记住：站点之间如何相连，以及不同交通方式会把你带向哪里。",
                28,
                y,
                WINDOW_W - 56,
                (205, 210, 225),
            )
            y += 8
            y = _draw_wrapped(
                screen,
                body,
                f"本练习共 {rounds_total} 轮；每轮需同时满足：",
                28,
                y,
                WINDOW_W - 56,
                (205, 210, 225),
            )
            y += 6
            y = _draw_wrapped(
                screen,
                body,
                f"1) 每个站点访问次数 >= {min_visits}",
                44,
                y,
                WINDOW_W - 72,
                (220, 220, 200),
            )
            y += 2
            y = _draw_wrapped(
                screen,
                body,
                f"2) 单轮练习时长 >= {min_trial_seconds // 60} 分钟",
                44,
                y,
                WINDOW_W - 72,
                (220, 220, 200),
            )
            y += 14
            _draw_wrapped(
                screen,
                body,
                "Enter/Space 开始  ·  Esc 退出",
                28,
                y,
                WINDOW_W - 56,
                (150, 185, 220),
            )
            pygame.display.flip()
            for e in events:
                if e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_SPACE):
                    intro_done = True
                    round_started_at = time.time()
            clock.tick(30)
            continue

        explored_rate, mastery_rate, mastered_count = _metrics()
        elapsed_trial_sec = max(0.0, time.time() - round_started_at)
        time_ok = elapsed_trial_sec >= float(min_trial_seconds)
        mastery_ok = mastery_rate >= 1.0
        current_code = cell_to_code.get((game.player_x, game.player_y), 0)
        actions = get_available_actions(game, include_bidirectional_for_surface=True)
        branch_specs = _build_branch_specs(game, actions)

        panel_rect = pygame.Rect(24, 100, 380, 380)
        _draw_branch_panel(
            screen=screen,
            rect=panel_rect,
            current_code=current_code,
            branch_specs=branch_specs,
            station_icons_mini=station_icons_mini,
            icon_max_side=icon_max_side,
        )

        text_left = panel_rect.right + 18
        text_w = WINDOW_W - text_left - 24
        y = 18
        y = _draw_wrapped(screen, font_lg, "Practice4 自由探索", text_left, y, text_w, (225, 230, 255))
        y += 4
        y = _draw_wrapped(
            screen,
            font_sm,
            f"被试 {participant_id}  |  地图 {map_id}  |  轮次 {round_index}/{rounds_total}",
            text_left,
            y,
            text_w,
            (180, 190, 210),
        )
        y += 6
        y = _draw_wrapped(
            screen,
            font_sm,
            f"当前站点：{code_to_station_name(current_code)}",
            text_left,
            y,
            text_w,
            (180, 230, 180),
        )
        y += 10
        y = _draw_wrapped(
            screen,
            font_md,
            f"探索率 {explored_rate:.0%}  |  覆盖达标 {mastery_rate:.0%}  ({mastered_count}/{len(all_codes)})",
            text_left,
            y,
            text_w,
            (220, 220, 200),
        )
        y += 6
        y = _draw_wrapped(
            screen,
            font_sm,
            f"进下一轮条件：每点>= {min_visits} 次 且 本轮时长>= {min_trial_seconds // 60} 分钟",
            text_left,
            y,
            text_w,
            (190, 190, 210),
        )
        y += 8
        y = _draw_wrapped(
            screen,
            font_sm,
            f"本轮时长 {int(elapsed_trial_sec)//60:02d}:{int(elapsed_trial_sec)%60:02d} / {min_trial_seconds//60:02d}:{min_trial_seconds%60:02d}"
            f"  |  时间 {'达标' if time_ok else '未达标'}  |  覆盖 {'达标' if mastery_ok else '未达标'}",
            text_left,
            y,
            text_w,
            (200, 205, 220),
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
                # 仅当覆盖条件和时长条件同时满足，才进入下一轮
                current_elapsed = max(0.0, time.time() - round_started_at)
                if mr >= 1.0 and current_elapsed >= float(min_trial_seconds):
                    _finish_round()
                    break

        if phase == "round_transition":
            y += 8
            y = _draw_wrapped(
                screen,
                font_md,
                f"第 {round_index - 1} 轮完成  ·  Enter 开始第 {round_index} 轮",
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
                f"练习完成：{rounds_total} 轮均达标",
                text_left,
                y,
                text_w,
                (140, 220, 140),
            )
            y = _draw_wrapped(screen, font_sm, "Esc 退出并保存结果", text_left, y + 6, text_w, (170, 170, 190))

        y += 12
        y = _draw_wrapped(
            screen,
            font_md,
            "按键：公交 Q/E  ·  轻轨 A/D  ·  高铁 W",
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
            for label, action_key, extra in actions:
                mode = "metro"
                if extra is not None:
                    li = int(extra) if not isinstance(extra, int) else extra
                    if 0 <= li < len(modes):
                        mode = modes[li]
                key_letter = _key_label_for_action(mode, action_key)
                text = f"[{key_letter}] {_clean_option_label(label)}"
                y = _draw_wrapped(screen, font_sm, text, text_left + 12, y, text_w - 12, (225, 220, 205))
                y += 2

        pygame.display.flip()
        clock.tick(30)

    payload = {
        "schema": "navigation6_practice4",
        "participant_id": participant_id,
        "session_start_iso": datetime.fromtimestamp(session_t0).isoformat(),
        "session_end_iso": datetime.now().isoformat(),
        "duration_sec": round(time.time() - session_t0, 3),
        "map_file": os.path.basename(map_path),
        "map_id": map_id,
        "rounds_total": rounds_total,
        "min_visits": min_visits,
        "min_trial_seconds": min_trial_seconds,
        "round_summaries": round_summaries,
        "steps": [s.__dict__ for s in step_logs],
    }
    out = _save_result(practice_raw_dir(), payload)
    print(f"Practice4 数据已保存: {out}")

    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
