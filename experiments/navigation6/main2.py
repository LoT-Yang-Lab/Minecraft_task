#!/usr/bin/env python3
"""Navigation6 测试阶段独立入口（地图交通动作版）。

该版本是较新的被试界面：
- 不再使用 Graph9 的“上/下/左/右/环路”动作文案；
- 而是使用交通方式动作：公交、地铁、环线；
- 支持由外部脚本注入预先规划好的 (start, goal) 试次序列与 session 元数据。
- 包含示意性可视化小部件，被试可点击彩色线选择交通工具。
"""
from __future__ import annotations

import datetime
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

# .../Minecraft8.0/experiments/navigation6/main2.py -> .../Minecraft8.0
_this_file = Path(__file__).resolve()
_project_root = _this_file.parents[2]
_project_root_str = str(_project_root)
if _project_root_str not in sys.path:
    sys.path.insert(0, _project_root_str)

from experiments.navigation6.app.common.station_names import code_to_station_name
from experiments.navigation6.app.common.trajectory_export import export_navigation_session_to_legacy_xlsx
from experiments.navigation6.app.experiment.main import (
    EXPERIMENT_MAPS,
    _resolve_map_path,
    build_position_encoding,
    execute_action,
    get_available_actions,
)
from experiments.navigation6.app.experiment.game import GameNavigation6
from experiments.navigation6.app.paths import trajectory_raw_dir
from experiments.navigation6.app.practice.practice.practice_ui import (
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

_MAX_ACTIONS_PER_TRIAL = 10

# ── 交通工具显示名称与颜色（与 main.py 保持一致） ───────────
_MODE_DISPLAY_NAME: Dict[str, str] = {
    "bus": "公交",
    "light_rail": "地铁",
    "metro": "环线",
}

_MODE_COLORS: Dict[str, Tuple[int, int, int]] = {
    "bus": (60, 160, 255),       # 蓝色
    "light_rail": (80, 200, 120),  # 绿色
    "metro": (180, 100, 240),    # 紫色
}

# 每种 (mode, direction) 组合在示意图中的固定角度
_MODE_DIR_ANGLES: Dict[Tuple[str, str], float] = {
    ("bus", "next"): -90.0,      # 上
    ("bus", "prev"): 90.0,       # 下
    ("light_rail", "next"): 180.0,  # 左
    ("light_rail", "prev"): 0.0,    # 右
    ("metro", "next"): 45.0,     # 右下
}

# 每种 (mode, direction) 的显示标签与按键
_MODE_DIR_LABEL: Dict[Tuple[str, str], str] = {
    ("bus", "next"): "公交(前)",
    ("bus", "prev"): "公交(后)",
    ("light_rail", "next"): "地铁(前)",
    ("light_rail", "prev"): "地铁(后)",
    ("metro", "next"): "环线",
}

_MODE_DIR_KEY: Dict[Tuple[str, str], str] = {
    ("bus", "next"): "Q",
    ("bus", "prev"): "E",
    ("light_rail", "next"): "A",
    ("light_rail", "prev"): "D",
    ("metro", "next"): "W",
}

# ── 可视化参数 ──────────────────────────────────────────
_VIS_NODE_RADIUS = 28
_VIS_LINE_LEN = 100
_VIS_LINE_WIDTH = 6
_VIS_HIT_WIDTH = 18
_VIS_ANIM_DURATION = 0.3


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
        self._anim_active = False
        self._anim_start_time = 0.0
        self._anim_from_xy: Tuple[float, float] = (0, 0)
        self._anim_to_xy: Tuple[float, float] = (0, 0)
        self._anim_color: Tuple[int, int, int] = (200, 200, 200)

    def set_rect(self, rect: pygame.Rect):
        self.rect = rect

    def start_animation(self, mode: str, direction: str):
        """启动移动动画。"""
        cx = self.rect.centerx
        cy = self.rect.centery
        self._anim_from_xy = (float(cx), float(cy))
        angle_deg = _MODE_DIR_ANGLES.get((mode, direction), 0.0)
        angle_rad = _math.radians(angle_deg)
        end_x = cx + _VIS_LINE_LEN * _math.cos(angle_rad)
        end_y = cy + _VIS_LINE_LEN * _math.sin(angle_rad)
        self._anim_to_xy = (end_x, end_y)
        self._anim_color = _MODE_COLORS.get(mode, (200, 200, 200))
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
            label = code_to_station_name(current_code)
            txt = font_sm.render(label, True, (40, 40, 50))
            txt_r = txt.get_rect(center=(int(anim_x), int(anim_y)))
            screen.blit(txt, txt_r)
            return

        # 正常绘制：当前节点在中心，可用交通线从中心辐射
        for mode, direction in available_mode_dirs:
            color = _MODE_COLORS.get(mode, (200, 200, 200))
            angle_deg = _MODE_DIR_ANGLES.get((mode, direction), 0.0)
            angle_rad = _math.radians(angle_deg)
            end_x = cx + _VIS_LINE_LEN * _math.cos(angle_rad)
            end_y = cy + _VIS_LINE_LEN * _math.sin(angle_rad)

            line_width = _VIS_LINE_WIDTH
            if hover_pos and self.rect.collidepoint(hover_pos[0], hover_pos[1]):
                d = _point_to_segment_distance(float(hover_pos[0]), float(hover_pos[1]),
                                                float(cx), float(cy), end_x, end_y)
                if d < _VIS_HIT_WIDTH:
                    line_width = _VIS_LINE_WIDTH + 3

            pygame.draw.line(screen, color, (cx, cy), (int(end_x), int(end_y)), line_width)
            self._edge_hitboxes.append(((mode, direction), (float(cx), float(cy)), (end_x, end_y)))

            pygame.draw.circle(screen, color, (int(end_x), int(end_y)), 8)

            key = _MODE_DIR_KEY.get((mode, direction), "?")
            display_label = _MODE_DIR_LABEL.get((mode, direction), f"{mode}_{direction}")
            label_x = cx + (_VIS_LINE_LEN + 20) * _math.cos(angle_rad)
            label_y = cy + (_VIS_LINE_LEN + 20) * _math.sin(angle_rad)
            act_label = f"[{key}] {display_label}"
            act_surf = font_sm.render(act_label, True, color)
            act_rect = act_surf.get_rect(center=(int(label_x), int(label_y)))
            screen.blit(act_surf, act_rect)

        # 中心节点
        pygame.draw.circle(screen, (255, 255, 255), (cx, cy), _VIS_NODE_RADIUS)
        pygame.draw.circle(screen, (100, 140, 220), (cx, cy), _VIS_NODE_RADIUS, 3)
        node_label = code_to_station_name(current_code)
        node_surf = font_sm.render(node_label, True, (40, 40, 50))
        node_rect = node_surf.get_rect(center=(cx, cy))
        screen.blit(node_surf, node_rect)

        # 图例（3 种交通工具）
        legend_x = self.rect.x + 8
        legend_y = self.rect.bottom - len(_MODE_COLORS) * 16 - 8
        for mode, mode_color in _MODE_COLORS.items():
            display_name = _MODE_DISPLAY_NAME.get(mode, mode)
            pygame.draw.line(screen, mode_color, (legend_x, legend_y + 6), (legend_x + 16, legend_y + 6), 3)
            legend_surf = font_sm.render(f" {display_name}", True, (180, 180, 195))
            screen.blit(legend_surf, (legend_x + 18, legend_y - 2))
            legend_y += 16


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
    participant_id: str = "Navigation6_User",
) -> Optional[str]:
    pygame.init()
    pygame.key.stop_text_input()
    W, H = 800, 780
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Navigation6 — 点击线条或按键选择交通工具")

    font_lg = pygame.font.SysFont("SimHei", 26)
    font_md = pygame.font.SysFont("SimHei", 20)
    font_sm = pygame.font.SysFont("SimHei", 16)
    pad_x = 24
    text_max_w = W - pad_x * 2
    clock = pygame.time.Clock()
    station_icons_raw = _load_raw_station_icons()
    station_icons_mini = _scale_station_icon_dict(station_icons_raw, max(56, MINI_MAP_STATION_ICON_MAX))

    if not EXPERIMENT_MAPS:
        print("未配置可用地图（EXPERIMENT_MAPS 为空）。")
        pygame.quit()
        return None
    map_file = EXPERIMENT_MAPS[0][1]
    map_path = _resolve_map_path(map_file)
    map_id = os.path.splitext(os.path.basename(map_path))[0]
    map_structure = EXPERIMENT_MAPS[0][0]
    if not os.path.exists(map_path):
        print(f"地图文件不存在: {map_path}")
        pygame.quit()
        return None

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
        test_trials = _generate_test_trials(all_codes, neighbors, trial_count=9, min_distance=2)
    if not test_trials:
        print("无法生成测试试次。")
        pygame.quit()
        return None

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
    while running:
        hover_pos = pygame.mouse.get_pos()
        events = pygame.event.get()
        for ev in events:
            if ev.type == pygame.QUIT:
                running = False

        key_events = [ev for ev in events if ev.type == pygame.KEYDOWN]
        text_events = [ev for ev in events if ev.type == pygame.TEXTINPUT]
        click_events = [ev for ev in events if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1]

        # IME 兼容：将 TEXTINPUT 转换为虚拟按键
        _TEXT_TO_KEY = {"q": pygame.K_q, "e": pygame.K_e, "a": pygame.K_a,
                        "d": pygame.K_d, "w": pygame.K_w}
        mapped_keys = {ev.key for ev in key_events}
        for tev in text_events:
            ch = tev.text.lower()
            if ch in _TEXT_TO_KEY and _TEXT_TO_KEY[ch] not in mapped_keys:
                class _FakeKeyEvent:
                    def __init__(self, key_code):
                        self.type = pygame.KEYDOWN
                        self.key = key_code
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
                    if chosen_idx is not None:
                        action = actions[chosen_idx]
                        ok = execute_action(game, action)
                        if ok:
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
                            elif test_step >= _MAX_ACTIONS_PER_TRIAL:
                                log_step(
                                    PHASE_TEST, test_trial_idx + 1, test_step,
                                    new_code, "trial_cap_reached", new_code, True,
                                    {
                                        "goal_node": test_goal_node,
                                        "max_actions": _MAX_ACTIONS_PER_TRIAL,
                                        "latency_to_first_move_ms": trial_first_move_latency_ms,
                                        "total_response_time_ms": int(round((time.time() - trial_start_wall_time) * 1000)),
                                    },
                                )
                                _finalize_current_trial(reached_goal=False, end_code=new_code)
                    break

        for ev in key_events:
            if ev.type != pygame.KEYDOWN:
                continue
            if ev.key == pygame.K_ESCAPE:
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
            elif test_step >= _MAX_ACTIONS_PER_TRIAL:
                log_step(
                    PHASE_TEST,
                    test_trial_idx + 1,
                    test_step,
                    new_code,
                    "trial_cap_reached",
                    new_code,
                    True,
                    {
                        "goal_node": test_goal_node,
                        "max_actions": _MAX_ACTIONS_PER_TRIAL,
                        "latency_to_first_move_ms": trial_first_move_latency_ms,
                        "total_response_time_ms": int(round((time.time() - trial_start_wall_time) * 1000)),
                    },
                )
                _finalize_current_trial(reached_goal=False, end_code=new_code)

        screen.fill((28, 28, 32))
        y = 16
        if phase == PHASE_TEST:
            current_code = cell_to_code.get((game.player_x, game.player_y), 0)
            y = _blit_wrapped(screen, font_lg, "测试阶段 — 导航任务", (255, 220, 200), pad_x, y, text_max_w)
            y += 8
            y = _blit_wrapped(
                screen,
                font_md,
                f"试次：{test_trial_idx + 1} / {len(test_trials)}",
                (190, 210, 230),
                pad_x,
                y,
                text_max_w,
            )
            y += 4
            cur_text = f"当前位置：{code_to_station_name(current_code)}（编码 {current_code}）"
            cur_surf = font_md.render(cur_text, True, (180, 230, 180))
            screen.blit(cur_surf, (pad_x, y))
            cur_icon_x = min(pad_x + cur_surf.get_width() + 10, W - 70)
            _draw_station_icon(screen, station_icons_mini, current_code, cur_icon_x, y - 6, max_side=40)
            y += max(font_md.get_linesize() + 2, 40) + 2

            goal_text = f"目标位置：{code_to_station_name(test_goal_node)}（编码 {test_goal_node}）"
            goal_surf = font_md.render(goal_text, True, (255, 200, 160))
            screen.blit(goal_surf, (pad_x, y))
            goal_icon_x = min(pad_x + goal_surf.get_width() + 10, W - 70)
            _draw_station_icon(screen, station_icons_mini, test_goal_node, goal_icon_x, y - 6, max_side=40)
            y += max(font_md.get_linesize() + 2, 40) + 2
            y = _blit_wrapped(
                screen,
                font_sm,
                f"本试次已用步数：{test_step} / {_MAX_ACTIONS_PER_TRIAL}",
                (180, 180, 200),
                pad_x,
                y,
                text_max_w,
            )
            y += 10
            y = _blit_wrapped(screen, font_sm,
                "点击彩色线或按快捷键选择下一步交通工具。",
                (190, 190, 210), pad_x, y, text_max_w)

            # 可视化图
            available_mode_dirs = _get_available_mode_dirs(game)
            vis_top = y + 6
            vis_size = min(W - pad_x * 2, H - vis_top - 30, 340)
            vis_rect = pygame.Rect((W - vis_size) // 2, vis_top, vis_size, vis_size)
            vis_widget.set_rect(vis_rect)
            vis_widget.draw(screen, font_sm, current_code, available_mode_dirs, hover_pos=hover_pos)

            _blit_wrapped(screen, font_sm, "ESC：退出（数据会保存）", (140, 140, 160), pad_x, H - 24, text_max_w)
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
                    f"  试次 {i + 1}：{code_to_station_name(s0)} → {code_to_station_name(g0)}  步数 {steps}（最短 {opt}，结果 {outcome}）",
                    (190, 200, 210),
                    pad_x,
                    y,
                    text_max_w,
                )
                y += 2
            y += 12
            _blit_wrapped(screen, font_sm, "按 ESC 退出（数据已保存）。", (170, 180, 190), pad_x, y, text_max_w)

        pygame.display.flip()
        clock.tick(30)

    out = save_session()
    print(f"Main2 数据已保存（legacy xlsx）: {out}")
    pygame.quit()
    return out


if __name__ == "__main__":
    main()
