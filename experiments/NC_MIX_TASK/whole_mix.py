#!/usr/bin/env python3
"""
完整混合实验入口（全屏）。

流程：
  1. 收集被试编号 + 选择实验顺序 (navigation-first / crafting-first)
  2. 导航练习指导语 → 导航练习（不存数据）
  3. 合成练习指导语 → 合成练习（不存数据）
  4. 正式测试（5 session，数据存储与 run_mix 一致）
"""
from __future__ import annotations

import json
import math
import os
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from common.bootstrap import ensure_project_root_on_path

ensure_project_root_on_path()

import pygame

# ── 导航相关 ─────────────────────────────────────────────
from navigation.app.experiment.main import (
    EXPERIMENT_MAPS,
    build_position_encoding,
    execute_action,
    get_available_actions,
)
from navigation.app.experiment.game import GameNavigation6
from navigation.app.common.station_names import code_to_station_name, draw_station_shape
from navigation.app.practice.practice.practice_ui import (
    MINI_MAP_STATION_ICON_MAX,
    START_ICON_MAX_PX,
    _load_raw_station_icons,
    _scale_station_icon_dict,
    _scale_surface_uniform_to_max_side,
)
from navigation.app.paths import resolve_map_path
from navigation.main2 import (
    _MODE_DIR_COLORS,
    _MODE_COLORS,
    _VisGraphWidget,
    _get_available_mode_dirs,
    _draw_legend,
)
from shared.common.recorder import RLDataRecorder as NavRecorder

# ── 合成相关 ─────────────────────────────────────────────
from crafting.src.bottle_images import BottleImageCache, collect_bottle_asset_dirs
from crafting.src.config_io_crafting import load_trial_list
from crafting.src.game_crafting import GameCrafting
from crafting.src.main_crafting import (
    ACTION_KEYS,
    WINDOW_H as CRAFT_WINDOW_H,
    WINDOW_W as CRAFT_WINDOW_W,
    _action_key_symbol,
    _find_action_by_key,
    _font as _craft_font,
    _potion_index_for_action_key,
    ACTION_BTN_ERROR_S,
    ACTION_BTN_HIGHLIGHT_S,
    draw_ui as craft_draw_ui,
    layout_rects as craft_layout_rects,
)
from crafting.src.map_select_crafting import resolve_transition_map_cli_path
from crafting.src.recorder import RLDataRecorder as CraftRecorder
from crafting.src.rules_io_crafting import load_rule_data_with_transition_map
from crafting.src.stone_space import STONE_IDS
from crafting.src.stone_images import StoneImageCache, collect_stone_asset_dirs

# ── 测试流程（复用 run_mix_experiment） ──────────────────
from crafting.src.session_runner import run_crafting_session
from navigation.session_runner import run_navigation_session
from mix.mix_session_guidance import run_mix_session_guidance_screen
from mix.preflight_equivalence import run_equivalence_preflight
from mix.schedule import build_session_schedule, save_schedule

try:
    import pandas as pd
    _HAS_PANDAS = True
except ImportError:
    _HAS_PANDAS = False

# ─────────────────────────────────────────────────────────
# 常量
# ─────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent
DEFAULT_NAV_MAP = "map_1774095558.json"
DEFAULT_TRANSITION_MAP = "data/maps/builtin_map_a.json"
NAV_PRACTICE_ROUNDS = 2
NAV_MIN_VISITS = 2
NAV_MIN_TRIAL_SECONDS = 5 * 60
CRAFT_PRACTICE_ROUNDS = 2
CRAFT_MIN_VISITS = 2
CRAFT_MIN_TRIAL_SECONDS = 5 * 60

_KEY_TO_TRANSIT_MODE = {
    pygame.K_q: ("bus", "next"),
    pygame.K_e: ("bus", "prev"),
    pygame.K_a: ("light_rail", "next"),
    pygame.K_d: ("light_rail", "prev"),
    pygame.K_w: ("metro", "next"),
}


# ─────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────
def _font(size: int) -> pygame.font.Font:
    try:
        return pygame.font.SysFont("SimHei", size)
    except Exception:
        return pygame.font.SysFont("arial", size)


def _draw_wrapped(
    screen: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    x: int,
    y: int,
    width: int,
    color: Tuple[int, int, int],
) -> int:
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


def _resolve_nav_map(arg: str) -> Path:
    p = Path(arg)
    if p.is_absolute() and p.is_file():
        return p
    candidate = _ROOT / "navigation" / "assets" / "maps" / arg
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(f"找不到导航地图: {arg}")


