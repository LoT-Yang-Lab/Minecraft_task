"""
练习界面：题干（当前站点+动作）、答案槽、候选区为可拖拽的水果站块，拖拽与反馈。
可选左侧迷你地图显示当前题目对应地图与高亮位置。
"""
from pathlib import Path

import math
import pygame
from typing import Optional, Dict, Tuple, List, Any

from experiments.navigation6.app.common.station_names import (
    STATION_ICON_ENGLISH_NAMES,
    code_to_station_icon_stem,
    code_to_station_name,
)
from experiments.navigation6.app.common.transit_curve_geometry import (
    transit_bezier_control,
    transit_bezier_tangent_at_mid,
    transit_segment_polyline,
    TRANSIT_CURVE_MIN_LEN,
)
from .practice_manager import PracticeManager, PracticePhase


# 候选站点拖拽块（加大以避免水果图与站名重叠；总宽需适配 640 窗宽下的右侧内容区）
ITEM_SIZE = 70
SLOT_SIZE = 88
MARGIN = 28
SECTION_GAP = 26
CARD_PADDING = 20
FEEDBACK_CORRECT_DURATION = 1.2
FEEDBACK_WRONG_DURATION = 1.0
GAP_OPTIONS = 5
MAP_WIDTH = 168
MAP_HEIGHT = 176
# 迷你地图相对标题行的下移、相对窗口左缘的右移（与 _content_bounds / map_rect 同步）
MINI_MAP_TOP_PAD = 28
MINI_MAP_LEFT_PAD = 18
MAP_PADDING = 4
AXIS_SIZE = 76
AXIS_MARGIN_LEFT = 20
AXIS_MARGIN_BOTTOM = 20

# 与地图编辑器线路色一致：公交蓝 / 地铁黄 / 轻轨绿
COLOR_TRANSIT_BUS = (60, 120, 220)
COLOR_TRANSIT_METRO = (240, 210, 60)
COLOR_TRANSIT_LIGHT_RAIL = (70, 190, 110)
COLOR_TRANSIT_UNKNOWN = (140, 145, 160)
# 迷你地图上「当前站」人物标记（向下.png）；水果在迷你地图上的绘制边长与此一致
START_ICON_MAX_PX = 26
# 水果图预缩放缓存上限（再按与人物相同的目标边长绘制到迷你地图）
MINI_MAP_STATION_ICON_MAX = 56
# 答案槽内图标区上限（实际边长由槽内矩形动态计算）
SLOT_INNER_ICON_MAX = 44


def _app_assets_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "assets"


def _iter_station_asset_paths(assets_root: Path, stations_dir: Path, code: int):
    exts = (".png", ".webp", ".jpg", ".jpeg")
    names: List[str] = []
    stem = code_to_station_icon_stem(code)
    if stem:
        names.append(stem)
    if 1 <= code <= len(STATION_ICON_ENGLISH_NAMES):
        en = STATION_ICON_ENGLISH_NAMES[code - 1]
        if en not in names:
            names.append(en)
    names.append(str(code))
    for base in (stations_dir, assets_root):
        for name in names:
            for ext in exts:
                yield base / f"{name}{ext}"


def _load_raw_station_icons() -> Dict[int, pygame.Surface]:
    """从 app/assets/stations/ 或 app/assets/ 加载 1～9 号站水果图（文件名见 station_names）。"""
    assets = _app_assets_dir()
    stations = assets / "stations"
    out: Dict[int, pygame.Surface] = {}
    for code in range(1, 10):
        surf: Optional[pygame.Surface] = None
        for path in _iter_station_asset_paths(assets, stations, code):
            if not path.is_file():
                continue
            try:
                surf = pygame.image.load(str(path)).convert_alpha()
                break
            except Exception:
                continue
        if surf is not None:
            out[code] = surf
    return out


def _scale_surface_max_side(surf: pygame.Surface, max_side: int) -> pygame.Surface:
    w, h = surf.get_size()
    if w <= 0 or h <= 0:
        return surf
    m = max(w, h)
    if m <= max_side:
        return surf
    s = max_side / m
    nw, nh = max(1, int(w * s)), max(1, int(h * s))
    return pygame.transform.smoothscale(surf, (nw, nh))


