"""
学习阶段专用界面：题面出现后 3 秒内禁答；之后按下与本题「动作」对应的 Q/W/E 键
（与正式实验一致：公交 Q、轻轨 W、高铁/地铁 E；同站多条同类型线路时与主任务相同取列表中第一条）。
揭示的答案为：执行该动作后下一站（成功移动到了哪一站，即 correct_next_code）。
选对动作键后走 PracticeManager.submit_answer(correct_next_code) 记为答对。
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

import pygame

from experiments.navigation6.app.common.station_names import code_to_station_name
from experiments.navigation6.app.common.transit_action_display import transit_mode_key_letter
from experiments.navigation6.app.practice.practice.question_generator import PoolItem

from .practice_manager import PracticeManager, PracticePhase
from .practice_ui import (
    CARD_PADDING,
    FEEDBACK_CORRECT_DURATION,
    FEEDBACK_WRONG_DURATION,
    MARGIN,
    MAP_HEIGHT,
    MAP_WIDTH,
    MINI_MAP_LEFT_PAD,
    MINI_MAP_TOP_PAD,
    SECTION_GAP,
    SLOT_SIZE,
    PracticeUI,
    _scale_surface_uniform_to_max_side,
)


LEARNING_KEY_LOCK_S = 3.0
# 答案区「下一站」水果图标边长上限
REVEAL_NEXT_STATION_ICON_MAX = 52

# 与 experiments.navigation6.app.experiment.main 一致
_KEY_TO_TRANSIT_MODE = {
    pygame.K_q: "bus",
    pygame.K_w: "light_rail",
    pygame.K_e: "metro",
}


def _transit_modes_from_lines(transit_lines: List[Dict[str, Any]]) -> List[str]:
    """从迷你地图用的线路表恢复按 line_index 索引的 mode 列表（缺省填 metro）。"""
    if not transit_lines:
        return []
    n = max(int(d.get("line_index", 0)) for d in transit_lines) + 1
    out = ["metro"] * n
    for d in transit_lines:
        li = int(d.get("line_index", 0))
        m = d.get("mode")
        if isinstance(m, str) and 0 <= li < n:
            out[li] = m
    return out


def _action_index_for_pool_transit_key(
    actions: List[PoolItem],
    transit_modes: List[str],
    key: int,
) -> Optional[int]:
    """按下 Q/W/E 时，返回第一个匹配该交通方式的池项下标（与正式实验按键逻辑一致）。"""
    want_mode = _KEY_TO_TRANSIT_MODE.get(key)
    if want_mode is None:
        return None
    for i, it in enumerate(actions):
        _, _, _, action_key, extra, _ = it
        if action_key not in ("instant_transit_next", "instant_transit_prev") or extra is None:
            continue
        li = int(extra) if not isinstance(extra, int) else extra
        if li < 0 or li >= len(transit_modes):
            continue
        if transit_modes[li] == want_mode:
            return i
    return None


def _pool_item_transit_mode(item: PoolItem, transit_modes: List[str]) -> Optional[str]:
    _, _, _, action_key, extra, _ = item
    if action_key not in ("instant_transit_next", "instant_transit_prev") or extra is None:
        return None
    li = int(extra) if not isinstance(extra, int) else extra
    if li < 0 or li >= len(transit_modes):
        return None
    return transit_modes[li]


def _pool_actions_at_code(full_pool: List[PoolItem], current_code: int) -> List[PoolItem]:
    """当前站可执行的所有池项（每条对应一个动作），顺序稳定便于按键编号。"""
    rows = [it for it in full_pool if it[1] == current_code]
    rows.sort(key=lambda x: (x[3], str(x[4] if x[4] is not None else ""), x[2], x[0]))
    return rows


class PracticeUIKeyedLearning(PracticeUI):
    """仅用于学习阶段：按本题动作键（Q/W/E）+ 3 秒等待；揭示「下一站」为成功到达站。"""

    def __init__(
        self,
        screen: pygame.Surface,
        manager: PracticeManager,
        code_to_cell: Optional[Dict[int, Tuple[int, int]]] = None,
        transit_lines: Optional[List[Dict[str, Any]]] = None,
        transit_modes: Optional[List[str]] = None,
    ):
        super().__init__(screen, manager, code_to_cell=code_to_cell, transit_lines=transit_lines)
        tm = list(transit_modes) if transit_modes else []
        self._transit_modes: List[str] = tm if tm else _transit_modes_from_lines(self.transit_lines)
        self._answer_unlock_at = 0.0
        self.keyed_chosen_action_idx: Optional[int] = None

    def clear_for_next_question(self) -> None:
        super().clear_for_next_question()
        self.keyed_chosen_action_idx = None
        self._answer_unlock_at = time.time() + LEARNING_KEY_LOCK_S

    def _layout(self) -> None:
        w, _ = self.screen.get_size()
        self.candidate_rects.clear()
        content_left, content_width = self._content_bounds(w)
        y_top = MARGIN
        title_h = self.font_lg.get_height()
        badge_h = self.font_sm.get_height()
        header_y = y_top + title_h + badge_h + 16
        card_h = 76
        card_top = header_y + MINI_MAP_TOP_PAD
        prompt_h = self.font_sm.get_height()
        slot_y = card_top + card_h + SECTION_GAP + prompt_h + 12
        content_cx = content_left + content_width // 2
        self.answer_slot_rect = pygame.Rect(content_cx - SLOT_SIZE // 2, slot_y, SLOT_SIZE, SLOT_SIZE)

    def _actions_for_question(self) -> List[PoolItem]:
        q = self.manager.current_question
        if not q:
            return []
        pool = self.manager.question_generator.get_full_pool()
        return _pool_actions_at_code(pool, q.current_code)

    @staticmethod
    def _correct_action_index(q, actions: List[PoolItem]) -> int:
        for i, it in enumerate(actions):
            if it[0] == q.question_id:
                return i
        return 0

    def draw(self, dt: float) -> None:
        self.screen.fill((32, 34, 40))
        w, h = self.screen.get_size()
        content_left, content_width = self._content_bounds(w)
        content_cx = content_left + content_width // 2

        phase = self.manager.get_current_phase()
        if phase == PracticePhase.COMPLETE:
            return

        q = self.manager.current_question
        if not q:
            self._layout()
            return
        self._layout()

        actions = self._actions_for_question()
        n_act = len(actions)

        y_top = MARGIN
        phase_text = "学习阶段（键控·动作→下一站）"
        phase_color = (120, 180, 255)
        title = self.font_lg.render("Navigation6 练习 v2（学习：按键看下一站）", True, (240, 240, 255))
        self.screen.blit(title, (MARGIN, y_top))
        badge = self.font_sm.render(phase_text, True, phase_color)
        badge_r = badge.get_rect(topleft=(MARGIN, y_top + title.get_height() + 4))
        self.screen.blit(badge, badge_r)

        stats = self.manager.get_statistics()
        stat_text = f"学习 {stats['learning_count']} 题 · 测试 {stats['test_count']} 题"
        if stats["learning_count"] > 0:
            stat_text += f" · 正确率 {stats['learning_accuracy']:.0%}"
        surf = self.font_sm.render(stat_text, True, (150, 155, 170))
        self.screen.blit(surf, (w - surf.get_width() - MARGIN, y_top + title.get_height() + 4))
        y = y_top + title.get_height() + badge.get_height() + 16

        if self.code_to_cell and q:
            map_y = y + MINI_MAP_TOP_PAD
            map_rect = pygame.Rect(MARGIN + MINI_MAP_LEFT_PAD, map_y, MAP_WIDTH, MAP_HEIGHT)
            pygame.draw.rect(self.screen, (42, 46, 54), map_rect, border_radius=8)
            pygame.draw.rect(self.screen, (70, 76, 90), map_rect, 1, border_radius=8)
            self._draw_mini_map(map_rect, q.current_code, q.correct_next_code, phase)

        card_y = y + MINI_MAP_TOP_PAD
        card_h = 76
        card_rect = pygame.Rect(content_left, card_y, content_width, card_h)
        pygame.draw.rect(self.screen, (42, 46, 54), card_rect, border_radius=12)
        pygame.draw.rect(self.screen, (70, 76, 90), card_rect, 1, border_radius=12)
        inner_x = card_rect.x + CARD_PADDING
        inner_y = card_rect.y + CARD_PADDING
        txt = self.font_md.render(f"当前站点：{code_to_station_name(q.current_code)}", True, (220, 222, 235))
        self.screen.blit(txt, (inner_x, inner_y))
        action_txt = self.font_sm.render(f"本题动作：{q.action_label}", True, (180, 190, 210))
        self.screen.blit(action_txt, (inner_x, inner_y + 32))
        y = card_y + card_h + SECTION_GAP

        now = time.time()
        locked = now < self._answer_unlock_at
        remain = max(0.0, self._answer_unlock_at - now)
        if n_act == 0:
            err = self.font_sm.render("无法列出本站动作（题库异常）", True, (239, 68, 68))
            self.screen.blit(err, (content_left + 8, y))
        elif locked:
            prompt = self.font_sm.render(
                f"请等待 {remain:.1f} 秒后，按键执行本题动作",
                True,
                (200, 180, 120),
            )
            self.screen.blit(prompt, (prompt.get_rect(centerx=content_cx, y=y).topleft))
        else:
            prompt = self.font_sm.render(
                "请按键执行本题动作",
                True,
                (170, 185, 200),
            )
            self.screen.blit(prompt, (prompt.get_rect(centerx=content_cx, y=y).topleft))
        y += 28

        options_top = y
        ay = y
        line_h = 22
        max_lines = min(n_act, 12)
        for i in range(max_lines):
            it = actions[i]
            label = it[2]
            if len(label) > 42:
                label = label[:39] + "..."
            mode = _pool_item_transit_mode(it, self._transit_modes)
            letter = transit_mode_key_letter(mode) if mode else "?"
            line = self.font_sm.render(f"[{letter}]  {label}", True, (210, 212, 225))
            self.screen.blit(line, (content_left + 12, ay))
            ay += line_h
        if n_act > max_lines:
            more = self.font_sm.render(f"… 共 {n_act} 项，仅显示前 {max_lines} 项", True, (130, 135, 150))
            self.screen.blit(more, (content_left + 12, ay))
            ay += line_h
        options_bottom = ay

        reveal_y = ay + 12
        if self.keyed_chosen_action_idx is not None and 0 <= self.keyed_chosen_action_idx < n_act:
            panel_h = 150 if self.feedback == "wrong" else 128
            panel = pygame.Rect(content_left + 8, reveal_y, content_width - 16, panel_h)
            pygame.draw.rect(self.screen, (48, 52, 60), panel, border_radius=10)
            bc = (100, 108, 120)
            if self.feedback == "correct":
                bc = (34, 197, 94)
            elif self.feedback == "wrong":
                bc = (239, 68, 68)
            pygame.draw.rect(self.screen, bc, panel, 2, border_radius=10)
            dest_name = code_to_station_name(q.correct_next_code)
            ly = panel.y + 10
            ans_title = self.font_sm.render("答案（执行本题动作后，成功到达）", True, (190, 195, 210))
            self.screen.blit(ans_title, (panel.x + 12, ly))
            ly += 24
            row_top = ly
            l_main = self.font_md.render(f"下一站：{dest_name}", True, (240, 245, 255))
            raw_next = self._station_icons_raw.get(q.correct_next_code)
            icon_col_w = 0
            if raw_next:
                ic = _scale_surface_uniform_to_max_side(raw_next, REVEAL_NEXT_STATION_ICON_MAX)
                icon_col_w = ic.get_width()
                ir = ic.get_rect(left=panel.x + 14, centery=row_top + max(REVEAL_NEXT_STATION_ICON_MAX, l_main.get_height()) // 2)
                self.screen.blit(ic, ir)
            text_x = panel.x + 14 + (icon_col_w + 10 if icon_col_w else 0)
            tr = l_main.get_rect(left=text_x, centery=row_top + max(REVEAL_NEXT_STATION_ICON_MAX, l_main.get_height()) // 2)
            self.screen.blit(l_main, tr)
            ly = row_top + max(REVEAL_NEXT_STATION_ICON_MAX, l_main.get_height()) + 10
            if self.feedback == "wrong":
                chosen = actions[self.keyed_chosen_action_idx]
                wrong_hint = self.font_sm.render(
                    f"错误答案，您所选动作会到达：{code_to_station_name(chosen[5])}",
                    True,
                    (230, 200, 200),
                )
                self.screen.blit(wrong_hint, (panel.x + 12, ly))
                ly += 22
            if self.feedback == "correct":
                l3 = self.font_sm.render("已按下本题对应动作键", True, (34, 197, 94))
            elif self.feedback == "wrong":
                l3 = self.font_sm.render("请重试：按与本题动作相同的 Q / W / E 键", True, (239, 68, 68))
            else:
                l3 = None
            if l3:
                self.screen.blit(l3, (panel.x + 12, ly))

        if self.phase_switch_message and self.phase_switch_timer > 0:
            msg = self.font_md.render(self.phase_switch_message, True, (100, 200, 255))
            mr = msg.get_rect(center=(content_cx, 58))
            self.screen.blit(msg, mr)

        # 「正确/错误」放在选项列表右侧，避免与答案提示框、空答案槽重叠
        feedback_right = w - MARGIN - 8
        if options_bottom > options_top:
            feedback_cy = (options_top + options_bottom) // 2
        else:
            feedback_cy = options_top + line_h // 2
        if self.feedback == "correct" and self.keyed_chosen_action_idx is not None:
            msg = self.font_md.render("正确！", True, (34, 197, 94))
            mr = msg.get_rect(midright=(feedback_right, feedback_cy))
            self.screen.blit(msg, mr)
        elif self.feedback == "wrong" and self.keyed_chosen_action_idx is not None:
            msg = self.font_md.render("错误", True, (239, 68, 68))
            mr = msg.get_rect(midright=(feedback_right, feedback_cy))
            self.screen.blit(msg, mr)

        esc_hint = self.font_sm.render("ESC 退出", True, (100, 105, 115))
        self.screen.blit(esc_hint, (w - esc_hint.get_width() - MARGIN, h - MARGIN - esc_hint.get_height()))
        self._draw_coordinate_axis(w, h)

    def handle_events(self, events: list) -> bool:
        for event in events:
            if event.type != pygame.KEYDOWN:
                continue
            q = self.manager.current_question
            if not q:
                continue
            if self.feedback and self.feedback_timer > 0:
                continue
            if time.time() < self._answer_unlock_at:
                continue
            actions = self._actions_for_question()
            n_act = len(actions)
            if n_act == 0:
                continue
            idx = _action_index_for_pool_transit_key(actions, self._transit_modes, event.key)
            if idx is None:
                continue
            correct_idx = self._correct_action_index(q, actions)
            self.keyed_chosen_action_idx = idx
            if idx == correct_idx:
                correct, phase_changed = self.manager.submit_answer(q.correct_next_code)
                if phase_changed and self.manager.get_current_phase() == PracticePhase.TEST:
                    self.phase_switch_message = "进入测试阶段！请使用拖拽作答，作答后会短暂提示是否正确。"
                    self.phase_switch_timer = 2.0
                self.feedback = "correct"
                self.feedback_timer = FEEDBACK_CORRECT_DURATION
                return True
            self.feedback = "wrong"
            self.feedback_timer = FEEDBACK_WRONG_DURATION
        return False

    def update(self, dt: float) -> bool:
        had_feedback = bool(self.feedback)
        r = super().update(dt)
        if had_feedback and self.feedback is None and self.manager.is_learning_phase():
            self.keyed_chosen_action_idx = None
        return r
