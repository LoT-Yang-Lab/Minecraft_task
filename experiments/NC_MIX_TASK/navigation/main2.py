#!/usr/bin/env python3
"""Navigation6 测试阶段独立入口（地图交通动作版）。

该版本是较新的被试界面：
- 不再使用 Graph9 的“上/下/左/右/环路”动作文案；
- 而是使用交通方式动作：公交、地铁、环线；
- 支持由外部脚本注入预先规划好的 (start, goal) 试次序列与 session 元数据。
- 包含示意性可视化小部件，被试可点击彩色线选择交通工具。

独立运行 `python main2.py` 时（与 crafting 一致）：先输入被试编号 → 选择 maps 下 JSON → 任务说明 → 进入测试。
试次默认从 `assets/trial_sequences/<地图主文件名>.json` 加载；若无该文件则回退为内存随机 9 试次。可用 `--trials` 指定其它试次表路径。
可用 `--participant_id` / `-p` 跳过编号页，`--map` 跳过选图，`--no-guidance` 跳过说明。
批量脚本（如 tests/run_experiment_new.py）会传入 preflight=False，保持原行为。
"""
from __future__ import annotations

import argparse
import datetime
import json
import math as _math
import os
import random
import re
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import pygame

_this_file = Path(__file__).resolve()
_nav6_root = _this_file.parent
_nav6_root_str = str(_nav6_root)
if _nav6_root_str not in sys.path:
    sys.path.insert(0, _nav6_root_str)

_nc_mix_root = str(_this_file.parent.parent)
if _nc_mix_root not in sys.path:
    sys.path.insert(0, _nc_mix_root)

from mix.trial_display import format_session_trial_line

from app.common.station_names import code_to_station_name, draw_station_shape, station_shape_spec
from app.common.trajectory_export import export_navigation_session_to_legacy_xlsx
from app.experiment.main import (
    EXPERIMENT_MAPS,
    _resolve_map_path,
    build_position_encoding,
    execute_action,
    get_available_actions,
)
from app.experiment.game import GameNavigation6
from app.experiment.nav6_trial_list import (
    load_start_goal_pairs_from_sequence_json,
    resolve_trial_sequence_cli_path,
    validate_pairs_against_station_codes,
)
from app.paths import trajectory_raw_dir, trial_sequences_dir
from app.practice.practice.practice_ui import (
    MINI_MAP_STATION_ICON_MAX,
    _load_raw_station_icons,
    _scale_station_icon_dict,
    _scale_surface_uniform_to_max_side,
)
from shared.common.recorder import RLDataRecorder


_KEY_TO_TRANSIT_MODE = {
    pygame.K_q: ("bus", "next"),
    pygame.K_e: ("bus", "prev"),
    pygame.K_a: ("light_rail", "next"),
    pygame.K_d: ("light_rail", "prev"),
    pygame.K_w: ("metro", "next"),
}

# IME 兼容用常量
_TEXT_TO_KEY: Dict[str, int] = {
    "q": pygame.K_q, "e": pygame.K_e, "a": pygame.K_a,
    "d": pygame.K_d, "w": pygame.K_w,
}


class _FakeKeyEvent:
    """IME 兼容用伪按键事件。"""
    def __init__(self, key_code: int):
        self.type = pygame.KEYDOWN
        self.key = key_code

_MAX_ACTIONS_PER_TRIAL = None  # 无步数限制

# ── 交通工具显示名称与颜色（与 main.py 保持一致） ───────────
_MODE_DISPLAY_NAME: Dict[str, str] = {
    "bus": "公交",
    "light_rail": "地铁",
    "metro": "环线",
}

_MODE_COLORS: Dict[str, Tuple[int, int, int]] = {
    "bus": (60, 160, 255),       # 蓝色（默认 / 回退）
    "light_rail": (80, 200, 120),  # 绿色
    "metro": (180, 100, 240),    # 紫色
}

# 深色 = next（向前）、浅色 = prev（向后），同色调
_MODE_DIR_COLORS: Dict[Tuple[str, str], Tuple[int, int, int]] = {
    ("bus", "next"):        (30, 100, 210),    # 深蓝
    ("bus", "prev"):        (130, 195, 255),   # 浅蓝
    ("light_rail", "next"): (30, 140, 60),     # 深绿
    ("light_rail", "prev"): (140, 225, 160),   # 浅绿
    ("metro", "next"):      (130, 55, 200),    # 深紫（单向线，仅 next）
}

# 每种 (mode, direction) 组合在示意图中的固定角度
_MODE_DIR_ANGLES: Dict[Tuple[str, str], float] = {
    ("bus", "next"): -90.0,      # 上
    ("bus", "prev"): 90.0,       # 下
    ("light_rail", "next"): 180.0,  # 左
    ("light_rail", "prev"): 0.0,    # 右
    ("metro", "next"): 45.0,     # 右下
}

# ── 可视化参数 ──────────────────────────────────────────
_VIS_NODE_RADIUS = 40
_VIS_LINE_LEN = 200
_VIS_LINE_WIDTH = 8
_VIS_HIT_WIDTH = 24
_VIS_ANIM_DURATION = 0.3
_VIS_ERROR_FLASH_DURATION = 0.36  # 无效按键时对应线路红色闪烁时长（秒）
_ERROR_RED = (255, 55, 55)