def _scale_surface_uniform_to_max_side(surf: pygame.Surface, max_side: int) -> pygame.Surface:
    """长宽同比缩放，使 max(宽,高) == max_side（可放大或缩小）。"""
    w, h = surf.get_size()
    if w <= 0 or h <= 0 or max_side < 1:
        return surf
    m = max(w, h)
    if m == max_side:
        return surf
    s = max_side / m
    nw, nh = max(1, int(round(w * s))), max(1, int(round(h * s)))
    return pygame.transform.smoothscale(surf, (nw, nh))


def _scale_station_icon_dict(raw: Dict[int, pygame.Surface], max_side: int) -> Dict[int, pygame.Surface]:
    return {c: _scale_surface_max_side(s, max_side) for c, s in raw.items()}


def _draw_arrow_head_mini(
    screen: pygame.Surface,
    sx1: float,
    sy1: float,
    sx2: float,
    sy2: float,
    color: tuple,
    arrow_len: int = 7,
    arrow_hw: int = 4,
    at_midpoint: bool = False,
) -> None:
    """与编辑器 _draw_arrow_head 相同逻辑，尺寸适配迷你地图。"""
    dx = sx2 - sx1
    dy = sy2 - sy1
    length = (dx * dx + dy * dy) ** 0.5
    if length < 1e-6:
        return
    ux = dx / length
    uy = dy / length
    if at_midpoint:
        tip = ((sx1 + sx2) / 2, (sy1 + sy2) / 2)
    else:
        tip = (sx2, sy2)
    base_center_x = tip[0] - ux * arrow_len
    base_center_y = tip[1] - uy * arrow_len
    base_left = (base_center_x - uy * arrow_hw, base_center_y + ux * arrow_hw)
    base_right = (base_center_x + uy * arrow_hw, base_center_y - ux * arrow_hw)
    pygame.draw.polygon(screen, color, [tip, base_left, base_right])


def _load_start_marker_surface() -> Optional[pygame.Surface]:
    """练习迷你地图上标记题目起点（当前站点），使用 shared/assets/向下.png；尺寸上限见 START_ICON_MAX_PX（小于水果）。"""
    root = Path(__file__).resolve().parents[5]
    p = root / "shared" / "assets" / "向下.png"
    if not p.is_file():
        return None
    try:
        img = pygame.image.load(str(p)).convert_alpha()
        w, h = img.get_size()
        if w <= 0 or h <= 0:
            return None
        m = max(w, h)
        if m > START_ICON_MAX_PX:
            s = START_ICON_MAX_PX / m
            nw, nh = max(1, int(w * s)), max(1, int(h * s))
            img = pygame.transform.smoothscale(img, (nw, nh))
        return img
    except Exception:
        return None


def _font(size: int) -> pygame.font.Font:
    try:
        return pygame.font.SysFont("SimHei", size)
    except Exception:
        return pygame.font.SysFont("arial", size)