# ─────────────────────────────────────────────────────────
# 1) 被试编号 + 顺序选择
# ─────────────────────────────────────────────────────────
def _run_participant_and_order_screen(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
) -> Optional[Tuple[str, str]]:
    """
    收集被试编号与实验顺序。
    返回 (participant_id, order) 或 None（退出）。
    order: "navigation-first" | "crafting-first"
    """
    W, H = screen.get_size()
    margin = 40
    text_w = W - margin * 2
    text = ""
    order_idx = 0  # 0 = navigation-first, 1 = crafting-first
    orders = ["navigation-first", "crafting-first"]
    order_labels = ["导航优先 (navigation-first)", "合成优先 (crafting-first)"]
    phase = "id"  # "id" -> "order"

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type != pygame.KEYDOWN:
                continue
            if event.key == pygame.K_ESCAPE:
                return None

            if phase == "id":
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    if text.strip():
                        phase = "order"
                    continue
                if event.key == pygame.K_BACKSPACE:
                    text = text[:-1]
                    continue
                ch = event.unicode
                if ch and ch.isprintable() and len(text) < 48:
                    text += ch
            elif phase == "order":
                if event.key in (pygame.K_UP, pygame.K_DOWN):
                    order_idx = 1 - order_idx
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    return (text.strip(), orders[order_idx])
                elif event.key == pygame.K_BACKSPACE:
                    phase = "id"

        screen.fill((28, 31, 38))

        if phase == "id":
            y = H // 4
            y = _draw_wrapped(screen, _font(30), "请输入被试编号", margin, y, text_w, (220, 228, 245))
            y += 8
            y = _draw_wrapped(
                screen, _font(18), "完成后按 Enter 继续；Esc 退出",
                margin, y, text_w, (130, 142, 168),
            )
            y += 20
            box = pygame.Rect(margin, y, text_w, 52)
            pygame.draw.rect(screen, (48, 52, 62), box, border_radius=10)
            pygame.draw.rect(screen, (96, 165, 250), box, 2, border_radius=10)
            display = text + ("|" if (pygame.time.get_ticks() // 530) % 2 else "")
            surf = _font(24).render(display if display else " ", True, (200, 206, 220))
            screen.blit(surf, (box.x + 14, box.centery - surf.get_height() // 2))

        elif phase == "order":
            y = H // 4
            y = _draw_wrapped(screen, _font(30), f"被试：{text.strip()}", margin, y, text_w, (220, 228, 245))
            y += 12
            y = _draw_wrapped(
                screen, _font(20), "请选择实验顺序（↑↓切换，Enter 确认，Backspace 返回）",
                margin, y, text_w, (190, 198, 214),
            )
            y += 20
            for i, label in enumerate(order_labels):
                selected = i == order_idx
                color = (240, 245, 170) if selected else (200, 206, 220)
                prefix = "▶ " if selected else "   "
                y = _draw_wrapped(screen, _font(22), f"{prefix}{label}", margin + 20, y, text_w - 40, color)
                y += 8

        pygame.display.flip()
        clock.tick(60)


# ─────────────────────────────────────────────────────────
# 2) 导航练习
# ─────────────────────────────────────────────────────────
def _nav_practice_guidance(screen: pygame.Surface, clock: pygame.time.Clock) -> bool:
    """导航练习指导语，Enter/Space 进入练习，Esc 退出。"""
    W, H = screen.get_size()
    margin = 40
    text_w = W - margin * 2
    while True:
        screen.fill((28, 31, 38))
        y = 36
        y = _draw_wrapped(screen, _font(28), "导航练习 · 指导语", margin, y, text_w, (230, 235, 255))
        y += 14
        y = _draw_wrapped(
            screen, _font(18),
            "本阶段为导航练习，不计入正式成绩。请在自由探索中尽量记住站点之间的连通关系，"
            "以及不同交通方式会把你带向哪里。",
            margin, y, text_w, (205, 210, 225),
        )
        y += 10
        y = _draw_wrapped(
            screen, _font(18),
            "操作：公交前进 Q、后退 E；地铁前进 A、后退 D；环线 W。"
            "每种交通工具有深色（向前）和浅色（向后）两条线，表示不同行进方向。",
            margin, y, text_w, (205, 210, 225),
        )
        y += 10
        y = _draw_wrapped(
            screen, _font(18),
            f"练习共 {NAV_PRACTICE_ROUNDS} 轮，满足以下任一条件即可进入下一轮：",
            margin, y, text_w, (210, 215, 200),
        )
        y += 4
        y = _draw_wrapped(
            screen, _font(18),
            f"  1) 每个站点均被探索过（探索率 100%）",
            margin + 20, y, text_w - 20, (220, 220, 200),
        )
        y += 2
        y = _draw_wrapped(
            screen, _font(18),
            f"  2) 单轮练习时长 ≥ {NAV_MIN_TRIAL_SECONDS // 60} 分钟",
            margin + 20, y, text_w - 20, (220, 220, 200),
        )
        y += 16
        _draw_wrapped(
            screen, _font(16),
            "Enter / 空格 开始练习  ·  Esc 退出",
            margin, H - 50, text_w, (150, 185, 220),
        )
        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return True
        clock.tick(60)


def _pick_action_idx_by_mode(
    actions: list, game: GameNavigation6, mode: str, want_dir: str,
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


def _run_nav_practice(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    nav_map_path: str,
) -> bool:
    """运行导航练习（不存数据）。完成返回 True，用户退出返回 False。"""
    W, H = screen.get_size()
    margin = 28
    text_w = W - margin * 2

    map_id = os.path.splitext(os.path.basename(nav_map_path))[0]
    font_lg = _font(26)
    font_md = _font(20)
    font_sm = _font(16)

    vis_widget = _VisGraphWidget()

    def new_game():
        rec = NavRecorder("_practice_", task_type="Navigation6_Practice_Whole")
        return GameNavigation6(
            rec,
            map_type=map_id,
            target_entropy=0.5,
            enable_experiment=False,
            custom_map_file=nav_map_path,
        )

    game = new_game()
    cell_to_code, code_to_cell, _ = build_position_encoding(game)
    all_codes = sorted(code_to_cell.keys())
    if not all_codes:
        return True

    visit_counts: Dict[int, int] = {c: 0 for c in all_codes}
    cur_code = cell_to_code.get((game.player_x, game.player_y), 0)
    if cur_code > 0:
        visit_counts[cur_code] += 1

    round_index = 1
    round_started_at = time.time()
    step_counter = 0
    phase = "running"  # running | round_transition | finished
    running = True

    def metrics():
        n = len(all_codes)
        explored = sum(1 for c in all_codes if visit_counts[c] >= 1)
        mastered = sum(1 for c in all_codes if visit_counts[c] >= NAV_MIN_VISITS)
        return explored / n, mastered / n, mastered

    def finish_round():
        nonlocal round_index, visit_counts, game, cell_to_code, code_to_cell
        nonlocal round_started_at, step_counter, phase
        if round_index >= NAV_PRACTICE_ROUNDS:
            phase = "finished"
            return
        round_index += 1
        step_counter = 0
        round_started_at = time.time()
        game = new_game()
        cell_to_code, code_to_cell, _ = build_position_encoding(game)
        visit_counts = {c: 0 for c in all_codes}
        nc = cell_to_code.get((game.player_x, game.player_y), 0)
        if nc > 0:
            visit_counts[nc] += 1
        phase = "round_transition"

    while running:
        events = pygame.event.get()
        for e in events:
            if e.type == pygame.QUIT:
                return False
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                if phase == "finished":
                    return True
                return False

        screen.fill((28, 30, 36))
        current_code = cell_to_code.get((game.player_x, game.player_y), 0)
        available_mode_dirs = _get_available_mode_dirs(game)
        explored_rate, mastery_rate, mastered_count = metrics()
        elapsed = max(0.0, time.time() - round_started_at)
        time_ok = elapsed >= float(NAV_MIN_TRIAL_SECONDS)
        mastery_ok = mastery_rate >= 1.0

        # ── 左侧可视化组件（与测试阶段完全一致） ──
        vis_top = 80
        vis_size = min(W // 2 - margin, H - vis_top - 40)
        vis_rect = pygame.Rect(margin, vis_top, vis_size, vis_size)
        vis_widget.set_rect(vis_rect)
        hover_pos = pygame.mouse.get_pos()
        vis_widget.draw(screen, font_sm, current_code, available_mode_dirs, hover_pos=hover_pos)

        # ── 右侧信息 ──
        tx = vis_rect.right + 24
        tw = W - tx - margin
        y = 24
        y = _draw_wrapped(screen, font_lg, "导航练习 · 自由探索", tx, y, tw, (225, 230, 255))
        y += 6
        y = _draw_wrapped(
            screen, font_sm,
            f"轮次 {round_index}/{NAV_PRACTICE_ROUNDS}",
            tx, y, tw, (180, 190, 210),
        )
        y += 8
        y = _draw_wrapped(
            screen, font_sm,
            f"当前站点：{code_to_station_name(current_code)}",
            tx, y, tw, (180, 230, 180),
        )
        y += 10
        y = _draw_wrapped(
            screen, font_md,
            f"探索率 {explored_rate:.0%}  ({mastered_count}/{len(all_codes)} 站已探索)",
            tx, y, tw, (220, 220, 200),
        )
        y += 6
        em, es = int(elapsed) // 60, int(elapsed) % 60
        tm, ts = NAV_MIN_TRIAL_SECONDS // 60, NAV_MIN_TRIAL_SECONDS % 60
        y = _draw_wrapped(
            screen, font_sm,
            f"本轮时长 {em:02d}:{es:02d} / {tm:02d}:{ts:02d}"
            f"  ·  探索 {'✓' if explored_rate >= 1.0 else '✗'}  ·  时间 {'✓' if time_ok else '✗'}"
            f"  ·  任一✓即达标",
            tx, y, tw, (200, 205, 220),
        )

        if phase == "round_transition":
            y += 20
            _draw_wrapped(
                screen, font_md,
                f"第 {round_index - 1} 轮完成  ·  Enter 开始第 {round_index} 轮",
                tx, y, tw, (140, 220, 140),
            )
            for e in events:
                if e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_SPACE):
                    phase = "running"

        elif phase == "finished":
            y += 20
            _draw_wrapped(
                screen, font_md,
                f"导航练习完成：{NAV_PRACTICE_ROUNDS} 轮均达标",
                tx, y, tw, (140, 220, 140),
            )
            y += 4
            _draw_wrapped(screen, font_sm, "按 Enter / 空格 继续", tx, y, tw, (170, 170, 190))
            for e in events:
                if e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return True

        elif phase == "running":
            # 鼠标点击支持
            for e in events:
                if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    clicked = vis_widget.handle_click(e.pos)
                    if clicked:
                        mode, want_dir = clicked
                        actions = get_available_actions(game, include_bidirectional_for_surface=True)
                        chosen = _pick_action_idx_by_mode(actions, game, mode, want_dir)
                        if chosen is not None:
                            ok = execute_action(game, actions[chosen])
                            if ok:
                                vis_widget.start_animation(mode, want_dir)
                                new_code = cell_to_code.get((game.player_x, game.player_y), 0)
                                if new_code > 0:
                                    visit_counts[new_code] = visit_counts.get(new_code, 0) + 1
                                step_counter += 1
                                er, _, _ = metrics()
                                cur_el = max(0.0, time.time() - round_started_at)
                                if er >= 1.0 or cur_el >= float(NAV_MIN_TRIAL_SECONDS):
                                    finish_round()
                        else:
                            vis_widget.start_error_flash(mode, want_dir)

            # 键盘操作
            for e in events:
                if e.type != pygame.KEYDOWN:
                    continue
                mapping = _KEY_TO_TRANSIT_MODE.get(e.key)
                if mapping is None:
                    continue
                mode, want_dir = mapping
                actions = get_available_actions(game, include_bidirectional_for_surface=True)
                chosen = _pick_action_idx_by_mode(actions, game, mode, want_dir)
                if chosen is not None:
                    ok = execute_action(game, actions[chosen])
                    if ok:
                        vis_widget.start_animation(mode, want_dir)
                        new_code = cell_to_code.get((game.player_x, game.player_y), 0)
                        if new_code > 0:
                            visit_counts[new_code] = visit_counts.get(new_code, 0) + 1
                        step_counter += 1
                        er, _, _ = metrics()
                        cur_el = max(0.0, time.time() - round_started_at)
                        if er >= 1.0 or cur_el >= float(NAV_MIN_TRIAL_SECONDS):
                            finish_round()
                            break
                else:
                    vis_widget.start_error_flash(mode, want_dir)

            # 被动检查：即使没有新操作，条件满足也自动推进
            if phase == "running":
                er, _, _ = metrics()
                cur_el = max(0.0, time.time() - round_started_at)
                if er >= 1.0 or cur_el >= float(NAV_MIN_TRIAL_SECONDS):
                    finish_round()

        pygame.display.flip()
        clock.tick(60)

    return True


# ─────────────────────────────────────────────────────────
# 3) 合成练习
# ─────────────────────────────────────────────────────────
def _craft_practice_guidance(screen: pygame.Surface, clock: pygame.time.Clock) -> bool:
    """合成练习指导语。"""
    W, H = screen.get_size()
    margin = 40
    text_w = W - margin * 2
    while True:
        screen.fill((28, 31, 38))
        y = 36
        y = _draw_wrapped(screen, _font(28), "合成练习 · 指导语", margin, y, text_w, (230, 235, 255))
        y += 14
        y = _draw_wrapped(
            screen, _font(18),
            "本阶段为合成练习，不计入正式成绩。请自行尝试各种操作，观察石块状态如何变化，"
            "尽可能多地记住潜在的转化关系。",
            margin, y, text_w, (205, 210, 225),
        )
        y += 10
        y = _draw_wrapped(
            screen, _font(18),
            "操作：Q / E（药水 1 正向与逆向）、A / D（药水 2 正向与逆向）、W（药水 3）。"
            "按 R 可将当前状态重置为起始石块。",
            margin, y, text_w, (205, 210, 225),
        )
        y += 10
        y = _draw_wrapped(
            screen, _font(18),
            f"练习共 {CRAFT_PRACTICE_ROUNDS} 轮，满足以下任一条件即可进入下一轮：",
            margin, y, text_w, (210, 215, 200),
        )
        y += 4
        y = _draw_wrapped(
            screen, _font(18),
            f"  1) 九块石头均被到达过（探索率 100%）",
            margin + 20, y, text_w - 20, (220, 220, 200),
        )
        y += 2
        y = _draw_wrapped(
            screen, _font(18),
            f"  2) 单轮练习时长 ≥ {CRAFT_MIN_TRIAL_SECONDS // 60} 分钟",
            margin + 20, y, text_w - 20, (220, 220, 200),
        )
        y += 16
        _draw_wrapped(
            screen, _font(16),
            "Enter / 空格 开始练习  ·  Esc 退出",
            margin, H - 50, text_w, (150, 185, 220),
        )
        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return True
        clock.tick(60)


def _run_craft_practice(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    rules,
    img_cache: StoneImageCache,
    bottle_cache: BottleImageCache,
) -> bool:
    """运行合成练习（不存数据）。完成返回 True，退出返回 False。"""
    W, H = screen.get_size()
    craft_root = _ROOT / "crafting"
    default_trials = str(craft_root / "data" / "trials" / "practice_trial_list_v1.json")
    trial_list = load_trial_list(default_trials)

    recorder = CraftRecorder(participant_id="_practice_", task_type="Crafting_Practice_Whole")
    game = GameCrafting(
        recorder=recorder,
        rules=rules,
        trial_data=trial_list,
        practice_mode=True,
    )

    visit_counts: Dict[str, int] = {s: 0 for s in STONE_IDS}
    c0 = game.current_state_id
    if c0 in visit_counts:
        visit_counts[c0] += 1

    round_index = 1
    round_started_at = time.time()
    step_counter = 0
    phase = "running"
    running = True

    highlight_p1_until = 0.0
    highlight_p2_until = 0.0
    highlight_p3_until = 0.0
    error_p1_until = 0.0
    error_p2_until = 0.0
    error_p3_until = 0.0

    font_md = _craft_font(18)
    font_sm = _craft_font(16)

    def craft_metrics():
        n = len(STONE_IDS)
        explored = sum(1 for s in STONE_IDS if visit_counts.get(s, 0) >= 1)
        mastered = sum(1 for s in STONE_IDS if visit_counts.get(s, 0) >= CRAFT_MIN_VISITS)
        return explored / n, mastered / n, mastered

    def finish_round():
        nonlocal phase, round_index, visit_counts, round_started_at, step_counter
        if round_index >= CRAFT_PRACTICE_ROUNDS:
            phase = "finished"
            return
        round_index += 1
        step_counter = 0
        round_started_at = time.time()
        if not game.start_next_trial():
            phase = "finished"
            return
        visit_counts = {s: 0 for s in STONE_IDS}
        cs = game.current_state_id
        if cs in visit_counts:
            visit_counts[cs] += 1
        phase = "round_transition"

    while running:
        now = time.monotonic()
        lit_p1 = now < highlight_p1_until
        lit_p2 = now < highlight_p2_until
        lit_p3 = now < highlight_p3_until
        err_p1 = now < error_p1_until
        err_p2 = now < error_p2_until
        err_p3 = now < error_p3_until

        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                if phase == "finished":
                    return True
                return False

        # ── 先处理按键事件，再绘制，避免额外 1 帧延迟 ──
        if phase == "running":
            for event in events:
                if event.type != pygame.KEYDOWN:
                    continue
                if event.key == pygame.K_r:
                    prev = game.current_state_id
                    if game.clear_operation_slot():
                        nxt = game.current_state_id
                        if nxt in visit_counts:
                            visit_counts[nxt] += 1
                        step_counter += 1
                        er, _, _ = craft_metrics()
                        cur_el = max(0.0, time.time() - round_started_at)
                        if er >= 1.0 or cur_el >= float(CRAFT_MIN_TRIAL_SECONDS):
                            finish_round()
                            break
                    continue

                ak = None
                if event.key in ACTION_KEYS:
                    ak = event.key
                if ak is None and hasattr(event, "unicode") and event.unicode:
                    _TEXT_TO_KEY = {
                        "q": pygame.K_q, "e": pygame.K_e,
                        "a": pygame.K_a, "d": pygame.K_d, "w": pygame.K_w,
                    }
                    ak = _TEXT_TO_KEY.get(event.unicode.lower())
                if ak is None:
                    continue

                actions_list = game.get_available_actions()
                action = _find_action_by_key(game, actions_list, ak)
                pi = _potion_index_for_action_key(ak)
                if action is None:
                    if pi == 1:
                        error_p1_until = now + ACTION_BTN_ERROR_S
                    elif pi == 2:
                        error_p2_until = now + ACTION_BTN_ERROR_S
                    elif pi == 3:
                        error_p3_until = now + ACTION_BTN_ERROR_S
                    continue

                prev = game.current_state_id
                ok = game.execute_action(action)
                if ok:
                    if pi == 1:
                        highlight_p1_until = now + ACTION_BTN_HIGHLIGHT_S
                    elif pi == 2:
                        highlight_p2_until = now + ACTION_BTN_HIGHLIGHT_S
                    elif pi == 3:
                        highlight_p3_until = now + ACTION_BTN_HIGHLIGHT_S
                    nxt = game.current_state_id
                    if nxt in visit_counts:
                        visit_counts[nxt] += 1
                    step_counter += 1
                    er, _, _ = craft_metrics()
                    cur_el = max(0.0, time.time() - round_started_at)
                    if er >= 1.0 or cur_el >= float(CRAFT_MIN_TRIAL_SECONDS):
                        finish_round()
                        break

            # 被动检查
            if phase == "running":
                er, _, _ = craft_metrics()
                cur_el = max(0.0, time.time() - round_started_at)
                if er >= 1.0 or cur_el >= float(CRAFT_MIN_TRIAL_SECONDS):
                    finish_round()

        # ── 重新计算高亮/报错标志，让事件处理结果即时可见 ──
        now2 = time.monotonic()
        lit_p1 = now2 < highlight_p1_until
        lit_p2 = now2 < highlight_p2_until
        lit_p3 = now2 < highlight_p3_until
        err_p1 = now2 < error_p1_until
        err_p2 = now2 < error_p2_until
        err_p3 = now2 < error_p3_until

        explored_rate, mastery_rate, mastered_count = craft_metrics()
        elapsed = max(0.0, time.time() - round_started_at)
        time_ok = elapsed >= float(CRAFT_MIN_TRIAL_SECONDS)

        trial_id = game.current_trial.trial_id if game.current_trial else "-"
        meta1 = (
            f"练习 · 第 {round_index}/{CRAFT_PRACTICE_ROUNDS} 轮 · "
            f"探索 {explored_rate:.0%} · 覆盖达标 {mastery_rate:.0%} ({mastered_count}/9)"
        )
        em = int(elapsed) // 60
        es = int(elapsed) % 60
        tm = CRAFT_MIN_TRIAL_SECONDS // 60
        ts_s = CRAFT_MIN_TRIAL_SECONDS % 60
        meta2 = (
            f"本轮 {em:02d}:{es:02d} / {tm:02d}:{ts_s:02d} · "
            f"探索 {'✓' if explored_rate >= 1.0 else '✗'} · "
            f"时间 {'✓' if time_ok else '✗'} · "
            f"任一✓即达标"
        )

        _co = (max(0, (W - CRAFT_WINDOW_W) // 2), max(0, (H - CRAFT_WINDOW_H) // 2)) if (W != CRAFT_WINDOW_W or H != CRAFT_WINDOW_H) else None
        op_slot_rect, action_btn_row, target_rect = craft_layout_rects(W, H)
        craft_draw_ui(
            screen=screen,
            game=game,
            img_cache=img_cache,
            bottle_cache=bottle_cache,
            op_slot_rect=op_slot_rect,
            action_btn_row=action_btn_row,
            target_rect=target_rect,
            lit_p1=lit_p1,
            lit_p2=lit_p2,
            lit_p3=lit_p3,
            err_p1=err_p1,
            err_p2=err_p2,
            err_p3=err_p3,
            header_title="合成练习",
            meta_line=meta1,
            meta_line2=meta2,
            target_area_mode="practice",
            content_origin=_co,
        )

        if phase == "round_transition":
            banner = font_md.render(
                f"第 {round_index - 1} 轮完成  ·  Enter / 空格 开始第 {round_index} 轮",
                True, (140, 220, 140),
            )
            screen.blit(banner, banner.get_rect(center=(W // 2, H - 48)))
            for e in events:
                if e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_SPACE):
                    phase = "running"
        elif phase == "finished":
            b1 = font_md.render(
                f"合成练习完成：共 {CRAFT_PRACTICE_ROUNDS} 轮均达标",
                True, (140, 220, 140),
            )
            screen.blit(b1, b1.get_rect(center=(W // 2, H - 62)))
            b2 = font_sm.render("按 Enter / 空格 继续", True, (170, 170, 190))
            screen.blit(b2, b2.get_rect(center=(W // 2, H - 32)))
            for e in events:
                if e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return True

        pygame.display.flip()
        clock.tick(60)

    return True


# ─────────────────────────────────────────────────────────
# 4) 正式测试（复用 run_mix_experiment 的核心逻辑）
# ─────────────────────────────────────────────────────────

def _consolidate_all_sessions_to_xlsx(data_root: Path, pid: str, order: str) -> Optional[Path]:
    """把 5 个 session 的全部步骤级数据汇总到一个 xlsx（每个 session 一个 sheet）。"""
    if not _HAS_PANDAS:
        print("[WARN] pandas 不可用，跳过汇总 xlsx 生成。")
        return None

    nav_root = data_root / "navigation"
    craft_root = data_root / "crafting"
    order_tag = order.replace("-", "_")  # e.g. navigation_first
    out_path = data_root / f"{pid}_{order_tag}_all_sessions.xlsx"

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        for sn in range(1, 6):
            frames: list[pd.DataFrame] = []

            # ── 导航数据 ──
            nav_session_dir = nav_root / f"session_{sn:02d}"
            if nav_session_dir.is_dir():
                # 可能有单个 xlsx（纯导航 session）或 trial_XX 子目录（混合 session）
                for xlsx in sorted(nav_session_dir.rglob("*.xlsx")):
                    try:
                        df = pd.read_excel(xlsx, sheet_name="Sheet1")
                        df.insert(0, "Domain", "navigation")
                        frames.append(df)
                    except Exception:
                        pass

            # ── 合成数据 ──
            craft_session_dir = craft_root / f"session_{sn:02d}"
            if craft_session_dir.is_dir():
                for xlsx in sorted(craft_session_dir.rglob("*.xlsx")):
                    try:
                        df = pd.read_excel(xlsx)
                        df.insert(0, "Domain", "crafting")
                        frames.append(df)
                    except Exception:
                        pass

            if frames:
                combined = pd.concat(frames, ignore_index=True)
            else:
                combined = pd.DataFrame({"Domain": [], "Note": []})

            sheet_name = f"Session_{sn}"
            combined.to_excel(writer, sheet_name=sheet_name, index=False)

    print(f"[INFO] 汇总数据已保存: {out_path}")
    return out_path


def _collect_trials(session: Dict[str, Any], trial_type: str) -> List[Dict[str, Any]]:
    combined = session.get("combined_order") or []
    if combined:
        return [item["trial"] for item in combined if item["type"] == trial_type]
    key = "navigation_trials" if trial_type == "navigation" else "crafting_trials"
    return list(session.get(key, []))


def _run_test_sessions(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    pid: str,
    order: str,
    nav_map: Path,
    rules,
    stone_cache: StoneImageCache,
    bottle_cache: BottleImageCache,
) -> int:
    """运行全部 5 个正式测试 session，数据存储逻辑与 run_mix_experiment 一致。"""
    schedule = build_session_schedule(order)
    data_root = _ROOT / "data"
    nav_data_root = data_root / "navigation"
    craft_data_root = data_root / "crafting"
    mix_data_root = data_root / "mix"
    for p in (data_root, nav_data_root, craft_data_root, mix_data_root):
        p.mkdir(parents=True, exist_ok=True)
    save_schedule(schedule, data_root / "full_schedule.json")

    for session in schedule["sessions"]:
        sn = int(session["session"])
        domain = str(session["domain"])
        session_seed = int(session["seed"])
        combined = list(session.get("combined_order") or [])
        nav_trials = _collect_trials(session, "navigation")
        craft_trials = _collect_trials(session, "crafting")

        if domain == "navigation":
            guidance_kind = "navigation"
            trial_count_hint = len(nav_trials)
        elif domain == "crafting":
            guidance_kind = "crafting"
            trial_count_hint = len(craft_trials)
        else:
            guidance_kind = "mixed"
            trial_count_hint = len(combined)

        if not run_mix_session_guidance_screen(
            screen, clock,
            session_num=sn, domain=guidance_kind,
            total_trials_in_session=trial_count_hint or None,
        ):
            return 1

        mix_session_dir = mix_data_root / f"session_{sn:02d}"
        mix_session_dir.mkdir(parents=True, exist_ok=True)
        outputs: List[Dict[str, Any]] = []
        session_interrupted = False

        if domain == "navigation":
            out = run_navigation_session(
                screen=screen, clock=clock, participant_id=pid,
                map_path=str(nav_map), nav_trials=nav_trials,
                session_num=sn, session_seed=session_seed,
                order=order, domain=domain,
                output_dir=nav_data_root / f"session_{sn:02d}",
                crafting_trials=craft_trials, combined_order=combined,
            )
            outputs.append({"type": "navigation", "output": out})
            session_interrupted = bool(out.get("interrupted", False))

        elif domain == "crafting":
            out = run_crafting_session(
                screen=screen, clock=clock, pid=pid,
                rules=rules, image_cache=stone_cache, bottle_cache=bottle_cache,
                craft_trials=craft_trials, session_num=sn, session_seed=session_seed,
                output_dir=craft_data_root / f"session_{sn:02d}",
                order=order, domain=domain,
                navigation_trials=nav_trials, combined_order=combined,
            )
            outputs.append({"type": "crafting", "output": out})
            session_interrupted = bool(out.get("interrupted", False))

        else:
            total = len(combined)
            nav_idx = 0
            craft_idx = 0
            for idx, item in enumerate(combined, start=1):
                phase = item["type"]
                trial = item["trial"]
                if phase == "navigation":
                    nav_idx += 1
                    out = run_navigation_session(
                        screen=screen, clock=clock, participant_id=pid,
                        map_path=str(nav_map), nav_trials=[trial],
                        session_num=sn, session_seed=session_seed,
                        order=order, domain=domain,
                        output_dir=nav_data_root / f"session_{sn:02d}" / f"trial_{nav_idx:02d}",
                        crafting_trials=craft_trials, combined_order=combined,
                        display_trial_progress=(idx, total),
                    )
                    outputs.append({"type": "navigation", "index": nav_idx, "progress": [idx, total], "output": out})
                    if bool(out.get("interrupted", False)):
                        session_interrupted = True
                        break
                else:
                    craft_idx += 1
                    out = run_crafting_session(
                        screen=screen, clock=clock, pid=pid,
                        rules=rules, image_cache=stone_cache, bottle_cache=bottle_cache,
                        craft_trials=[trial], session_num=sn, session_seed=session_seed,
                        output_dir=craft_data_root / f"session_{sn:02d}" / f"trial_{craft_idx:02d}",
                        order=order, domain=domain,
                        navigation_trials=nav_trials, combined_order=combined,
                        display_trial_progress=(idx, total),
                    )
                    outputs.append({"type": "crafting", "index": craft_idx, "progress": [idx, total], "output": out})
                    if bool(out.get("interrupted", False)):
                        session_interrupted = True
                        break

        with (mix_session_dir / "session_metadata.json").open("w", encoding="utf-8") as fh:
            json.dump(
                {
                    "order": order,
                    "session": sn,
                    "seed": session_seed,
                    "domain": domain,
                    "navigation_trials": nav_trials,
                    "crafting_trials": craft_trials,
                    "combined_order": combined,
                    "outputs": outputs,
                    "session_interrupted": session_interrupted,
                },
                fh, ensure_ascii=False, indent=2,
            )
        if session_interrupted:
            print(f"[INFO] Session {sn} 被用户中断，自动进入下一 session。")

    # ── 汇总所有 session 数据到一个 xlsx ──
    _consolidate_all_sessions_to_xlsx(data_root, pid, order)
    return 0


# ─────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────
def main() -> int:
    pygame.init()
    pygame.key.stop_text_input()

    # 全屏
    info = pygame.display.Info()
    screen = pygame.display.set_mode((info.current_w, info.current_h), pygame.FULLSCREEN)
    pygame.display.set_caption("NC Mix — 完整实验")
    clock = pygame.time.Clock()

    # 1. 被试编号 + 顺序选择
    result = _run_participant_and_order_screen(screen, clock)
    if result is None:
        pygame.quit()
        return 1
    pid, order = result

    # 解析资源路径
    nav_map = _resolve_nav_map(DEFAULT_NAV_MAP)
    transition_map = resolve_transition_map_cli_path(_ROOT / "crafting", DEFAULT_TRANSITION_MAP)
    run_equivalence_preflight(
        navigation_map_path=str(nav_map),
        transition_map_path=str(transition_map),
        report_path=str(_ROOT / "data" / "mix" / "preflight_report.json"),
    )

    craft_root = _ROOT / "crafting"
    rules_path = str(craft_root / "data" / "rules" / "crafting_rules_v1.json")
    rules = load_rule_data_with_transition_map(rules_path, transition_map)
    stone_cache = StoneImageCache(collect_stone_asset_dirs(craft_root))
    bottle_cache = BottleImageCache(collect_bottle_asset_dirs(craft_root))

    # 2. 导航练习指导语 → 导航练习
    if not _nav_practice_guidance(screen, clock):
        pygame.quit()
        return 1
    if not _run_nav_practice(screen, clock, str(nav_map)):
        pygame.quit()
        return 1

    # 3. 合成练习指导语 → 合成练习
    if not _craft_practice_guidance(screen, clock):
        pygame.quit()
        return 1
    if not _run_craft_practice(screen, clock, rules, stone_cache, bottle_cache):
        pygame.quit()
        return 1

    # 4. 正式测试（5 session）
    rc = _run_test_sessions(screen, clock, pid, order, nav_map, rules, stone_cache, bottle_cache)

    pygame.quit()
    print(f"实验完成。数据目录：{_ROOT / 'data'}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
