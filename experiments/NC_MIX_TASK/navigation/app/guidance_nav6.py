"""
选图后的正式任务说明页（Enter/空格继续）。
"""

from __future__ import annotations

import pygame


COLOR_BG = (28, 31, 38)
COLOR_TITLE = (230, 235, 255)
COLOR_BODY = (205, 210, 225)
COLOR_HINT = (150, 185, 220)


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
    color: tuple,
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


def run_navigation6_guidance_screen(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    *,
    map_label: str,
) -> bool:
    """
    正式实验前指导语。Enter/空格进入；Esc/关闭窗口返回 False。
    """
    pygame.display.set_caption("Navigation6 - 任务说明")
    w, h = screen.get_size()
    margin_x = min(28, max(16, w // 28))
    text_w = w - margin_x * 2
    font_title = _font(26)
    font_body = _font(16)
    font_hint = _font(15)

    body = (
        "感谢您参与本研究。本任务为公共交通导航：每个试次会给出起点与目标站点（显示为彩色几何图形），"
        "请您通过「公交 / 地铁 / 环线」在站点间移动，尽快到达目标。"
        "每种交通工具有深色（向前）和浅色（向后）两条线，表示不同行进方向。"
        "可用鼠标点击示意图中的线路，或使用键盘快捷键："
        "公交前进 Q、后退 E；地铁前进 A、后退 D；环线 W。"
        "若当前位置无法执行某操作，对应线路会短暂红色提示。"
        "请在安静环境中尽量依据直觉作答。"
    )

    while True:
        screen.fill(COLOR_BG)
        y = 32
        y = _draw_wrapped(
            screen, font_title, "正式实验 · 任务说明", margin_x, y, text_w, COLOR_TITLE
        )
        y += 8
        y = _draw_wrapped(
            screen, font_body, f"当前地图：{map_label}", margin_x, y, text_w, (180, 200, 230)
        )
        y += 12
        y = _draw_wrapped(screen, font_body, body, margin_x, y, text_w, COLOR_BODY)

        _draw_wrapped(
            screen,
            font_hint,
            "Enter / 空格 开始  ·  Esc 退出",
            margin_x,
            h - 44,
            text_w,
            COLOR_HINT,
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
        clock.tick(30)
