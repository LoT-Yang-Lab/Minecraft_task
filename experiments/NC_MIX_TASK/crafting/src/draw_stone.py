"""
绘制石块：若存在位图则缩放贴入 rect；否则使用程序生成的多边形石块。
"""

from __future__ import annotations

import math
import random
from typing import List, Optional, Tuple

import pygame

from .stone_images import StoneImageCache, blit_image_fit
from .stone_space import stone_index, is_valid_state_id


def _stone_palette(n: int) -> Tuple[int, int, int]:
    rng = random.Random(n * 11003)
    r = 58 + (n * 5 + rng.randint(0, 18)) % 36
    g = 52 + (n * 7 + rng.randint(0, 16)) % 32
    b = 44 + (n * 3 + rng.randint(0, 14)) % 28
    return r, g, b


def _polygon_for_stone(rect: pygame.Rect, n: int) -> List[Tuple[int, int]]:
    rng = random.Random(n * 4243)
    cx, cy = rect.centerx, rect.centery
    rw = max(6, rect.w // 2 - 4)
    rh = max(6, rect.h // 2 - 4)
    k = 6 + rng.randint(0, 3)
    pts: List[Tuple[int, int]] = []
    for i in range(k):
        ang = (i / k) * math.tau + rng.uniform(-0.12, 0.12)
        rr = rw * rng.uniform(0.72, 1.08)
        ss = rh * rng.uniform(0.72, 1.08)
        x = int(cx + math.cos(ang) * rr)
        y = int(cy + math.sin(ang) * ss)
        pts.append((x, y))
    return pts


def _draw_procedural(
    screen: pygame.Surface,
    rect: pygame.Rect,
    border_color: tuple,
    n: int,
) -> None:
    base = _stone_palette(n)
    inner = rect.inflate(-6, -6)
    pts = _polygon_for_stone(inner, n)

    pygame.draw.polygon(screen, base, pts)
    dark = (
        max(0, base[0] - 18),
        max(0, base[1] - 16),
        max(0, base[2] - 14),
    )
    rng = random.Random(n * 9187)
    for _ in range(1 + rng.randint(0, 2)):
        if len(pts) < 3:
            break
        i = rng.randrange(0, len(pts))
        j = (i + rng.randint(2, len(pts) - 1)) % len(pts)
        pygame.draw.line(screen, dark, pts[i], pts[j], 1)

    light = (
        min(255, base[0] + 22),
        min(255, base[1] + 20),
        min(255, base[2] + 18),
    )
    hx = inner.centerx + rng.randint(-3, 3)
    hy = inner.centery + rng.randint(-3, 3)
    pygame.draw.circle(screen, light, (hx, hy), max(2, min(inner.w, inner.h) // 7), 0)

    pygame.draw.polygon(screen, border_color, pts, 2)


def draw_stone(
    screen: pygame.Surface,
    item_id: str,
    rect: pygame.Rect,
    border_color: tuple,
    img_cache: Optional[StoneImageCache] = None,
    image_fit_padding: int = 3,
) -> None:
    if not is_valid_state_id(item_id):
        pygame.draw.rect(screen, (44, 48, 58), rect, border_radius=8)
        pygame.draw.rect(screen, border_color, rect, 2, border_radius=8)
        return

    n = stone_index(item_id) or 1
    img = img_cache.get(item_id) if img_cache else None
    if img is not None:
        blit_image_fit(screen, img, rect, padding=image_fit_padding)
        pygame.draw.rect(screen, border_color, rect, 2, border_radius=8)
        return

    _draw_procedural(screen, rect, border_color, n)