def _point_to_segment_distance(px: float, py: float,
                                x1: float, y1: float,
                                x2: float, y2: float) -> float:
    """点 (px,py) 到线段 (x1,y1)-(x2,y2) 的最短距离。"""
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return _math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return _math.hypot(px - proj_x, py - proj_y)


class _VisGraphWidget:
    """
    示意性可视化小部件（main2 版）。
    在指定矩形区域内，以当前站点为中心绘制可用交通工具的彩色线条。
    线条位置为示意性布局，不反映地图实际结构。
    被试可以点击线条来选择交通工具。
    """

    def __init__(self):
        self.rect = pygame.Rect(0, 0, 300, 300)
        self._edge_hitboxes: List[Tuple[Tuple[str, str], Tuple[float, float], Tuple[float, float]]] = []
        # 动态计算的角度映射（每次 draw 时根据可用动作数均匀分布）
        self._current_angles: Dict[Tuple[str, str], float] = {}
        self._anim_active = False
        self._anim_start_time = 0.0
        self._anim_from_xy: Tuple[float, float] = (0, 0)
        self._anim_to_xy: Tuple[float, float] = (0, 0)
        self._anim_color: Tuple[int, int, int] = (200, 200, 200)
        # 无效按键：对应 (mode, direction) 线路红色闪一下
        self._error_flash_md: Optional[Tuple[str, str]] = None
        self._error_flash_start: float = 0.0

    def set_rect(self, rect: pygame.Rect):
        self.rect = rect

    def start_error_flash(self, mode: str, direction: str) -> None:
        """当前按键/动作不可执行时，让该交通线在示意图上红色闪烁。"""
        if self.is_animating():
            return
        self._error_flash_md = (mode, direction)
        self._error_flash_start = time.perf_counter()

    def start_animation(self, mode: str, direction: str):
        """启动移动动画。"""
        self._error_flash_md = None
        cx = self.rect.centerx
        cy = self.rect.centery
        self._anim_from_xy = (float(cx), float(cy))
        # 使用动态均匀角度（由上次 draw 计算），回退到旧固定角度
        angle_deg = self._current_angles.get((mode, direction),
                                              _MODE_DIR_ANGLES.get((mode, direction), 0.0))
        angle_rad = _math.radians(angle_deg)
        end_x = cx + _VIS_LINE_LEN * _math.cos(angle_rad)
        end_y = cy + _VIS_LINE_LEN * _math.sin(angle_rad)
        self._anim_to_xy = (end_x, end_y)
        self._anim_color = _MODE_DIR_COLORS.get((mode, direction),
                                                  _MODE_COLORS.get(mode, (200, 200, 200)))
        self._anim_active = True
        self._anim_start_time = time.perf_counter()

    def is_animating(self) -> bool:
        if not self._anim_active:
            return False
        elapsed = time.perf_counter() - self._anim_start_time
        if elapsed >= _VIS_ANIM_DURATION:
            self._anim_active = False
            return False
        return True

    def handle_click(self, mouse_pos: Tuple[int, int]) -> Optional[Tuple[str, str]]:
        """
        检测鼠标点击是否命中某条交通工具线。
        返回命中的 (mode, direction)，或 None。
        """
        if self.is_animating():
            return None
        mx, my = mouse_pos
        if not self.rect.collidepoint(mx, my):
            return None
        best_key = None
        best_dist = _VIS_HIT_WIDTH
        for mode_dir, (sx, sy), (ex, ey) in self._edge_hitboxes:
            d = _point_to_segment_distance(float(mx), float(my), sx, sy, ex, ey)
            if d < best_dist:
                best_dist = d
                best_key = mode_dir
        return best_key

    def draw(
        self,
        screen: pygame.Surface,
        font_sm: pygame.font.Font,
        current_code: int,
        available_mode_dirs: List[Tuple[str, str]],
        hover_pos: Optional[Tuple[int, int]] = None,
    ):
        """
        绘制示意性可视化图：当前站点在中心 + 可用交通工具的彩色线。
        available_mode_dirs: 当前站点可用的 [(mode, direction), ...] 列表。
        """
        # 背景框
        pygame.draw.rect(screen, (38, 40, 48), self.rect, border_radius=12)
        pygame.draw.rect(screen, (70, 76, 90), self.rect, 2, border_radius=12)

        cx = self.rect.centerx
        cy = self.rect.centery

        self._edge_hitboxes.clear()

        if self._error_flash_md is not None:
            if time.perf_counter() - self._error_flash_start >= _VIS_ERROR_FLASH_DURATION:
                self._error_flash_md = None

        # 动画中
        if self.is_animating():
            elapsed = time.perf_counter() - self._anim_start_time
            t = min(1.0, elapsed / _VIS_ANIM_DURATION)
            eased = 1.0 - (1.0 - t) ** 2
            anim_x = self._anim_from_xy[0] + (self._anim_to_xy[0] - self._anim_from_xy[0]) * eased
            anim_y = self._anim_from_xy[1] + (self._anim_to_xy[1] - self._anim_from_xy[1]) * eased
            color = self._anim_color
            pygame.draw.line(screen, color,
                             (int(self._anim_from_xy[0]), int(self._anim_from_xy[1])),
                             (int(self._anim_to_xy[0]), int(self._anim_to_xy[1])),
                             _VIS_LINE_WIDTH)
            pygame.draw.circle(screen, (255, 255, 255), (int(anim_x), int(anim_y)), _VIS_NODE_RADIUS)
            pygame.draw.circle(screen, color, (int(anim_x), int(anim_y)), _VIS_NODE_RADIUS, 3)
            # 中心绘制站点形状图标
            draw_station_shape(screen, current_code, cx, cy, size=22)
            _draw_legend(screen, font_sm, self.rect)
            return

        # 正常绘制：当前节点在中心，始终展示全部5种交通线
        all_mode_dirs: List[Tuple[str, str]] = [
            ("bus", "next"), ("bus", "prev"),
            ("light_rail", "next"), ("light_rail", "prev"),
            ("metro", "next"),
        ]
        available_set = set(available_mode_dirs)
        n = len(all_mode_dirs)
        self._current_angles.clear()
        for i, md in enumerate(all_mode_dirs):
            self._current_angles[md] = -90.0 + (360.0 / n) * i

        err_elapsed = 0.0
        flash_this_md: Optional[Tuple[str, str]] = None
        if self._error_flash_md is not None:
            flash_this_md = self._error_flash_md
            err_elapsed = time.perf_counter() - self._error_flash_start

        for mode, direction in all_mode_dirs:
            is_available = (mode, direction) in available_set
            base_color = _MODE_DIR_COLORS.get((mode, direction),
                                               _MODE_COLORS.get(mode, (200, 200, 200)))
            angle_deg = self._current_angles[(mode, direction)]
            angle_rad = _math.radians(angle_deg)
            end_x = cx + _VIS_LINE_LEN * _math.cos(angle_rad)
            end_y = cy + _VIS_LINE_LEN * _math.sin(angle_rad)

            line_width = _VIS_LINE_WIDTH
            color = base_color
            if flash_this_md is not None and (mode, direction) == flash_this_md:
                pulse = max(0.0, _math.sin(err_elapsed * _math.pi * 2 * 7.5)) ** 1.4
                color = tuple(
                    int(base_color[i] * (1.0 - pulse) + _ERROR_RED[i] * pulse)
                    for i in range(3)
                )
                line_width = _VIS_LINE_WIDTH + int(4 + 3 * pulse)

            if is_available:
                if hover_pos and self.rect.collidepoint(hover_pos[0], hover_pos[1]):
                    d = _point_to_segment_distance(float(hover_pos[0]), float(hover_pos[1]),
                                                    float(cx), float(cy), end_x, end_y)
                    if d < _VIS_HIT_WIDTH:
                        line_width = _VIS_LINE_WIDTH + 3
                self._edge_hitboxes.append(((mode, direction), (float(cx), float(cy)), (end_x, end_y)))

            pygame.draw.line(screen, color, (cx, cy), (int(end_x), int(end_y)), line_width)
            pygame.draw.circle(screen, color, (int(end_x), int(end_y)), 12)

        # 中心节点：白色圆底 + 站点形状图标
        pygame.draw.circle(screen, (255, 255, 255), (cx, cy), _VIS_NODE_RADIUS)
        pygame.draw.circle(screen, (100, 140, 220), (cx, cy), _VIS_NODE_RADIUS, 3)
        draw_station_shape(screen, current_code, cx, cy, size=22)

        # 图例
        _draw_legend(screen, font_sm, self.rect)


