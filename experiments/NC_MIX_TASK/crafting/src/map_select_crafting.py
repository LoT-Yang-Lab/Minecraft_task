"""
进入正式实验前：从 data/maps 中选择转化地图（Pygame 列表 + 键盘/鼠标）。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, Tuple

import pygame

from .transition_map_io_crafting import list_available_transition_maps


def _font(size: int) -> pygame.font.Font:
    try:
        return pygame.font.SysFont("SimHei", size)
    except Exception:
        return pygame.font.SysFont("arial", size)


def run_transition_map_selection(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    crafting_root: Path,
) -> Optional[str]:
    """
    返回选中的转化地图绝对路径；Esc / 关闭窗口 返回 None。
    """
    items: List[Tuple[str, str]] = list_available_transition_maps(str(crafting_root))
    w, h = screen.get_size()
    bg = (28, 31, 38)
    fg = (230, 234, 245)
    muted = (130, 142, 168)
    hi = (96, 165, 250)
    title_f = _font(28)
    row_f = _font(22)
    hint_f = _font(18)

    if not items:
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                if event.type == pygame.KEYDOWN and event.key in (
                    pygame.K_ESCAPE,
                    pygame.K_RETURN,
                ):
                    return None
            screen.fill(bg)
            t = title_f.render("未找到可用转化地图", True, fg)
            screen.blit(t, t.get_rect(center=(w // 2, h // 2 - 40)))
            t2 = hint_f.render(
                "请在 crafting/data/maps 下放置 schema 为 crafting_transition_map 的 JSON",
                True,
                muted,
            )
            screen.blit(t2, t2.get_rect(center=(w // 2, h // 2 + 10)))
            t3 = hint_f.render("按 Enter 或 Esc 退出", True, muted)
            screen.blit(t3, t3.get_rect(center=(w // 2, h // 2 + 48)))
            pygame.display.flip()
            clock.tick(30)

    selected = 0
    row_h = 44
    margin_x = 80
    list_top = 160

    row_rects: List[pygame.Rect] = []
    for i in range(len(items)):
        row_rects.append(
            pygame.Rect(margin_x, list_top + i * row_h, w - margin_x * 2, row_h - 6)
        )

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return None
                if event.key in (pygame.K_UP, pygame.K_w):
                    selected = (selected - 1) % len(items)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    selected = (selected + 1) % len(items)
                elif event.key in (
                    pygame.K_RETURN,
                    pygame.K_SPACE,
                    pygame.K_KP_ENTER,
                ):
                    return items[selected][1]
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                for i, rect in enumerate(row_rects):
                    if rect.collidepoint(mx, my):
                        selected = i
                        return items[i][1]

        screen.fill(bg)
        screen.blit(
            title_f.render("选择转化地图", True, fg),
            (margin_x, 48),
        )
        screen.blit(
            hint_f.render(
                "↑↓ 或 W/S 切换 · Enter 确认 · 鼠标点击条目确认 · Esc 退出",
                True,
                muted,
            ),
            (margin_x, 92),
        )

        for i, (label, _) in enumerate(items):
            rect = row_rects[i]
            if i == selected:
                pygame.draw.rect(screen, (50, 58, 78), rect, border_radius=8)
                pygame.draw.rect(screen, hi, rect, 2, border_radius=8)
            else:
                pygame.draw.rect(screen, (40, 44, 54), rect, border_radius=8)
                pygame.draw.rect(screen, (70, 76, 92), rect, 1, border_radius=8)
            surf = row_f.render(label, True, fg if i == selected else muted)
            screen.blit(surf, (rect.x + 16, rect.y + (rect.h - surf.get_height()) // 2))

        pygame.display.flip()
        clock.tick(30)


def resolve_transition_map_cli_path(crafting_root: Path, arg: str) -> str:
    """--transition_map 参数：支持绝对路径、相对 crafting 根、或相对当前工作目录。"""
    if os.path.isabs(arg) and os.path.isfile(arg):
        return os.path.abspath(arg)
    cand = crafting_root / arg
    if cand.is_file():
        return str(cand.resolve())
    if os.path.isfile(arg):
        return os.path.abspath(arg)
    raise FileNotFoundError(f"找不到转化地图文件: {arg}")


def resolve_trial_list_cli_path(crafting_root: Path, arg: str) -> str:
    """--trials 参数：支持绝对路径、相对 crafting 根、或相对当前工作目录。"""
    if os.path.isabs(arg) and os.path.isfile(arg):
        return os.path.abspath(arg)
    cand = crafting_root / arg
    if cand.is_file():
        return str(cand.resolve())
    if os.path.isfile(arg):
        return os.path.abspath(arg)
    raise FileNotFoundError(f"找不到 trial 列表文件: {arg}")
