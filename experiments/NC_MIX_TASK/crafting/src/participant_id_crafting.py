"""
选图前采集被试编号（图形界面）。
"""

from __future__ import annotations

from typing import Optional

import pygame

WINDOW_W = 1000
WINDOW_H = 820
MARGIN = 40
COLOR_BG = (28, 31, 38)
COLOR_TITLE = (220, 228, 245)
COLOR_BODY = (200, 206, 220)
COLOR_MUTED = (130, 142, 168)
COLOR_ACCENT = (96, 165, 250)
COLOR_INPUT_BG = (48, 52, 62)
COLOR_INPUT_EDGE = (96, 165, 250)
MAX_ID_LEN = 48


def _font(size: int) -> pygame.font.Font:
    try:
        return pygame.font.SysFont("SimHei", size)
    except Exception:
        return pygame.font.SysFont("arial", size)


def run_participant_id_screen(screen: pygame.Surface, clock: pygame.time.Clock) -> Optional[str]:
    """
    被试输入编号后按 Enter 确认；Esc 取消（返回 None）。
    允许字母、数字、下划线、连字符及常见可打印字符（便于实验室编号规则）。
    """
    text = ""
    pygame.display.set_caption("Crafting - 被试编号")

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type != pygame.KEYDOWN:
                continue
            if event.key == pygame.K_ESCAPE:
                return None
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                stripped = text.strip()
                if stripped:
                    return stripped
                continue
            if event.key == pygame.K_BACKSPACE:
                text = text[:-1]
                continue
            if event.key == pygame.K_v and (event.mod & pygame.KMOD_CTRL):
                continue
            ch = event.unicode
            if ch and ch.isprintable() and len(text) < MAX_ID_LEN:
                text += ch

        screen.fill(COLOR_BG)
        title = _font(30).render("请输入被试编号", True, COLOR_TITLE)
        screen.blit(title, (MARGIN, 120))
        hint = _font(18).render("完成后按 Enter 开始；Esc 退出", True, COLOR_MUTED)
        screen.blit(hint, (MARGIN, 168))

        box = pygame.Rect(MARGIN, 230, WINDOW_W - MARGIN * 2, 52)
        pygame.draw.rect(screen, COLOR_INPUT_BG, box, border_radius=10)
        pygame.draw.rect(screen, COLOR_INPUT_EDGE, box, 2, border_radius=10)
        display = text + ("|" if (pygame.time.get_ticks() // 530) % 2 else "")
        surf = _font(24).render(display if display else " ", True, COLOR_BODY)
        screen.blit(surf, (box.x + 14, box.centery - surf.get_height() // 2))

        foot = _font(15).render(
            "编号将写入行为数据文件名与日志列 Participant；命令行可用 -p 跳过本页",
            True,
            COLOR_MUTED,
        )
        screen.blit(foot, (MARGIN, 320))

        pygame.display.flip()
        clock.tick(30)