def _draw_legend(
    screen: pygame.Surface,
    font_sm: pygame.font.Font,
    widget_rect: pygame.Rect,
) -> None:
    """绘制线路图例（仅线路方向，不标注站点形状）。"""
    legend_x = widget_rect.x + 10
    line_h = 20
    # 5 条线路
    total_lines = 5
    legend_y = widget_rect.bottom - total_lines * line_h - 10

    text_color = (180, 180, 195)
    # (mode, direction, label, shortcut_key)
    _entries = [
        ("bus",        "next", "公交（前）", "Q"),
        ("bus",        "prev", "公交（后）", "E"),
        ("light_rail", "next", "地铁（前）", "A"),
        ("light_rail", "prev", "地铁（后）", "D"),
        ("metro",      "next", "环线",       "W"),
    ]
    for mode, direction, label, key in _entries:
        c = _MODE_DIR_COLORS.get((mode, direction),
                                  _MODE_COLORS.get(mode, (200, 200, 200)))
        pygame.draw.line(screen, c, (legend_x, legend_y + 9), (legend_x + 22, legend_y + 9), 5)
        s = font_sm.render(f" {label} [{key}]", True, text_color)
        screen.blit(s, (legend_x + 26, legend_y))
        legend_y += line_h


def _blit_wrapped(
    screen: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    color: Tuple[int, int, int],
    x: int,
    y: int,
    max_width: int,
    line_gap: int = 2,
) -> int:
    if not text.strip():
        return y
    line_h = font.get_linesize() + line_gap
    current = ""
    yy = y
    for ch in text:
        test = current + ch
        w = font.size(test)[0]
        if w <= max_width or not current:
            current = test
        else:
            screen.blit(font.render(current, True, color), (x, yy))
            yy += line_h
            current = ch
    if current:
        screen.blit(font.render(current, True, color), (x, yy))
        yy += line_h
    return yy


