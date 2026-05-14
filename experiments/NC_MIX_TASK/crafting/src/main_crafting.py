"""
Crafting 正式实验 UI：
- 无石块池：每 trial 仅一个当前石块，显示在操作区
- 下方三枚魔法药水键 + 目标区
- Q/E：药水1 回路一正/逆向 · A/D：药水2 回路二正/逆向 · W：药水3 九石间状态变换

Proposal-5（与 Navigation6 试次设计对齐）：
- 在仓库根目录运行 ``python run_proposal5_experiment.py``（参见该脚本 ``--help``）。
- 使用与实验设计一致的转化地图，推荐 ``--transition_map data/maps/builtin_map_a.json``。
- 导航整数站点 1–9 对应 ``stone_01``…``stone_09``；试次调度逻辑见 ``src/proposal5_trial_schedule.py``（与 navigation6/tests/trial_schedule.py 同步维护）。
- 正式单机 ``python main.py``：优先通过转化地图 ``linked_navigation_map_id`` 或 ``--trials`` / ``--nav-map-id`` 加载与 Navigation6 相同的 trial_sequences JSON；否则使用 ``data/trials/trial_list_v1.json``。Proposal-5 使用有限试次并在每 session 结束自动退出游戏循环。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import List, Literal, Optional, Tuple

import pygame

_NC_ROOT = Path(__file__).resolve().parents[2]
if str(_NC_ROOT) not in sys.path:
    sys.path.insert(0, str(_NC_ROOT))

from mix.trial_display import format_session_trial_line

from .config_io_crafting import load_trial_list_auto
from .draw_stone import draw_stone
from .game_crafting import Action, GameCrafting
from .recorder import RLDataRecorder
from .map_select_crafting import (
    resolve_transition_map_cli_path,
    resolve_trial_list_cli_path,
    run_transition_map_selection,
)
from .transition_map_io_crafting import load_transition_map
from .participant_id_crafting import run_participant_id_screen
from .rules_io_crafting import load_rule_data_with_transition_map
from .bottle_images import (
    BottleImageCache,
    collect_bottle_asset_dirs,
    count_loaded_bottles,
)
from .stone_images import (
    StoneImageCache,
    blit_image_fit,
    collect_stone_asset_dirs,
    count_loaded_gems,
)
WINDOW_W = 1000
WINDOW_H = 820

ACTION_KEYS = [pygame.K_q, pygame.K_e, pygame.K_a, pygame.K_d, pygame.K_w]

# IME 兼容：TEXTINPUT → 虚拟 KEYDOWN 映射
_CRAFT_TEXT_TO_KEY: dict[str, int] = {
    "q": pygame.K_q, "e": pygame.K_e, "a": pygame.K_a,
    "d": pygame.K_d, "w": pygame.K_w, "r": pygame.K_r,
}


class _FakeKeyEvent:
    """IME 兼容用伪按键事件。"""
    def __init__(self, key_code: int):
        self.type = pygame.KEYDOWN
        self.key = key_code


MARGIN = 22
# 预留第二行 meta（练习模式时长等），正式实验略增顶部留白
HEADER_BOTTOM = 98
FOOTER_H = 22
PANEL_RADIUS = 12
INNER_PAD = 16
# 药水按钮行加高，瓶图区域更大
ACTION_BTN_ROW_H = 100
ACTION_BTN_INNER_GAP = 8
ACTION_BTN_HIGHLIGHT_S = 0.22
ACTION_BTN_ERROR_S = 0.28
COLOR_BG = (28, 31, 38)
COLOR_PANEL = (40, 44, 54)
COLOR_PANEL_EDGE = (72, 78, 94)
COLOR_TITLE = (188, 198, 225)
COLOR_BODY = (232, 236, 246)
COLOR_MUTED = (130, 142, 168)
COLOR_ACCENT = (96, 165, 250)
COLOR_BTN_ACTIVE = (72, 168, 96)
COLOR_BTN_ACTIVE_EDGE = (130, 220, 150)
COLOR_BTN_ERROR_EDGE = (230, 82, 82)
COLOR_BTN_ERROR_EDGE_SOFT = (180, 64, 64)


def _crafting_root() -> Path:
    return Path(__file__).resolve().parent.parent


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


def run_experiment_guidance_screen(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    *,
    map_label: str,
) -> bool:
    """
    被试编号与地图选择之后呈现的正式实验指导语。
    Enter/空格进入实验，Esc/关闭窗口退出。
    """
    font_title = _font(26)
    font_body = _font(16)
    font_hint = _font(15)
    margin_x = 28
    text_w = WINDOW_W - margin_x * 2

    while True:
        screen.fill(COLOR_BG)
        y = 32
        y = _draw_wrapped(
            screen, font_title, "正式实验 · 任务说明", margin_x, y, text_w, (230, 235, 255)
        )
        y += 10
        y = _draw_wrapped(
            screen,
            font_body,
            "感谢您参与本研究。您的任务是在每个试次中，通过键盘操作使「操作区」石块状态变化，"
            "直至与「目标区」所示目标一致。"
            "请在安静环境中保持专注，尽量依据直觉作答。",
            margin_x,
            y,
            text_w,
            (205, 210, 225),
        )

        _draw_wrapped(
            screen,
            font_hint,
            "Enter / 空格 开始正式实验  ·  Esc 退出",
            margin_x,
            WINDOW_H - 44,
            text_w,
            (150, 185, 220),
        )
        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type != pygame.KEYDOWN:
                continue
            if event.key == pygame.K_ESCAPE:
                return False
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                return True
        clock.tick(60)


def layout_rects(
    screen_w: Optional[int] = None,
    screen_h: Optional[int] = None,
) -> Tuple[pygame.Rect, pygame.Rect, pygame.Rect]:
    """操作区、药水键条、目标区（全宽，无左侧池）。

    当传入 screen_w / screen_h 时，将 WINDOW_W×WINDOW_H 布局居中。
    """
    sw = screen_w or WINDOW_W
    sh = screen_h or WINDOW_H
    x_off = max(0, (sw - WINDOW_W) // 2)
    y_off = max(0, (sh - WINDOW_H) // 2)

    content_top = HEADER_BOTTOM + y_off
    content_bottom = WINDOW_H + y_off - FOOTER_H
    content_h = content_bottom - content_top
    full_w = WINDOW_W - MARGIN * 2
    x = MARGIN + x_off

    # 药水行与上下间隙；剩余高度在操作区 / 目标区之间略偏上，使两侧宝石可用高度接近
    gap_mid = 8
    gap_below_btn = 10
    avail = content_h - ACTION_BTN_ROW_H - gap_mid - gap_below_btn
    op_h = max(178, min(275, int(avail * 0.508)))
    op_rect = pygame.Rect(x, content_top, full_w, op_h)

    btn_y = op_rect.bottom + gap_mid
    action_btn_row = pygame.Rect(x, btn_y, full_w, ACTION_BTN_ROW_H)

    target_y = action_btn_row.bottom + gap_below_btn
    target_h = max(140, content_bottom - target_y)
    target_rect = pygame.Rect(x, target_y, full_w, target_h)

    return op_rect, action_btn_row, target_rect


def _action_button_rects(row: pygame.Rect) -> Tuple[pygame.Rect, pygame.Rect, pygame.Rect]:
    gap = ACTION_BTN_INNER_GAP
    inner_w = max(3, row.w - gap * 2)
    w = inner_w // 3
    x0 = row.x
    y0 = row.y
    h = row.h
    r0 = pygame.Rect(x0, y0, w, h)
    r1 = pygame.Rect(x0 + w + gap, y0, w, h)
    r2_x = x0 + (w + gap) * 2
    r2_w = max(1, row.right - r2_x)
    r2 = pygame.Rect(r2_x, y0, r2_w, h)
    return r0, r1, r2


def _potion_index_for_action_key(key: int) -> Optional[int]:
    """Q/E→1，A/D→2，W→3。"""
    if key in (pygame.K_q, pygame.K_e):
        return 1
    if key in (pygame.K_a, pygame.K_d):
        return 2
    if key == pygame.K_w:
        return 3
    return None


def _draw_action_buttons(
    screen: pygame.Surface,
    row: pygame.Rect,
    lit1: bool,
    lit2: bool,
    lit3: bool,
    err1: bool,
    err2: bool,
    err3: bool,
    bottle_cache: Optional[BottleImageCache],
) -> None:
    labels = ("魔法药水1", "魔法药水2", "魔法药水3")
    highlights = (lit1, lit2, lit3)
    errors = (err1, err2, err3)
    btn_label_f = _font(12)
    for i, (rect, label, ok, bad) in enumerate(
        zip(_action_button_rects(row), labels, highlights, errors), start=1
    ):
        if ok:
            pygame.draw.rect(screen, COLOR_BTN_ACTIVE, rect, border_radius=10)
            pygame.draw.rect(screen, COLOR_BTN_ACTIVE_EDGE, rect, 2, border_radius=10)
        else:
            pygame.draw.rect(screen, (48, 52, 62), rect, border_radius=10)
            if bad:
                pygame.draw.rect(screen, COLOR_BTN_ERROR_EDGE_SOFT, rect, 3, border_radius=10)
                pygame.draw.rect(screen, COLOR_BTN_ERROR_EDGE, rect, 2, border_radius=10)
            else:
                pygame.draw.rect(screen, (70, 76, 92), rect, 1, border_radius=10)

        txt_color = (236, 255, 242) if ok else COLOR_BODY
        img = bottle_cache.get(i) if bottle_cache else None
        if img is not None:
            label_h = 14
            edge = 3
            img_r = pygame.Rect(
                rect.x + edge,
                rect.y + edge,
                rect.w - edge * 2,
                max(24, rect.h - label_h - edge * 2),
            )
            blit_image_fit(screen, img, img_r, padding=0)
            surf = btn_label_f.render(label, True, txt_color)
            screen.blit(surf, surf.get_rect(midbottom=(rect.centerx, rect.bottom - 4)))
        else:
            surf = _font(14).render(label, True, txt_color)
            screen.blit(surf, surf.get_rect(center=rect.center))


def _action_key_symbol(key: int) -> str:
    return {
        pygame.K_q: "Q",
        pygame.K_e: "E",
        pygame.K_a: "A",
        pygame.K_d: "D",
        pygame.K_w: "W",
    }.get(key, "?")


def _find_action_by_key(game: GameCrafting, actions: List[Action], key: int) -> Optional[Action]:
    if key == pygame.K_q:
        for a in actions:
            if a.kind == "ring1_step" and a.param == "+1":
                return a
        return None
    if key == pygame.K_e:
        for a in actions:
            if a.kind == "ring1_step" and a.param == "-1":
                return a
        return None
    if key == pygame.K_a:
        for a in actions:
            if a.kind == "ring2_step" and a.param == "+1":
                return a
        return None
    if key == pygame.K_d:
        for a in actions:
            if a.kind == "ring2_step" and a.param == "-1":
                return a
        return None
    if key == pygame.K_w:
        for a in actions:
            if a.kind == "w_cycle":
                return a
        return None
    return None


def _draw_current_stone(
    screen: pygame.Surface,
    gem_rect: pygame.Rect,
    state_id: str,
    img_cache: StoneImageCache,
) -> None:
    border = COLOR_ACCENT
    draw_stone(screen, state_id, gem_rect, border, img_cache=img_cache)
    pygame.draw.rect(screen, border, gem_rect, 2, border_radius=8)


def _shared_gem_size(inner: pygame.Rect, tgt_inner: pygame.Rect) -> Tuple[int, int]:
    """操作区与目标区宝石位图使用相同像素宽高。"""
    w = min(inner.w, tgt_inner.w)
    h = min(inner.h, tgt_inner.h)
    return max(40, w), max(40, h)


def _gem_rect_centered(container: pygame.Rect, gem_w: int, gem_h: int) -> pygame.Rect:
    r = pygame.Rect(0, 0, gem_w, gem_h)
    r.center = container.center
    return r


def _draw_order_complete_overlay(screen: pygame.Surface, game: GameCrafting) -> None:
    sw, sh = screen.get_size()
    veil = pygame.Surface((sw, sh), pygame.SRCALPHA)
    veil.fill((18, 20, 26, 238))
    screen.blit(veil, (0, 0))

    big = _font(44)
    sub = _font(20)
    hint = _font(18)
    cx = sw // 2

    t1 = big.render("订单完成", True, (245, 248, 255))
    r1 = t1.get_rect(center=(cx, sh // 2 - 36))
    screen.blit(t1, r1)

    y = sh // 2 + 8
    if game.completes_trial_after_order_overlay:
        s0 = hint.render("本局试次已完成", True, (190, 198, 215))
        screen.blit(s0, s0.get_rect(center=(cx, y)))
        y += 30
    s1 = hint.render("按 空格 或 Enter 继续", True, (180, 188, 205))
    screen.blit(s1, s1.get_rect(center=(cx, y)))

    t2 = sub.render("（也可随时按 Esc 退出程序）", True, (120, 128, 148))
    screen.blit(t2, t2.get_rect(center=(cx, y + 52)))


def draw_ui(
    screen: pygame.Surface,
    game: GameCrafting,
    img_cache: StoneImageCache,
    bottle_cache: Optional[BottleImageCache],
    op_slot_rect: pygame.Rect,
    action_btn_row: pygame.Rect,
    target_rect: pygame.Rect,
    lit_p1: bool,
    lit_p2: bool,
    lit_p3: bool,
    err_p1: bool,
    err_p2: bool,
    err_p3: bool,
    *,
    header_title: Optional[str] = None,
    meta_line: Optional[str] = None,
    meta_line2: Optional[str] = None,
    session_meta_prefix: Optional[str] = None,
    target_area_mode: Literal["order", "practice"] = "order",
    content_origin: Optional[Tuple[int, int]] = None,
) -> None:
    screen.fill(COLOR_BG)

    ox, oy = content_origin or (0, 0)
    title_f = _font(26)
    meta_f = _font(16)

    trial_id = game.current_trial.trial_id if game.current_trial else "-"
    trial_seq = (game.trial_index + 1) if game.current_trial else 0
    trial_total = max(1, len(getattr(game, "trials", [])))
    if meta_line is not None:
        meta = meta_line
    elif session_meta_prefix:
        meta = format_session_trial_line(
            session_label=session_meta_prefix,
            trial_n=trial_seq,
            trial_n_total=trial_total,
            domain_zh="合成",
        )
    else:
        meta = format_session_trial_line(
            session_label=None,
            trial_n=trial_seq,
            trial_n_total=trial_total,
            domain_zh="合成",
        )
    display_title = header_title or "Crafting 正式实验（九石阵）"
    screen.blit(title_f.render(display_title, True, (236, 242, 255)), (MARGIN + ox, 20 + oy))
    if meta:
        screen.blit(meta_f.render(meta, True, COLOR_MUTED), (MARGIN + ox, 52 + oy))
    if meta_line2:
        meta2_y = 74 + oy if meta else 52 + oy
        screen.blit(meta_f.render(meta_line2, True, COLOR_MUTED), (MARGIN + ox, meta2_y))

    pygame.draw.rect(screen, COLOR_PANEL, op_slot_rect, border_radius=PANEL_RADIUS)
    pygame.draw.rect(screen, COLOR_PANEL_EDGE, op_slot_rect, 1, border_radius=PANEL_RADIUS)
    screen.blit(_font(18).render("操作区", True, COLOR_TITLE), (op_slot_rect.x + INNER_PAD, op_slot_rect.y + 12))

    inner_top = op_slot_rect.y + 34
    inner_bottom = op_slot_rect.y + op_slot_rect.h - INNER_PAD
    inner_h = max(40, inner_bottom - inner_top)
    inner = pygame.Rect(op_slot_rect.x + INNER_PAD, inner_top, op_slot_rect.w - INNER_PAD * 2, inner_h)

    pygame.draw.rect(screen, COLOR_PANEL, target_rect, border_radius=PANEL_RADIUS)
    pygame.draw.rect(screen, COLOR_PANEL_EDGE, target_rect, 1, border_radius=PANEL_RADIUS)
    if target_area_mode == "practice":
        screen.blit(
            _font(18).render("本局起始石块（按 R 可重置回此）", True, COLOR_TITLE),
            (target_rect.x + INNER_PAD, target_rect.y + 12),
        )
    else:
        screen.blit(_font(18).render("目标区", True, COLOR_TITLE), (target_rect.x + INNER_PAD, target_rect.y + 12))
    tgt_inner_top = target_rect.y + 32
    tgt_inner = pygame.Rect(
        target_rect.x + INNER_PAD,
        tgt_inner_top,
        target_rect.w - INNER_PAD * 2,
        target_rect.bottom - INNER_PAD - tgt_inner_top,
    )

    gem_w, gem_h = _shared_gem_size(inner, tgt_inner)
    gem_op = _gem_rect_centered(inner, gem_w, gem_h)
    gem_tgt = _gem_rect_centered(tgt_inner, gem_w, gem_h)

    if game.current_state_id:
        _draw_current_stone(screen, gem_op, game.current_state_id, img_cache)
    else:
        pygame.draw.rect(screen, (44, 48, 58), gem_op, border_radius=8)
        pygame.draw.rect(screen, (68, 74, 88), gem_op, 2, border_radius=8)

    _draw_action_buttons(
        screen, action_btn_row, lit_p1, lit_p2, lit_p3, err_p1, err_p2, err_p3, bottle_cache
    )

    tgt_border = (120, 140, 180)
    if target_area_mode == "practice":
        start_id = game.active_raw_start_state_id or ""
        if start_id:
            draw_stone(screen, start_id, gem_tgt, tgt_border, img_cache=img_cache)
        else:
            pygame.draw.rect(screen, (44, 48, 58), gem_tgt, border_radius=8)
            pygame.draw.rect(screen, (68, 74, 88), gem_tgt, 2, border_radius=8)
        hint_f = _font(14)
        hx = target_rect.x + INNER_PAD
        hy = min(gem_tgt.bottom + 10, target_rect.bottom - 52)
        for i, line in enumerate(
            (
                "练习模式：无订单任务，请熟悉 Q/E/A/D/W",
                "与当前地图上的石块变化规律。",
            )
        ):
            screen.blit(hint_f.render(line, True, COLOR_MUTED), (hx, hy + i * (hint_f.get_linesize() + 2)))
    else:
        tgt_id = game.current_target()
        if tgt_id:
            draw_stone(screen, tgt_id, gem_tgt, tgt_border, img_cache=img_cache)
        else:
            pygame.draw.rect(screen, (44, 48, 58), gem_tgt, border_radius=8)


def run_crafting_game_loop(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    game: GameCrafting,
    img_cache: StoneImageCache,
    bottle_cache: Optional[BottleImageCache],
    *,
    header_title: Optional[str] = None,
    meta_line: Optional[str] = None,
    meta_line2: Optional[str] = None,
    session_meta_prefix: Optional[str] = None,
) -> bool:
    """
    单阶段主循环：直到 finite_trials 下 session_complete、用户 Esc/关窗、或 QUIT。
    调用方负责在循环前后管理 pygame 与 recorder.save_to_file()。
    返回值：True 表示正常跑完本 session（session_complete），False 表示被 Esc/关窗中断。
    """
    highlight_p1_until = 0.0
    highlight_p2_until = 0.0
    highlight_p3_until = 0.0
    error_p1_until = 0.0
    error_p2_until = 0.0
    error_p3_until = 0.0

    sw, sh = screen.get_size()
    _content_origin = (max(0, (sw - WINDOW_W) // 2), max(0, (sh - WINDOW_H) // 2)) if (sw != WINDOW_W or sh != WINDOW_H) else None

    running = True
    while running:
        if game.session_complete:
            running = False
            continue

        actions = game.get_available_actions()
        op_slot_rect, action_btn_row, target_rect = layout_rects(sw, sh)
        now = time.monotonic()
        lit_p1 = now < highlight_p1_until
        lit_p2 = now < highlight_p2_until
        lit_p3 = now < highlight_p3_until
        err_p1 = now < error_p1_until
        err_p2 = now < error_p2_until
        err_p3 = now < error_p3_until

        raw_events = pygame.event.get()
        # IME 兼容：将 TEXTINPUT 转换为虚拟 KEYDOWN
        mapped_keys = {ev.key for ev in raw_events if ev.type == pygame.KEYDOWN}
        for tev in raw_events:
            if tev.type == pygame.TEXTINPUT:
                ch = tev.text.lower()
                if ch in _CRAFT_TEXT_TO_KEY and _CRAFT_TEXT_TO_KEY[ch] not in mapped_keys:
                    raw_events.append(_FakeKeyEvent(_CRAFT_TEXT_TO_KEY[ch]))

        for event in raw_events:
            if event.type == pygame.QUIT:
                running = False
                continue

            if game.order_complete_overlay_pending:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key in (
                        pygame.K_SPACE,
                        pygame.K_RETURN,
                        pygame.K_KP_ENTER,
                    ):
                        game.dismiss_order_complete_overlay()
                continue

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                    continue
                if event.key == pygame.K_r:
                    game.clear_operation_slot()
                    continue

                if event.key in ACTION_KEYS:
                    pi = _potion_index_for_action_key(event.key)
                    sym = _action_key_symbol(event.key)
                    action = _find_action_by_key(game, actions, event.key)
                    if pi == 1:
                        if action is not None and game.execute_action(
                            action, source_key=sym
                        ):
                            highlight_p1_until = now + ACTION_BTN_HIGHLIGHT_S
                            error_p1_until = 0.0
                        else:
                            highlight_p1_until = 0.0
                            error_p1_until = now + ACTION_BTN_ERROR_S
                            game.log_invalid_keypress(
                                sym,
                                "invalid_no_action"
                                if action is None
                                else "invalid_execute_failed",
                            )
                    elif pi == 2:
                        if action is not None and game.execute_action(
                            action, source_key=sym
                        ):
                            highlight_p2_until = now + ACTION_BTN_HIGHLIGHT_S
                            error_p2_until = 0.0
                        else:
                            highlight_p2_until = 0.0
                            error_p2_until = now + ACTION_BTN_ERROR_S
                            game.log_invalid_keypress(
                                sym,
                                "invalid_no_action"
                                if action is None
                                else "invalid_execute_failed",
                            )
                    elif pi == 3:
                        if action is not None and game.execute_action(
                            action, source_key=sym
                        ):
                            highlight_p3_until = now + ACTION_BTN_HIGHLIGHT_S
                            error_p3_until = 0.0
                        else:
                            highlight_p3_until = 0.0
                            error_p3_until = now + ACTION_BTN_ERROR_S
                            game.log_invalid_keypress(
                                sym,
                                "invalid_no_action"
                                if action is None
                                else "invalid_execute_failed",
                            )

        if game.session_complete:
            running = False
            continue

        # 重新计算高亮/报错标志，让本帧事件处理的结果立即可见
        now2 = time.monotonic()
        lit_p1 = now2 < highlight_p1_until
        lit_p2 = now2 < highlight_p2_until
        lit_p3 = now2 < highlight_p3_until
        err_p1 = now2 < error_p1_until
        err_p2 = now2 < error_p2_until
        err_p3 = now2 < error_p3_until

        draw_ui(
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
            header_title=header_title,
            meta_line=meta_line,
            meta_line2=meta_line2,
            session_meta_prefix=session_meta_prefix,
            content_origin=_content_origin,
        )
        if game.order_complete_overlay_pending:
            _draw_order_complete_overlay(screen, game)

        pygame.display.flip()
        clock.tick(60)
    return bool(game.session_complete)


def main() -> None:
    parser = argparse.ArgumentParser(description="Crafting 正式实验")
    parser.add_argument(
        "--participant_id",
        "-p",
        type=str,
        default=None,
        help="被试编号；若指定则跳过选图前的编号输入页",
    )
    parser.add_argument("--rules", type=str, default=None, help="规则 JSON（默认 data/rules/crafting_rules_v1.json）")
    parser.add_argument(
        "--trials",
        type=str,
        default=None,
        help="试次 JSON：crafting_trial_list 或 Navigation6 trial_sequences（相对 crafting 根或绝对路径）",
    )
    parser.add_argument(
        "--nav-map-id",
        type=str,
        default=None,
        help="Navigation 地图 stem（不含 .json），从 sibling navigation/assets/trial_sequences/<id>.json 加载",
    )
    parser.add_argument(
        "--transition_map",
        type=str,
        default=None,
        help="跳过选图界面，直接指定转化地图 JSON（相对 crafting 根或绝对路径）",
    )
    args = parser.parse_args()

    root = _crafting_root()
    default_rules = str(root / "data" / "rules" / "crafting_rules_v1.json")
    default_trials = str((root / "data" / "trials" / "trial_list_v1.json").resolve())

    rules_path = args.rules or default_rules

    pygame.init()
    pygame.key.stop_text_input()  # 禁用 IME，确保字母键产生 KEYDOWN
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    clock = pygame.time.Clock()

    if args.participant_id and str(args.participant_id).strip():
        pid = str(args.participant_id).strip()
    else:
        pid = run_participant_id_screen(screen, clock)
        if pid is None:
            pygame.quit()
            sys.exit(0)

    if args.transition_map:
        try:
            transition_map_path = resolve_transition_map_cli_path(root, args.transition_map)
        except FileNotFoundError as e:
            print(e)
            pygame.quit()
            sys.exit(1)
    else:
        pygame.display.set_caption("Crafting - 选择地图")
        transition_map_path = run_transition_map_selection(screen, clock, root)
        if transition_map_path is None:
            pygame.quit()
            sys.exit(0)

    map_label = Path(transition_map_path).stem
    pygame.display.set_caption("Crafting - 实验说明")
    if not run_experiment_guidance_screen(screen, clock, map_label=map_label):
        pygame.quit()
        sys.exit(0)

    pygame.display.set_caption("Crafting - 正式实验")

    stone_dirs = collect_stone_asset_dirs(root)
    if not stone_dirs:
        print(
            "提示: 未找到宝石素材目录。请在项目目录下创建 assets/stone 放入图片，"
            "或在任意上级目录放置 shared/assets/stone（推荐 stone_01.png … stone_09.png）。"
        )
    else:
        print("宝石素材搜索路径: " + "  |  ".join(str(d) for d in stone_dirs))
    img_cache = StoneImageCache(stone_dirs)
    gem_ok = count_loaded_gems(img_cache)
    if stone_dirs and gem_ok < 9:
        print(
            f"提示: 仅匹配到 {gem_ok}/9 张宝石图，其余仍用程序绘制。"
            " 请将文件命名为 stone_01.png … stone_09.png（或与状态 ID 一致），放在上述目录之一。"
        )

    bottle_dirs = collect_bottle_asset_dirs(root)
    if not bottle_dirs:
        print(
            "提示: 未找到药水瓶素材目录。请将图片放在 assets/bottle 或上级目录的 "
            "shared/assets/bottle（推荐 bottle_01.png、bottle_02.png、bottle_03.png）。"
        )
    else:
        print("药水瓶素材搜索路径: " + "  |  ".join(str(d) for d in bottle_dirs))
    bottle_cache = BottleImageCache(bottle_dirs)
    bottle_ok = count_loaded_bottles(bottle_cache)
    if bottle_dirs and bottle_ok < 3:
        print(
            f"提示: 仅匹配到 {bottle_ok}/3 张药水瓶图，缺失的按钮仍显示文字。"
            " 推荐命名 bottle_01.png / bottle_02.png / bottle_03.png。"
        )

    rules = load_rule_data_with_transition_map(rules_path, transition_map_path)

    cli_trials = (args.trials or "").strip()
    cli_nav_id = (args.nav_map_id or "").strip()
    nav6_seq_dir = root.parent / "navigation" / "assets" / "trial_sequences"

    if cli_trials:
        try:
            trials_path_resolved = resolve_trial_list_cli_path(root, cli_trials)
        except FileNotFoundError as e:
            print(e)
            pygame.quit()
            sys.exit(1)
        trial_source_note = "CLI --trials"
    elif cli_nav_id:
        seq_path = nav6_seq_dir / f"{cli_nav_id}.json"
        if not seq_path.is_file():
            print(
                f"[FATAL] 找不到 Navigation 试次表（--nav-map-id）：{seq_path}\n"
                f"请确认 NC_MIX_TASK/navigation 与 crafting 并列，且存在对应 trial_sequences 文件。"
            )
            pygame.quit()
            sys.exit(1)
        trials_path_resolved = str(seq_path.resolve())
        trial_source_note = f"CLI --nav-map-id {cli_nav_id}"
    else:
        tm = load_transition_map(transition_map_path)
        link = (tm.linked_navigation_map_id or "").strip()
        if link:
            seq_path = nav6_seq_dir / f"{link}.json"
            if not seq_path.is_file():
                print(
                    f"[FATAL] 转化地图 linked_navigation_map_id={link!r}，但试次表不存在：{seq_path}\n"
                    "请改用 --trials 指定 JSON，或修正 navigation 下试次文件名。"
                )
                pygame.quit()
                sys.exit(1)
            trials_path_resolved = str(seq_path.resolve())
            trial_source_note = f"linked_navigation_map_id={link}"
        else:
            trials_path_resolved = default_trials
            trial_source_note = "default trial_list_v1.json"
            print(
                "[INFO] 转化地图未设置 linked_navigation_map_id；使用默认 crafting 试次表。\n"
                "     若要与 Navigation6 共用试次，请在转化地图 JSON 中设置 linked_navigation_map_id，"
                "或使用 --trials / --nav-map-id。"
            )

    try:
        trial_list = load_trial_list_auto(trials_path_resolved)
    except ValueError as e:
        print(f"[FATAL] 试次表解析失败: {e}")
        pygame.quit()
        sys.exit(1)

    print(
        f"[INFO] 已加载 trial 列表: {trial_list.source_path} "
        f"[{trial_list.format_label}] via {trial_source_note} — "
        f"{len(trial_list.trials)} 条 trial，轮换直至退出"
    )

    recorder = RLDataRecorder(participant_id=pid, task_type="Crafting")
    game = GameCrafting(recorder=recorder, rules=rules, trial_data=trial_list)

    run_crafting_game_loop(screen, clock, game, img_cache, bottle_cache)

    try:
        recorder.save_to_file()
    except Exception:
        pass
    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
