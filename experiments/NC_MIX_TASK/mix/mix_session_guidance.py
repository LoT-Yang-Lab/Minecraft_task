"""
NC_MIX_TASK：每个 Session 开始前的统一指导语（排版分行、段落间距）。
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

import pygame

COLOR_BG = (28, 31, 38)
COLOR_TITLE = (230, 235, 255)
COLOR_BODY = (205, 210, 225)
COLOR_HINT = (150, 185, 220)
COLOR_SECTION = (180, 200, 230)

DomainKind = Literal["navigation", "crafting", "mixed"]


def _font(size: int) -> pygame.font.Font:
    try:
        return pygame.font.SysFont("SimHei", size)
    except Exception:
        return pygame.font.SysFont("arial", size)


def _draw_wrapped_line(
    screen: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    x: int,
    y: int,
    width: int,
    color: tuple,
    line_gap: int = 2,
) -> int:
    if not text.strip():
        return y
    line_h = font.get_linesize() + line_gap
    cur = ""
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


def _paragraphs_for_domain(domain: DomainKind, session_num: int) -> Dict[str, object]:
    """指导语：分段列表，段与段之间留空行。"""
    if domain == "navigation":
        return {
            "title": f"Session {session_num} · 导航阶段",
            "subtitle": "任务概要",
            "paragraphs": [
                "本阶段为公共交通导航。每个试次会给出起点与目标站点（显示为彩色几何图形），请您尽快到达目标。",
                "操作：点击示意图中的彩色线路，或使用快捷键——公交 Q / E，地铁 A / D，环线 W。"
                "每种交通工具有深色（向前）和浅色（向后）两条线，表示不同方向。",
                "若当前位置无法执行该操作，对应线路会短暂标红。",
                "请在安静环境中作答，尽量依据第一反应，不必过度推敲。",
            ],
        }
    if domain == "crafting":
        return {
            "title": f"Session {session_num} · 合成阶段",
            "subtitle": "任务概要",
            "paragraphs": [
                "本阶段为石块变换（合成）任务。请依照地图规则，将起始石块转变为目标石块。",
                "通过下方三枚药水的固定操作完成订单；键位与练习一致（Q/E、A/D、W）。",
                "完成当前订单后按提示继续；可随时按 Esc 退出并保存本阶段数据。",
            ],
        }
    # mixed
    return {
        "title": f"Session {session_num} · 混合任务",
        "subtitle": "任务概要",
        "paragraphs": [
            "本阶段将交替出现「导航」与「合成」两类试次，请始终以当前屏幕标题与说明为准。",
            "导航：点击深色/浅色线路或 Q/E、A/D、W 选择交通工具方向。合成：用药水键变换石块以达成目标。",
            "两类任务操作不同，切换时请先看清界面再操作；保持节奏稳定即可。",
        ],
    }


def run_mix_session_guidance_screen(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    *,
    session_num: int,
    domain: DomainKind,
    total_trials_in_session: Optional[int] = None,
) -> bool:
    """
    Session 开始前指导语。Enter / 空格 继续；Esc / 关窗 返回 False。
    """
    pygame.display.set_caption("NC Mix — 阶段说明")
    w, h = screen.get_size()
    margin_x = min(36, max(20, w // 28))
    text_w = w - margin_x * 2

    font_title = _font(26)
    font_sub = _font(17)
    font_body = _font(16)
    font_hint = _font(15)

    spec = _paragraphs_for_domain(domain, session_num)
    title = str(spec["title"])
    subtitle = str(spec["subtitle"])
    paragraphs: List[str] = list(spec["paragraphs"])

    section_gap = font_body.get_linesize() + 8
    para_gap = font_body.get_linesize() + 4

    while True:
        screen.fill(COLOR_BG)
        y = 36

        y = _draw_wrapped_line(screen, font_title, title, margin_x, y, text_w, COLOR_TITLE)
        y += section_gap

        y = _draw_wrapped_line(screen, font_sub, subtitle, margin_x, y, text_w, COLOR_SECTION)
        y += 10

        if total_trials_in_session is not None and total_trials_in_session > 0:
            y = _draw_wrapped_line(
                screen,
                font_body,
                f"本阶段共 {total_trials_in_session} 个试次，将按顺序从第 1 试次开始。",
                margin_x,
                y,
                text_w,
                COLOR_BODY,
            )
            y += 10

        for i, para in enumerate(paragraphs):
            if i:
                y += 6
            y0 = y
            y = _draw_wrapped_line(screen, font_body, para, margin_x, y, text_w, COLOR_BODY)
            if y - y0 < para_gap and i < len(paragraphs) - 1:
                y += 4

        _draw_wrapped_line(
            screen,
            font_hint,
            "Enter / 空格 开始本阶段   ·   Esc 退出",
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