def _map_structure_label(map_path: str) -> str:
    """地图 JSON metadata.name，缺省为文件名 stem。"""
    try:
        with open(map_path, encoding="utf-8") as f:
            data = json.load(f)
        meta = data.get("metadata") or {}
        name = (meta.get("name") or Path(map_path).stem).strip()
        return name or Path(map_path).stem
    except Exception:
        return Path(map_path).stem


def _new_game(map_id: str, map_path: str) -> GameNavigation6:
    rec = RLDataRecorder("Navigation6_Main2", task_type="Navigation6_Main2")
    return GameNavigation6(
        rec,
        map_type=map_id,
        target_entropy=0.5,
        enable_experiment=False,
        custom_map_file=map_path,
    )


def _pick_action_idx_by_mode(
    actions: List[Tuple[str, str, Optional[Union[str, int]]]],
    game: GameNavigation6,
    mode: str,
    want_dir: str,
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


def _key_name_for_action(mode: str, action_key: str) -> str:
    is_next = action_key in ("instant_transit_next", "instant_subway_next")
    if mode == "bus":
        return "Q" if is_next else "E"
    if mode == "light_rail":
        return "A" if is_next else "D"
    # 环线（metro）单向，按键固定 W
    return "W"


def _clean_option_label(label: str) -> str:
    out = re.sub(r"（[^）]*）", "", label)
    out = re.sub(r"\([^)]*\)", "", out)
    return " ".join(out.split())


def _draw_station_icon(
    screen: pygame.Surface,
    station_icons: Dict[int, pygame.Surface],
    code: int,
    x: int,
    y: int,
    max_side: int = 64,
) -> None:
    icon = station_icons.get(code)
    if icon is not None:
        draw_ic = _scale_surface_uniform_to_max_side(icon, max_side)
        rect = draw_ic.get_rect(topleft=(x, y))
        screen.blit(draw_ic, rect)
        return
    # 回退占位：无素材时画圆点
    pygame.draw.circle(screen, (210, 220, 240), (x + max_side // 2, y + max_side // 2), max_side // 3)


def _build_neighbors(
    game: GameNavigation6,
    all_codes: List[int],
    code_to_cell: Dict[int, Tuple[int, int]],
    cell_to_code: Dict[Tuple[int, int], int],
) -> Dict[int, Set[int]]:
    neighbors: Dict[int, Set[int]] = {c: set() for c in all_codes}
    original_pos = (game.player_x, game.player_y)
    for c in all_codes:
        sx, sy = code_to_cell[c]
        game.player_x, game.player_y = sx, sy
        actions = get_available_actions(game, include_bidirectional_for_surface=True)
        for action in actions:
            ox, oy = game.player_x, game.player_y
            ok = execute_action(game, action)
            if ok:
                nc = cell_to_code.get((game.player_x, game.player_y), 0)
                if nc > 0 and nc != c:
                    neighbors[c].add(nc)
            game.player_x, game.player_y = ox, oy
    game.player_x, game.player_y = original_pos
    return neighbors


def _shortest_distance(neighbors: Dict[int, Set[int]], start: int, goal: int) -> int:
    if start == goal:
        return 0
    q = deque([(start, 0)])
    visited = {start}
    while q:
        cur, d = q.popleft()
        for nxt in neighbors.get(cur, set()):
            if nxt == goal:
                return d + 1
            if nxt not in visited:
                visited.add(nxt)
                q.append((nxt, d + 1))
    return -1


def _generate_test_trials(
    all_codes: List[int],
    neighbors: Dict[int, Set[int]],
    trial_count: int = 9,
    min_distance: int = 2,
) -> List[Tuple[int, int]]:
    pairs: List[Tuple[int, int]] = []
    for s in all_codes:
        for g in all_codes:
            if s == g:
                continue
            d = _shortest_distance(neighbors, s, g)
            if d >= min_distance:
                pairs.append((s, g))
    if not pairs:
        for s in all_codes:
            for g in all_codes:
                if s != g:
                    pairs.append((s, g))
    random.shuffle(pairs)
    if not pairs:
        return []
    out: List[Tuple[int, int]] = []
    while len(out) < trial_count:
        out.append(pairs[len(out) % len(pairs)])
    return out


def _get_available_mode_dirs(
    game: GameNavigation6,
) -> List[Tuple[str, str]]:
    """返回当前位置可用的 (mode, direction) 对列表。"""
    actions = get_available_actions(game, include_bidirectional_for_surface=True)
    modes = list(getattr(game, "transit_modes", []) or [])
    result: List[Tuple[str, str]] = []
    seen: Set[Tuple[str, str]] = set()
    for _label, akey, extra in actions:
        if extra is None:
            continue
        li = int(extra) if not isinstance(extra, int) else extra
        if li < 0 or li >= len(modes):
            continue
        mode = modes[li]
        direction = "next"
        if akey in ("instant_transit_prev", "instant_subway_prev"):
            direction = "prev"
        key = (mode, direction)
        if key not in seen:
            seen.add(key)
            result.append(key)
    return result


def main(
    test_trials_override: Optional[List[Tuple[int, int]]] = None,
    session_metadata: Optional[Dict[str, Any]] = None,
    experiment_output_dir: Optional[str] = None,
    participant_id: Optional[str] = None,
    *,
    preflight: bool = True,
    map_path_cli: Optional[str] = None,
    skip_guidance: bool = False,
    trial_sequence_path_cli: Optional[str] = None,
    external_screen: Optional[pygame.Surface] = None,
    external_clock: Optional[pygame.time.Clock] = None,
    manage_pygame: bool = True,
    auto_exit_on_finish: bool = False,
    display_trial_progress: Optional[Tuple[int, int]] = None,
    return_run_state: bool = False,
) -> Optional[object]:
    if manage_pygame:
        pygame.init()
        pygame.key.stop_text_input()
    W, H = 800, 900
    if external_screen is None:
        screen = pygame.display.set_mode((W, H))
    else:
        screen = external_screen
        W, H = screen.get_size()
    pygame.display.set_caption("Navigation6")

    font_lg = pygame.font.SysFont("SimHei", 26)
    font_md = pygame.font.SysFont("SimHei", 20)
    font_sm = pygame.font.SysFont("SimHei", 16)
    pad_x = 24
    text_max_w = W - pad_x * 2
    clock = external_clock or pygame.time.Clock()
    station_icons_raw = _load_raw_station_icons()
    station_icons_mini = _scale_station_icon_dict(station_icons_raw, max(56, MINI_MAP_STATION_ICON_MAX))

    from app.guidance_nav6 import run_navigation6_guidance_screen
    from app.map_select_nav6 import resolve_map_cli_path, run_map_selection
    from app.participant_id_nav6 import run_participant_id_screen

    if preflight:
        if participant_id and str(participant_id).strip():
            participant_id = str(participant_id).strip()
        else:
            pid = run_participant_id_screen(screen, clock)
            if pid is None:
                pygame.quit()
                return None
            participant_id = pid

        if map_path_cli:
            try:
                map_path = resolve_map_cli_path(map_path_cli)
            except Exception as e:
                print(f"地图路径无效: {e}")
                pygame.quit()
                return None
        else:
            map_path = run_map_selection(screen, clock)
            if map_path is None:
                pygame.quit()
                return None

        if not os.path.isfile(map_path):
            print(f"地图文件不存在: {map_path}")
            pygame.quit()
            return None

        map_structure = _map_structure_label(map_path)
        map_id = Path(map_path).stem

        if not skip_guidance:
            if not run_navigation6_guidance_screen(screen, clock, map_label=map_structure):
                pygame.quit()
                return None
    else:
        participant_id = (participant_id or "Navigation6_User").strip() or "Navigation6_User"
        if map_path_cli:
            try:
                map_path = resolve_map_cli_path(map_path_cli)
            except Exception as e:
                print(f"地图路径无效: {e}")
                pygame.quit()
                return None
            map_structure = _map_structure_label(map_path)
            map_id = Path(map_path).stem
        else:
            if not EXPERIMENT_MAPS:
                print("未配置可用地图（EXPERIMENT_MAPS 为空）。")
                pygame.quit()
                return None
            map_file = EXPERIMENT_MAPS[0][1]
            map_path = _resolve_map_path(map_file)
            map_id = os.path.splitext(os.path.basename(map_path))[0]
            map_structure = EXPERIMENT_MAPS[0][0]

        if not os.path.isfile(map_path):
            print(f"地图文件不存在: {map_path}")
            pygame.quit()
            return None

    pygame.display.set_caption("Navigation6 — 点击线条或按键选择交通工具")

    # 数据记录机制沿用 main2 风格
    data_root = trajectory_raw_dir()
    os.makedirs(data_root, exist_ok=True)
    session_start = datetime.datetime.now()
    session_log: List[Dict] = []
    trial_summaries: List[Dict[str, Any]] = []

    def log_step(phase, trial_id, step, from_node, action, to_node, is_valid, extra=None):
        entry = {
            "phase": phase,
            "trial_id": trial_id,
            "step": step,
            "timestamp": time.time(),
            "from_node": from_node,
            "action": action,
            "to_node": to_node,
            "is_valid": is_valid,
        }
        if extra:
            entry.update(extra)
        session_log.append(entry)

    def save_session():
        return export_navigation_session_to_legacy_xlsx(
            data_root=data_root,
            session_start=session_start,
            session_end=datetime.datetime.now(),
            map_id=map_id,
            map_structure=map_structure,
            steps=session_log,
            test_trials=test_trials,
            trial_summaries=trial_summaries,
            session_metadata=session_metadata,
            code_to_cell=code_to_cell,
            participant_id=participant_id,
            task_type="Navigation6_Test",
            experiment_output_dir=experiment_output_dir,
        )

    PHASE_TEST = "test"
    PHASE_FINISHED = "finished"
    phase = PHASE_TEST

    game = _new_game(map_id, map_path)
    cell_to_code, code_to_cell, _ = build_position_encoding(game)
    all_codes = sorted(code_to_cell.keys())
    if len(all_codes) < 2:
        print("可用站点不足，无法开始测试。")
        pygame.quit()
        return None

    neighbors = _build_neighbors(game, all_codes, code_to_cell, cell_to_code)
    if test_trials_override:
        test_trials = [(int(s), int(g)) for s, g in test_trials_override]
    else:
        seq_path: Optional[str] = None
        cli_ts = (trial_sequence_path_cli or "").strip()
        if cli_ts:
            try:
                seq_path = resolve_trial_sequence_cli_path(cli_ts)
            except FileNotFoundError as e:
                print(f"[FATAL] {e}")
                pygame.quit()
                return None
        else:
            default_seq = os.path.join(trial_sequences_dir(), f"{map_id}.json")
            if os.path.isfile(default_seq):
                seq_path = default_seq
        if seq_path:
            try:
                test_trials = load_start_goal_pairs_from_sequence_json(seq_path)
                validate_pairs_against_station_codes(
                    test_trials, set(all_codes), path_hint=seq_path
                )
                print(f"[INFO] 已加载试次表: {seq_path}（共 {len(test_trials)} 个试次）")
            except (ValueError, OSError, json.JSONDecodeError) as e:
                print(f"[FATAL] 试次表无效: {e}")
                pygame.quit()
                return None
        else:
            test_trials = _generate_test_trials(
                all_codes, neighbors, trial_count=9, min_distance=2
            )
            print(
                f"[WARN] 未找到 assets/trial_sequences/{map_id}.json，"
                f"使用内存随机生成的 {len(test_trials)} 个试次；请用脚本生成试次表以对齐正式设计。"
            )
    if not test_trials:
        print("无法生成测试试次。")
        pygame.quit()
        return None

    mix_ui: Optional[Dict[str, Any]] = None
    if isinstance(session_metadata, dict):
        mix_ui = session_metadata.get("mix_ui")

    test_trial_idx = 0
    test_step = 0
    test_trial_steps: List[int] = []
    test_trial_outcomes: List[str] = []
    trial_start_wall_time = time.time()
    trial_first_move_latency_ms: Optional[int] = None
    trial_start_code: int
    s, g = test_trials[0]
    trial_start_code = s
    game.player_x, game.player_y = code_to_cell[s]
    test_goal_node = g

    def _start_trial(start_code: int, goal_code: int) -> None:
        nonlocal test_step, test_goal_node, trial_start_wall_time, trial_first_move_latency_ms, trial_start_code
        trial_start_code = start_code
        test_step = 0
        trial_first_move_latency_ms = None
        trial_start_wall_time = time.time()
        game.player_x, game.player_y = code_to_cell[start_code]
        test_goal_node = goal_code

    def _finalize_current_trial(reached_goal: bool, end_code: int) -> None:
        nonlocal phase, test_trial_idx
        elapsed_ms = int(round((time.time() - trial_start_wall_time) * 1000))
        optimal_distance = _shortest_distance(neighbors, trial_start_code, test_goal_node)
        outcome = "reached_goal" if reached_goal else "action_cap"
        trial_summaries.append(
            {
                "trial_id": test_trial_idx + 1,
                "start": trial_start_code,
                "goal": test_goal_node,
                "path_length": test_step,
                "optimal_distance": optimal_distance,
                "latency_to_first_move_ms": trial_first_move_latency_ms,
                "total_response_time_ms": elapsed_ms,
                "goal_reached": reached_goal,
                "outcome": outcome,
                "final_node": end_code,
                "path_efficiency": (optimal_distance / test_step) if reached_goal and test_step > 0 and optimal_distance > 0 else 0,
            }
        )
        test_trial_steps.append(test_step)
        test_trial_outcomes.append(outcome)
        test_trial_idx += 1
        if test_trial_idx >= len(test_trials):
            phase = PHASE_FINISHED
            return
        next_start, next_goal = test_trials[test_trial_idx]
        _start_trial(next_start, next_goal)

    # ── 可视化小部件 ────────────────────────────────────
    vis_widget = _VisGraphWidget()

    running = True
    interrupted = False
    while running:
        hover_pos = pygame.mouse.get_pos()
        events = pygame.event.get()
        for ev in events:
            if ev.type == pygame.QUIT:
                if phase != PHASE_FINISHED:
                    interrupted = True
                running = False

        key_events = [ev for ev in events if ev.type == pygame.KEYDOWN]
        text_events = [ev for ev in events if ev.type == pygame.TEXTINPUT]
        click_events = [ev for ev in events if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1]

        # IME 兼容：将 TEXTINPUT 转换为虚拟按键
        mapped_keys = {ev.key for ev in key_events}
        for tev in text_events:
            ch = tev.text.lower()
            if ch in _TEXT_TO_KEY and _TEXT_TO_KEY[ch] not in mapped_keys:
                key_events.append(_FakeKeyEvent(_TEXT_TO_KEY[ch]))

        # 处理鼠标点击（选择交通工具线）
        if not vis_widget.is_animating() and phase == PHASE_TEST:
            for cev in click_events:
                clicked = vis_widget.handle_click(cev.pos)
                if clicked is not None:
                    mode, want_dir = clicked
                    actions = get_available_actions(game, include_bidirectional_for_surface=True)
                    chosen_idx = _pick_action_idx_by_mode(actions, game, mode, want_dir)
                    current_code = cell_to_code.get((game.player_x, game.player_y), 0)
                    if chosen_idx is None:
                        vis_widget.start_error_flash(mode, want_dir)
                        break
                    action = actions[chosen_idx]
                    ok = execute_action(game, action)
                    if not ok:
                        vis_widget.start_error_flash(mode, want_dir)
                        break
                    new_code = cell_to_code.get((game.player_x, game.player_y), 0)
                    if trial_first_move_latency_ms is None:
                        trial_first_move_latency_ms = int(round((time.time() - trial_start_wall_time) * 1000))
                    test_step += 1
                    start_code, _goal = test_trials[test_trial_idx]
                    vis_widget.start_animation(mode, want_dir)
                    log_step(
                        PHASE_TEST, test_trial_idx + 1, test_step,
                        current_code, action[0], new_code, True,
                        {
                            "goal_node": test_goal_node,
                            "optimal_distance": _shortest_distance(neighbors, start_code, test_goal_node),
                            "action_key": action[1],
                            "action_extra": action[2],
                            "input_source": "click",
                            "reaction_time_ms": trial_first_move_latency_ms if test_step == 1 else None,
                            "elapsed_trial_time_ms": int(round((time.time() - trial_start_wall_time) * 1000)),
                            "max_actions": _MAX_ACTIONS_PER_TRIAL,
                        },
                    )
                    if new_code == test_goal_node:
                        _finalize_current_trial(reached_goal=True, end_code=new_code)
                    break

        for ev in key_events:
            if ev.type != pygame.KEYDOWN:
                continue
            if ev.key == pygame.K_ESCAPE:
                if phase != PHASE_FINISHED:
                    interrupted = True
                running = False
                break

            if phase != PHASE_TEST:
                continue
            mapping = _KEY_TO_TRANSIT_MODE.get(ev.key)
            if mapping is None:
                continue
            mode, want_dir = mapping
            actions = get_available_actions(game, include_bidirectional_for_surface=True)
            chosen_idx = _pick_action_idx_by_mode(actions, game, mode, want_dir)
            current_code = cell_to_code.get((game.player_x, game.player_y), 0)
            if chosen_idx is None:
                vis_widget.start_error_flash(mode, want_dir)
                log_step(
                    PHASE_TEST,
                    test_trial_idx + 1,
                    test_step,
                    current_code,
                    f"{mode}_{want_dir}",
                    None,
                    False,
                    {"goal_node": test_goal_node},
                )
                continue

            action = actions[chosen_idx]
            ok = execute_action(game, action)
            if not ok:
                vis_widget.start_error_flash(mode, want_dir)
                log_step(
                    PHASE_TEST,
                    test_trial_idx + 1,
                    test_step,
                    current_code,
                    action[0],
                    None,
                    False,
                    {"goal_node": test_goal_node},
                )
                continue

            new_code = cell_to_code.get((game.player_x, game.player_y), 0)
            if trial_first_move_latency_ms is None:
                trial_first_move_latency_ms = int(round((time.time() - trial_start_wall_time) * 1000))
            test_step += 1
            start_code, _goal = test_trials[test_trial_idx]
            vis_widget.start_animation(mode, want_dir)
            log_step(
                PHASE_TEST,
                test_trial_idx + 1,
                test_step,
                current_code,
                action[0],
                new_code,
                True,
                {
                    "goal_node": test_goal_node,
                    "optimal_distance": _shortest_distance(neighbors, start_code, test_goal_node),
                    "action_key": action[1],
                    "action_extra": action[2],
                    "input_source": "key",
                    "reaction_time_ms": trial_first_move_latency_ms if test_step == 1 else None,
                    "elapsed_trial_time_ms": int(round((time.time() - trial_start_wall_time) * 1000)),
                    "max_actions": _MAX_ACTIONS_PER_TRIAL,
                },
            )
            if new_code == test_goal_node:
                _finalize_current_trial(reached_goal=True, end_code=new_code)

        screen.fill((28, 28, 32))
        y = 16
        if phase == PHASE_FINISHED and auto_exit_on_finish:
            running = False
            continue
        if phase == PHASE_TEST:
            current_code = cell_to_code.get((game.player_x, game.player_y), 0)
            if mix_ui:
                sn_meta = (session_metadata or {}).get("session", "?")
                title_mix = str(mix_ui.get("title", "NC Mix · 导航"))
                y = _blit_wrapped(screen, font_lg, title_mix, (236, 242, 255), pad_x, y, text_max_w)
                y += 8
                trial_line = format_session_trial_line(
                    session_label=f"Session {sn_meta}",
                    trial_n=(
                        display_trial_progress[0]
                        if display_trial_progress is not None
                        else test_trial_idx + 1
                    ),
                    trial_n_total=(
                        display_trial_progress[1]
                        if display_trial_progress is not None
                        else len(test_trials)
                    ),
                    domain_zh="导航",
                )
                y = _blit_wrapped(screen, font_md, trial_line, (190, 210, 230), pad_x, y, text_max_w)
                y += 6
                meta2 = str(mix_ui.get("meta_line2", "Esc 退出并保存当前阶段"))
                y = _blit_wrapped(screen, font_sm, meta2, (130, 142, 168), pad_x, y, text_max_w)
                y += 12
            else:
                y = _blit_wrapped(screen, font_lg, "测试阶段 — 导航任务", (255, 220, 200), pad_x, y, text_max_w)
                y += 8
                y = _blit_wrapped(
                    screen,
                    font_md,
                    format_session_trial_line(
                        session_label=None,
                        trial_n=(
                            display_trial_progress[0]
                            if display_trial_progress is not None
                            else test_trial_idx + 1
                        ),
                        trial_n_total=(
                            display_trial_progress[1]
                            if display_trial_progress is not None
                            else len(test_trials)
                        ),
                        domain_zh="导航",
                    ),
                    (190, 210, 230),
                    pad_x,
                    y,
                    text_max_w,
                )
                y += 4
            cur_text = "当前位置："
            cur_surf = font_md.render(cur_text, True, (180, 230, 180))
            screen.blit(cur_surf, (pad_x, y))
            cur_icon_x = min(pad_x + cur_surf.get_width() + 10, W - 70)
            draw_station_shape(screen, current_code, cur_icon_x + 16, y + font_md.get_linesize() // 2, size=12)
            y += max(font_md.get_linesize() + 2, 40) + 2

            goal_text = "目标位置："
            goal_surf = font_md.render(goal_text, True, (255, 200, 160))
            screen.blit(goal_surf, (pad_x, y))
            goal_icon_x = min(pad_x + goal_surf.get_width() + 10, W - 70)
            draw_station_shape(screen, test_goal_node, goal_icon_x + 16, y + font_md.get_linesize() // 2, size=12)
            y += max(font_md.get_linesize() + 2, 40) + 2
            y = _blit_wrapped(
                screen,
                font_sm,
                f"本试次已用步数：{test_step}",
                (180, 180, 200),
                pad_x,
                y,
                text_max_w,
            )
            y += 10
            y = _blit_wrapped(
                screen,
                font_sm,
                "点击彩色线路或按快捷键选择下一步交通工具。",
                (190, 190, 210),
                pad_x,
                y,
                text_max_w,
            )

            # 可视化图
            available_mode_dirs = _get_available_mode_dirs(game)
            vis_top = y + 6
            vis_size = min(W - pad_x * 2, H - vis_top - 30)
            vis_rect = pygame.Rect((W - vis_size) // 2, vis_top, vis_size, vis_size)
            vis_widget.set_rect(vis_rect)
            vis_widget.draw(screen, font_sm, current_code, available_mode_dirs, hover_pos=hover_pos)

            _blit_wrapped(
                screen,
                font_sm,
                "Esc 退出并保存当前阶段" if mix_ui else "ESC：退出（数据会保存）",
                (140, 140, 160),
                pad_x,
                H - 24,
                text_max_w,
            )
        else:
            y = 60
            y = _blit_wrapped(screen, font_lg, "实验结束", (220, 255, 220), pad_x, y, text_max_w)
            y += 12
            y = _blit_wrapped(
                screen,
                font_md,
                f"已完成 {len(test_trials)} 个导航试次。",
                (200, 220, 210),
                pad_x,
                y,
                text_max_w,
            )
            y += 8
            for i, steps in enumerate(test_trial_steps):
                s0, g0 = test_trials[i]
                opt = _shortest_distance(neighbors, s0, g0)
                outcome = test_trial_outcomes[i] if i < len(test_trial_outcomes) else "unknown"
                y = _blit_wrapped(
                    screen,
                    font_sm,
                    f"  试次 {i + 1}：步数 {steps}（最短 {opt}，结果 {outcome}）",
                    (190, 200, 210),
                    pad_x,
                    y,
                    text_max_w,
                )
                y += 2
            y += 12
            _blit_wrapped(screen, font_sm, "按 ESC 退出（数据已保存）。", (170, 180, 190), pad_x, y, text_max_w)

        pygame.display.flip()
        clock.tick(60)

    out = save_session()
    print(f"Main2 数据已保存（legacy xlsx）: {out}")
    if manage_pygame:
        pygame.quit()
    if return_run_state:
        return {"output": out, "interrupted": bool(interrupted)}
    return out


if __name__ == "__main__":
    _ap = argparse.ArgumentParser(description="Navigation6 地图交通测试（含被试编号 / 选图 / 指导语）")
    _ap.add_argument(
        "--participant_id",
        "-p",
        default=None,
        help="指定被试编号则跳过编号输入页",
    )
    _ap.add_argument(
        "--map",
        default=None,
        help="指定地图 JSON 则跳过选图（相对 assets/maps 或 maps 目录的文件名，或绝对路径）",
    )
    _ap.add_argument("--no-guidance", action="store_true", help="跳过任务说明页")
    _ap.add_argument(
        "--trials",
        default=None,
        help="试次表 JSON（默认同名 map 的 assets/trial_sequences/<stem>.json）",
    )
    _args = _ap.parse_args()
    main(
        participant_id=_args.participant_id,
        map_path_cli=_args.map,
        skip_guidance=_args.no_guidance,
        preflight=True,
        trial_sequence_path_cli=_args.trials,
    )