class PracticeUI:
    def __init__(
        self,
        screen: pygame.Surface,
        manager: PracticeManager,
        code_to_cell: Optional[Dict[int, Tuple[int, int]]] = None,
        transit_lines: Optional[List[Dict[str, Any]]] = None,
    ):
        self.screen = screen
        self.manager = manager
        self.code_to_cell = code_to_cell
        # 每条含 mode、path、line_index、segment_curve、segment_straight（与编辑器一致，用于弧线路径）
        self.transit_lines: List[Dict[str, Any]] = transit_lines or []
        self._start_marker = _load_start_marker_surface()
        if self._start_marker:
            sw, sh = self._start_marker.get_size()
            self._mini_map_icon_max_side = max(sw, sh) if sw > 0 and sh > 0 else START_ICON_MAX_PX
        else:
            self._mini_map_icon_max_side = START_ICON_MAX_PX
        self._station_icons_raw = _load_raw_station_icons()
        self._station_icons_mini = _scale_station_icon_dict(self._station_icons_raw, MINI_MAP_STATION_ICON_MAX)
        self.font_sm = _font(16)
        self.font_station_block = _font(14)
        self.font_md = _font(20)
        self.font_lg = _font(24)

        self.dragging_code: Optional[int] = None
        self.drag_pos: Optional[tuple] = None
        self.slot_filled: Optional[int] = None
        self.feedback: Optional[str] = None
        self.feedback_timer: float = 0.0
        self.candidate_rects: Dict[int, pygame.Rect] = {}
        self.answer_slot_rect: Optional[pygame.Rect] = None
        self.phase_switch_message: Optional[str] = None
        self.phase_switch_timer: float = 0.0

    def _draw_station_block(self, code: int, rect: pygame.Rect, border_color: tuple) -> None:
        """绘制站点块：上方水果图、下方站名，避免重叠。"""
        pygame.draw.rect(self.screen, (50, 54, 62), rect, border_radius=8)
        pygame.draw.rect(self.screen, border_color, rect, 2, border_radius=8)
        label = code_to_station_name(code)
        pad = 6
        text = self.font_station_block.render(label, True, (220, 222, 235))
        text_h = text.get_height()
        bottom_reserve = text_h + pad + 4
        icon_area_h = max(10, rect.h - bottom_reserve)
        icon_max = max(8, min(rect.w - 2 * pad, icon_area_h - 2))
        raw = self._station_icons_raw.get(code)
        if raw and icon_max >= 10:
            draw_ic = _scale_surface_uniform_to_max_side(raw, icon_max)
            icon_top = rect.y + pad
            ir = draw_ic.get_rect(centerx=rect.centerx, top=icon_top)
            if ir.bottom > rect.bottom - bottom_reserve:
                ir.centery = rect.y + pad + icon_area_h // 2
            self.screen.blit(draw_ic, ir)
            tr = text.get_rect(centerx=rect.centerx, bottom=rect.bottom - pad)
            self.screen.blit(text, tr)
        else:
            tr = text.get_rect(center=rect.center)
            self.screen.blit(text, tr)

    def _draw_station_block_in_slot(self, code: int, inner: pygame.Rect, border_color: tuple) -> None:
        """答案槽内块：略小的字号与图标上限，布局同 _draw_station_block。"""
        pygame.draw.rect(self.screen, (50, 54, 62), inner, border_radius=8)
        pygame.draw.rect(self.screen, border_color, inner, 2, border_radius=8)
        label = code_to_station_name(code)
        pad = 5
        text = self.font_station_block.render(label, True, (220, 222, 235))
        bottom_reserve = text.get_height() + pad + 4
        icon_area_h = max(8, inner.h - bottom_reserve)
        icon_max = max(8, min(SLOT_INNER_ICON_MAX, inner.w - 2 * pad, icon_area_h - 2))
        raw = self._station_icons_raw.get(code)
        if raw:
            draw_ic = _scale_surface_uniform_to_max_side(raw, icon_max)
            ir = draw_ic.get_rect(centerx=inner.centerx, top=inner.y + pad)
            if ir.bottom > inner.bottom - bottom_reserve:
                ir.centery = inner.y + pad + icon_area_h // 2
            self.screen.blit(draw_ic, ir)
            tr = text.get_rect(centerx=inner.centerx, bottom=inner.bottom - pad)
            self.screen.blit(text, tr)
        else:
            tr = text.get_rect(center=inner.center)
            self.screen.blit(text, tr)

    def _draw_coordinate_axis(self, screen_w: int, screen_h: int) -> None:
        """Navigation6 无东南西北步行，不绘制方向坐标系。"""
        return

    def _content_bounds(self, w: int):
        """返回 (content_left, content_width)。有地图时内容区在右侧，否则全宽。"""
        if self.code_to_cell:
            content_left = MARGIN + MINI_MAP_LEFT_PAD + MAP_WIDTH + SECTION_GAP
        else:
            content_left = MARGIN
        content_width = w - content_left - MARGIN
        return content_left, content_width

    def _draw_mini_map(
        self,
        map_rect: pygame.Rect,
        current_code: int,
        correct_next_code: int,
        phase: PracticePhase,
    ) -> None:
        """在 map_rect 内绘制迷你地图：可行走格 + 当前格高亮 + 学习阶段正确下一站绿色。"""
        if not self.code_to_cell:
            return
        cells = list(self.code_to_cell.items())
        if not cells:
            return
        gxs = [c[1][0] for c in cells]
        gys = [c[1][1] for c in cells]
        min_gx, max_gx = min(gxs), max(gxs)
        min_gy, max_gy = min(gys), max(gys)
        span_x = max_gx - min_gx + 1
        span_y = max_gy - min_gy + 1
        inner_w = map_rect.w - 2 * MAP_PADDING
        inner_h = map_rect.h - 2 * MAP_PADDING
        cell_w = inner_w / span_x
        cell_h = inner_h / span_y
        base_x = map_rect.x + MAP_PADDING
        base_y = map_rect.y + MAP_PADDING

        def cell_center(gx: int, gy: int) -> Tuple[int, int]:
            cx = base_x + (gx - min_gx + 0.5) * cell_w
            cy = base_y + (gy - min_gy + 0.5) * cell_h
            return int(cx), int(cy)

        def cell_center_float(gx: int, gy: int) -> Tuple[float, float]:
            return (
                base_x + (gx - min_gx + 0.5) * cell_w,
                base_y + (gy - min_gy + 0.5) * cell_h,
            )

        def _line_color_for_mode(mode: str) -> Tuple[int, int, int]:
            if mode == "bus":
                return COLOR_TRANSIT_BUS
            if mode == "metro":
                return COLOR_TRANSIT_METRO
            if mode == "light_rail":
                return COLOR_TRANSIT_LIGHT_RAIL
            return COLOR_TRANSIT_UNKNOWN

        def _draw_transit_segment_arrow(
            ax: float,
            ay: float,
            bx: float,
            by: float,
            line_idx: int,
            seg_idx: int,
            bias: float,
            straight: bool,
            color: Tuple[int, int, int],
            bidirectional: bool = False,
        ) -> None:
            L = math.hypot(bx - ax, by - ay)
            if L < 2:
                return
            if straight or L < TRANSIT_CURVE_MIN_LEN:
                _draw_arrow_head_mini(self.screen, ax, ay, bx, by, color, 7, 4, at_midpoint=True)
                if bidirectional:
                    _draw_arrow_head_mini(self.screen, bx, by, ax, ay, color, 7, 4, at_midpoint=True)
            else:
                cx, cy = transit_bezier_control(ax, ay, bx, by, line_idx, seg_idx, bias)
                px, py, ux, uy = transit_bezier_tangent_at_mid(ax, ay, bx, by, cx, cy)
                tip_x, tip_y = px + ux * 4.0, py + uy * 4.0
                bx_a, by_a = px - ux * 9.0, py - uy * 9.0
                _draw_arrow_head_mini(self.screen, bx_a, by_a, tip_x, tip_y, color, 7, 4, at_midpoint=False)
                if bidirectional:
                    _draw_arrow_head_mini(self.screen, tip_x, tip_y, bx_a, by_a, color, 7, 4, at_midpoint=False)

        # 公交 / 地铁 / 轻轨：与编辑器相同弧度的折线采样 + 箭头
        for spec in self.transit_lines:
            path = spec.get("path") or []
            if len(path) < 2:
                continue
            mode = str(spec.get("mode", "metro"))
            line_idx = int(spec.get("line_index", 0))
            sc = spec.get("segment_curve") or []
            st = spec.get("segment_straight") or []
            line_color = _line_color_for_mode(mode)
            bidirectional = mode in ("bus", "light_rail")
            for i in range(len(path) - 1):
                ax, ay = cell_center_float(path[i][0], path[i][1])
                bx, by = cell_center_float(path[i + 1][0], path[i + 1][1])
                bias = float(sc[i]) if i < len(sc) else 0.0
                straight = bool(st[i]) if i < len(st) else False
                poly = transit_segment_polyline(ax, ay, bx, by, line_idx, i, bias, straight)
                if len(poly) >= 2:
                    pts = [(int(round(p[0])), int(round(p[1]))) for p in poly]
                    pygame.draw.lines(self.screen, line_color, False, pts, 2)
                _draw_transit_segment_arrow(
                    ax, ay, bx, by, line_idx, i, bias, straight, line_color, bidirectional
                )

        color_current = (80, 120, 200)
        color_correct_next = (34, 197, 94)
        color_normal = (60, 64, 72)
        border_normal = (80, 85, 95)
        for code, (gx, gy) in cells:
            rx = base_x + (gx - min_gx) * cell_w
            ry = base_y + (gy - min_gy) * cell_h
            rw = max(2, int(cell_w) - 1)
            rh = max(2, int(cell_h) - 1)
            rect = pygame.Rect(int(rx), int(ry), rw, rh)
            if code == current_code:
                pygame.draw.rect(self.screen, color_current, rect, border_radius=2)
                pygame.draw.rect(self.screen, (120, 160, 255), rect, 2, border_radius=2)
            elif phase == PracticePhase.LEARNING and code == correct_next_code:
                pygame.draw.rect(self.screen, color_correct_next, rect, border_radius=2)
                pygame.draw.rect(self.screen, (60, 220, 120), rect, 2, border_radius=2)
            else:
                pygame.draw.rect(self.screen, color_normal, rect, border_radius=2)
                pygame.draw.rect(self.screen, border_normal, rect, 1, border_radius=2)

        # 水果站图标：与「向下」人物同一最大边长（人物尺寸由 START_ICON_MAX_PX 与素材决定，此处不改）
        fruit_map_max = max(8, self._mini_map_icon_max_side)

        # 水果站图标（叠在格子上，位于线路与红箭头之间）
        for code, (gx, gy) in cells:
            ic = self._station_icons_mini.get(code)
            if not ic:
                continue
            rx = base_x + (gx - min_gx) * cell_w
            ry = base_y + (gy - min_gy) * cell_h
            rw = max(2, int(cell_w) - 1)
            rh = max(2, int(cell_h) - 1)
            rect = pygame.Rect(int(rx), int(ry), rw, rh)
            draw_ic = _scale_surface_uniform_to_max_side(ic, fruit_map_max)
            ir = draw_ic.get_rect(center=rect.center)
            self.screen.blit(draw_ic, ir)

        # 当前题目路径（红色）：若与某条线路的一段重合则沿曲线绘制，否则直线。
        cur_pos = self.code_to_cell.get(current_code)
        nxt_pos = self.code_to_cell.get(correct_next_code)
        question_color = (239, 68, 68)
        if cur_pos and nxt_pos and cur_pos != nxt_pos:
            drawn_curve = False
            for spec in self.transit_lines:
                path = spec.get("path") or []
                line_idx = int(spec.get("line_index", 0))
                sc = spec.get("segment_curve") or []
                st = spec.get("segment_straight") or []
                for i in range(len(path) - 1):
                    if path[i] != cur_pos or path[i + 1] != nxt_pos:
                        continue
                    ax, ay = cell_center_float(path[i][0], path[i][1])
                    bx, by = cell_center_float(path[i + 1][0], path[i + 1][1])
                    bias = float(sc[i]) if i < len(sc) else 0.0
                    straight = bool(st[i]) if i < len(st) else False
                    poly = transit_segment_polyline(ax, ay, bx, by, line_idx, i, bias, straight)
                    if len(poly) >= 2:
                        pts = [(int(round(p[0])), int(round(p[1]))) for p in poly]
                        pygame.draw.lines(self.screen, question_color, False, pts, 3)
                    _draw_transit_segment_arrow(ax, ay, bx, by, line_idx, i, bias, straight, question_color)
                    drawn_curve = True
                    break
                if drawn_curve:
                    break
            if not drawn_curve:
                cx1, cy1 = cell_center(cur_pos[0], cur_pos[1])
                cx2, cy2 = cell_center(nxt_pos[0], nxt_pos[1])
                pygame.draw.line(self.screen, question_color, (cx1, cy1), (cx2, cy2), 3)
                dx, dy = cx2 - cx1, cy2 - cy1
                seg_len = (dx * dx + dy * dy) ** 0.5
                if seg_len >= 2:
                    ux, uy = dx / seg_len, dy / seg_len
                    mx, my = (cx1 + cx2) / 2, (cy1 + cy2) / 2
                    tip = (int(mx), int(my))
                    left = (
                        int(mx - ux * 9 - uy * 5),
                        int(my - uy * 9 + ux * 5),
                    )
                    right = (
                        int(mx - ux * 9 + uy * 5),
                        int(my - uy * 9 - ux * 5),
                    )
                    pygame.draw.polygon(self.screen, question_color, [tip, left, right])

        # 题目起点（当前站点）：向下.png 叠在格心之上
        if self._start_marker and cur_pos:
            scx, scy = cell_center(cur_pos[0], cur_pos[1])
            ir = self._start_marker.get_rect(center=(scx, scy))
            self.screen.blit(self._start_marker, ir)

    def _layout(self) -> None:
        w, _ = self.screen.get_size()
        self.candidate_rects.clear()
        content_left, content_width = self._content_bounds(w)

        # 与 draw() 头部布局保持一致（含 MINI_MAP_TOP_PAD），避免提示文字与答案框重叠。
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

        q = self.manager.current_question
        if not q:
            return
        num_opts = len(q.options)
        total_w = num_opts * ITEM_SIZE + (num_opts - 1) * GAP_OPTIONS
        start_x = content_cx - total_w // 2
        opt_y = slot_y + SLOT_SIZE + 20 + 22 + 4
        for i, code in enumerate(q.options):
            rx = start_x + i * (ITEM_SIZE + GAP_OPTIONS)
            self.candidate_rects[code] = pygame.Rect(rx, opt_y, ITEM_SIZE, ITEM_SIZE)

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

        y_top = MARGIN
        phase_text = "学习阶段" if phase == PracticePhase.LEARNING else "测试阶段"
        phase_color = (120, 180, 255) if phase == PracticePhase.LEARNING else (160, 200, 255)
        title = self.font_lg.render("Navigation6 练习（公交/地铁/环线）", True, (240, 240, 255))
        self.screen.blit(title, (MARGIN, y_top))
        badge = self.font_sm.render(phase_text, True, phase_color)
        # 阶段标签单独放在标题下一行，避免在同一行时被遮挡。
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
        action_txt = self.font_sm.render(f"动作：{q.action_label}", True, (180, 190, 210))
        self.screen.blit(action_txt, (inner_x, inner_y + 32))
        y = card_y + card_h + SECTION_GAP

        prompt = self.font_sm.render("请将执行该动作后的站点拖入下方框内", True, (170, 185, 200))
        self.screen.blit(prompt, (prompt.get_rect(centerx=content_cx, y=y).topleft))
        y += 24

        if self.answer_slot_rect:
            slot_color = (50, 54, 62)
            border_color = (100, 108, 120)
            if self.feedback == "correct":
                border_color = (34, 197, 94)
            elif self.feedback == "wrong":
                border_color = (239, 68, 68)
            pygame.draw.rect(self.screen, slot_color, self.answer_slot_rect, border_radius=12)
            pygame.draw.rect(self.screen, border_color, self.answer_slot_rect, 3, border_radius=12)
            if self.slot_filled is not None:
                self._draw_station_block_in_slot(
                    self.slot_filled,
                    pygame.Rect(
                        self.answer_slot_rect.x + 10,
                        self.answer_slot_rect.y + 10,
                        self.answer_slot_rect.width - 20,
                        self.answer_slot_rect.height - 20,
                    ),
                    border_color,
                )
            else:
                hint = self.font_sm.render("拖到此处", True, (90, 98, 110))
                hr = hint.get_rect(center=self.answer_slot_rect.center)
                self.screen.blit(hint, hr)

        y = self.answer_slot_rect.bottom + 20
        opt_label = self.font_sm.render("候选站点（拖拽其一到上方框内）", True, (140, 150, 170))
        opt_label_r = opt_label.get_rect(centerx=content_cx, y=y)
        self.screen.blit(opt_label, opt_label_r)
        y += 22

        for code, rect in self.candidate_rects.items():
            if self.dragging_code == code:
                continue
            # 学习阶段：正确答案选项用绿色框提示（先提示再作答，不是作对后才提示）
            border_color = (160, 168, 185)
            if phase == PracticePhase.LEARNING and code == q.correct_next_code:
                border_color = (34, 197, 94)
            self._draw_station_block(code, rect, border_color)

        if self.dragging_code is not None and self.drag_pos:
            follow_rect = pygame.Rect(
                self.drag_pos[0] - ITEM_SIZE // 2,
                self.drag_pos[1] - ITEM_SIZE // 2,
                ITEM_SIZE,
                ITEM_SIZE,
            )
            self._draw_station_block(self.dragging_code, follow_rect, (255, 252, 220))

        if self.phase_switch_message and self.phase_switch_timer > 0:
            msg = self.font_md.render(self.phase_switch_message, True, (100, 200, 255))
            mr = msg.get_rect(center=(content_cx, 58))
            self.screen.blit(msg, mr)

        if self.feedback == "correct":
            msg = self.font_md.render("正确！", True, (34, 197, 94))
            mr = msg.get_rect(midright=(self.answer_slot_rect.x - 12, self.answer_slot_rect.centery))
            self.screen.blit(msg, mr)
        elif self.feedback == "wrong":
            msg = self.font_md.render("错误", True, (239, 68, 68))
            mr = msg.get_rect(midright=(self.answer_slot_rect.x - 12, self.answer_slot_rect.centery))
            self.screen.blit(msg, mr)

        esc_hint = self.font_sm.render("ESC 退出", True, (100, 105, 115))
        self.screen.blit(esc_hint, (w - esc_hint.get_width() - MARGIN, h - MARGIN - esc_hint.get_height()))
        self._draw_coordinate_axis(w, h)

    def handle_events(self, events: list) -> bool:
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button != 1:
                    continue
                pos = event.pos
                for code, rect in self.candidate_rects.items():
                    if rect.collidepoint(pos):
                        self.dragging_code = code
                        self.drag_pos = pos
                        break

            elif event.type == pygame.MOUSEMOTION:
                if self.dragging_code is not None:
                    self.drag_pos = event.pos

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button != 1 or self.dragging_code is None:
                    continue
                pos = event.pos
                code = self.dragging_code
                self.dragging_code = None
                self.drag_pos = None

                if self.answer_slot_rect and self.answer_slot_rect.collidepoint(pos):
                    correct, phase_changed = self.manager.submit_answer(code)
                    if phase_changed and self.manager.get_current_phase() == PracticePhase.TEST:
                        self.phase_switch_message = "进入测试阶段！规则不变，作答后会短暂提示是否正确。"
                        self.phase_switch_timer = 2.0
                    self.slot_filled = code
                    if self.manager.is_learning_phase():
                        if correct:
                            self.feedback = "correct"
                            self.feedback_timer = FEEDBACK_CORRECT_DURATION
                            return True
                        self.feedback = "wrong"
                        self.feedback_timer = FEEDBACK_WRONG_DURATION
                    else:
                        self.feedback = "correct" if correct else "wrong"
                        self.feedback_timer = (
                            FEEDBACK_CORRECT_DURATION if correct else FEEDBACK_WRONG_DURATION
                        )
        return False

    def update(self, dt: float) -> bool:
        if self.phase_switch_timer > 0:
            self.phase_switch_timer -= dt
            if self.phase_switch_timer <= 0:
                self.phase_switch_message = None
        if self.feedback and self.feedback_timer > 0:
            self.feedback_timer -= dt
            if self.feedback_timer <= 0:
                if self.feedback == "wrong":
                    if self.manager.is_learning_phase():
                        self.slot_filled = None
                        self.feedback = None
                    else:
                        self.feedback = None
                        self.slot_filled = None
                        return True
                elif self.feedback == "correct":
                    self.feedback = None
                    return True
        return False

    def clear_for_next_question(self) -> None:
        self.slot_filled = None
        self.feedback = None
        self.feedback_timer = 0.0
        self.dragging_code = None
        self.drag_pos = None
