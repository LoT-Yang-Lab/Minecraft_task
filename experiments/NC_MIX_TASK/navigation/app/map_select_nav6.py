"""
从 maps 目录选择 Navigation6 地图 JSON（与 Crafting 选图交互一致）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional, Tuple

import pygame

from .paths import maps_dir, resolve_map_path


def _font(size: int) -> pygame.font.Font:
    try:
        return pygame.font.SysFont("SimHei", size)
    except Exception:
        return pygame.font.SysFont("arial", size)


def list_navigation6_map_files() -> List[Tuple[str, str]]:
    """
    返回 [(列表显示名, 绝对路径), ...]，仅包含 schema 为 navigation6 的 JSON。
    """
    root = Path(maps_dir())
    if not root.is_dir():
        return []
    out: List[Tuple[str, str]] = []
    for p in sorted(root.glob("*.json")):
        try:
            with p.open(encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        if data.get("schema") != "navigation6":
            continue
        meta = data.get("metadata") or {}
        name = (meta.get("name") or p.stem).strip() or p.stem
        label = f"{name}  ({p.name})"
        out.append((label, str(p.resolve())))
    return out


def run_map_selection(screen: pygame.Surface, clock: pygame.time.Clock) -> Optional[str]:
    """
    返回选中的地图绝对路径；Esc / 关闭窗口返回 None。
    """
    items = list_navigation6_map_files()
    w, h = screen.get_size()
    bg = (28, 31, 38)
    fg = (230, 234, 245)
    muted = (130, 142, 168)
    hi = (96, 165, 250)
    title_f = _font(28)
    row_f = _font(22)
    hint_f = _font(18)

    pygame.display.set_caption("Navigation6 - 选择地图")

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
            t = title_f.render("未找到可用地图", True, fg)
            screen.blit(t, t.get_rect(center=(w // 2, h // 2 - 40)))
            t2 = hint_f.render(
                f"请在 {maps_dir()} 下放置 schema 为 navigation6 的 JSON",
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
    margin_x = min(80, max(24, w // 14))
    list_top = min(160, h // 5)

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
            title_f.render("选择地图", True, fg),
            (margin_x, min(48, h // 14)),
        )
        screen.blit(
            hint_f.render(
                "↑↓ 或 W/S 切换 · Enter 确认 · 鼠标点击确认 · Esc 退出",
                True,
                muted,
            ),
            (margin_x, min(92, h // 14 + 44)),
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


def resolve_map_cli_path(arg: str) -> str:
    """命令行 --map：支持绝对路径、相对 maps 目录、或 resolve_map_path 可解析的路径。"""
    if os.path.isabs(arg) and os.path.isfile(arg):
        return os.path.abspath(arg)
    cand = Path(maps_dir()) / arg
    if cand.is_file():
        return str(cand.resolve())
    p = resolve_map_path(arg)
    if os.path.isfile(p):
        return p
    raise FileNotFoundError(f"找不到地图文件: {arg}")
