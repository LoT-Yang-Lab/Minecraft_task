"""
Navigation6 正式实验模块。

本模块包含两部分：
1. 向后兼容的工具函数（供 practice_main3 等外部脚本 import）
2. 9 节点图实验主函数 main()

图结构（graph9）：
  1  2  3          网格双向连接（公交前后/地铁前后）
  4  5  6          四角单向环线 1→3→9→7→1
  7  8  9

动作按键：公交(前)(Q) 公交(后)(E) 地铁(前)(A) 地铁(后)(D) 环线(W)
"""
from __future__ import annotations

import os
import sys
import time
import random
import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Set, Optional, Any, Union

# ── 确保项目根在 sys.path（支持直接运行本文件） ──────────
_this_file = Path(__file__).resolve()
_project_root = _this_file.parents[4]  # .../Minecraft8.0
_project_root_str = str(_project_root)
if _project_root_str not in sys.path:
    sys.path.insert(0, _project_root_str)

import pygame

from experiments.navigation6.app.paths import (
    get_nav6_root, maps_dir, trial_sequences_dir,
    trajectory_raw_dir,
)
from experiments.navigation6.app.common.station_names import code_to_station_name
from experiments.navigation6.app.common.trajectory_export import export_navigation_session_to_legacy_xlsx

# ── graph9：9 节点图核心逻辑 ─────────────────────────────
from experiments.navigation6.app.experiment.graph9 import (
    NODE_IDS,
    ACTION_NAMES,
    ACTION_KEYS,
    get_next_node,
    get_available_actions as graph_available_actions,
    all_valid_edges,
    total_valid_actions,
    bfs_distance,
    shortest_path,
    generate_test_trials,
)

# ═══════════════════════════════════════════════════════════
# 向后兼容接口（practice_main3 等外部脚本依赖）
# ═══════════════════════════════════════════════════════════
from experiments.navigation6.app.experiment.game import GameNavigation6
from experiments.navigation6.app.common.transit_action_display import (
    transit_mode_action_with_direction_label,
)

_NAV6_MAPS_DIR = maps_dir()
_NAV6_TRIAL_SEQUENCE_DIR = trial_sequences_dir()
EXPERIMENT_MAPS = [
    ("地图1774095558", "map_1774095558.json"),
]


def _resolve_map_path(filename: str) -> str:
    return os.path.abspath(os.path.join(_NAV6_MAPS_DIR, filename))


def _resolve_trial_sequence_path(map_filename: str) -> str:
    map_id = os.path.splitext(os.path.basename(map_filename))[0]
    return os.path.abspath(os.path.join(_NAV6_TRIAL_SEQUENCE_DIR, f"{map_id}.json"))


def build_position_encoding(
    game: GameNavigation6,
) -> Tuple[Dict[Tuple[int, int], int], Dict[int, Tuple[int, int]], int]:
    """Navigation6：单格 ∪ 各线路站点格，去障碍后按 (gx, gy) 字典序编码 1～N。"""
    obstacle_map = getattr(game, "obstacle_map", {}) or {}
    walkable: List[Tuple[int, int]] = [
        c for c in (getattr(game, "single_cells", set()) or set())
        if c not in obstacle_map
    ]
    for pos in game._all_station_positions():
        if pos not in obstacle_map and pos not in walkable:
            walkable.append(pos)
    for _rid, room in getattr(game, "rooms", {}).items():
        lx, ly = room.logical_pos
        for dy in range(3):
            for dx in range(3):
                gx, gy = lx * 3 + dx, ly * 3 + dy
                if game._is_walkable(gx, gy) and (gx, gy) not in walkable:
                    walkable.append((gx, gy))
    walkable = sorted(set(walkable), key=lambda c: (c[0], c[1]))
    cell_to_code = {c: i + 1 for i, c in enumerate(walkable)}
    code_to_cell = {i + 1: c for i, c in enumerate(walkable)}
    target_pos = getattr(game, "original_target_pos", None)
    target_code = cell_to_code[target_pos] if target_pos and target_pos in cell_to_code else 0
    return cell_to_code, code_to_cell, target_code


def get_available_actions(
    game: GameNavigation6,
    include_bidirectional_for_surface: bool = False,
) -> List[Tuple[str, str, Optional[Union[str, int]]]]:
    """返回当前可执行动作列表（旧版地图交通模式）。"""
    px, py = game.player_x, game.player_y
    actions: List[Tuple[str, str, Optional[Union[str, int]]]] = []
    modes = getattr(game, "transit_modes", []) or []
    for line_idx, _ in game.get_instant_subway_next_stations(px, py):
        m = modes[line_idx] if line_idx < len(modes) else "metro"
        label = transit_mode_action_with_direction_label(m, "next")
        actions.append((label, "instant_transit_next", line_idx))
    if include_bidirectional_for_surface:
        for line_idx, _ in game.get_instant_subway_prev_stations(px, py):
            m = modes[line_idx] if line_idx < len(modes) else "metro"
            label = transit_mode_action_with_direction_label(m, "prev")
            actions.append((label, "instant_transit_prev", line_idx))
    return actions


def execute_action(
    game: GameNavigation6,
    action: Tuple[str, str, Optional[Union[str, int]]],
) -> bool:
    """执行一条动作，返回是否执行成功（旧版地图交通模式）。"""
    _label, action_key, extra = action
    if action_key in ("instant_transit_next", "instant_subway_next") and extra is not None:
        idx = int(extra) if not isinstance(extra, int) else extra
        return game.instant_subway_to_next_station(idx)
    if action_key in ("instant_transit_prev", "instant_subway_prev") and extra is not None:
        idx = int(extra) if not isinstance(extra, int) else extra
        return game.instant_subway_to_prev_station(idx)
    if action_key == "wait":
        return game.wait_one_step()
    return False


# ═══════════════════════════════════════════════════════════
# 9 节点图实验 —— pygame 主程序
# ═══════════════════════════════════════════════════════════

import math as _math

_KEY_TO_ACTION = {
    # 字母键
    pygame.K_q: "公交(前)",
    pygame.K_e: "公交(后)",
    pygame.K_a: "地铁(前)",
    pygame.K_d: "地铁(后)",
    pygame.K_w: "环线",
}

# IME 兼容用常量
_TEXT_TO_ACTION = {"q": "公交(前)", "e": "公交(后)", "a": "地铁(前)", "d": "地铁(后)", "w": "环线"}
_TEXT_TO_FAKE_KEY = {"q": pygame.K_q, "e": pygame.K_e, "a": pygame.K_a,
                     "d": pygame.K_d, "w": pygame.K_w}


class _FakeKeyEvent:
    """IME 兼容用伪按键事件。"""
    def __init__(self, key_code):
        self.type = pygame.KEYDOWN
        self.key = key_code

# ── 动作对应的颜色（3 种交通工具 3 种颜色） ────────────────
# 同一交通工具的前/后方向使用相同颜色
_TRANSPORT_COLORS: Dict[str, Tuple[int, int, int]] = {
    "公交": (60, 160, 255),      # 蓝色
    "地铁": (80, 200, 120),      # 绿色
    "环线": (180, 100, 240),     # 紫色
}

ACTION_COLORS: Dict[str, Tuple[int, int, int]] = {
    "公交(前)": _TRANSPORT_COLORS["公交"],
    "公交(后)": _TRANSPORT_COLORS["公交"],
    "地铁(前)": _TRANSPORT_COLORS["地铁"],
    "地铁(后)": _TRANSPORT_COLORS["地铁"],
    "环线": _TRANSPORT_COLORS["环线"],
}

# ── 可视化参数 ──────────────────────────────────────────
_VIS_NODE_RADIUS = 28
_VIS_LINE_LEN = 100
_VIS_LINE_WIDTH = 6
_VIS_HIT_WIDTH = 18       # 线条点击判定宽度
_VIS_ANIM_DURATION = 0.3  # 动画持续时间（秒）

# 动作在视觉图中的方向角度（从中心节点出发）
_ACTION_ANGLES: Dict[str, float] = {
    "公交(前)": -90.0,
    "公交(后)": 90.0,
    "地铁(前)": 180.0,
    "地铁(后)": 0.0,
    "环线": 45.0,  # 右下方向的弧线
}


def _blit_wrapped(
    screen: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    color: Tuple[int, int, int],
    x: int, y: int,
    max_width: int,
    line_gap: int = 2,
) -> int:
    """逐字折行绘制中文文本，返回下一行 y。"""
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
    可视化小部件：在指定矩形区域内绘制当前节点和与之相连的动作线。
    每条线的颜色对应不同的动作/交通方式。
    被试可以点击线来选择动作。
    支持移动动画。
    """

    def __init__(self):
        self.rect = pygame.Rect(0, 0, 300, 300)
        # 当前展示的线条 hit-test 信息: [(action, start_xy, end_xy), ...]
        self._edge_hitboxes: List[Tuple[str, Tuple[float, float], Tuple[float, float]]] = []
        # 动画状态
        self._anim_active = False
        self._anim_start_time = 0.0
        self._anim_from_xy: Tuple[float, float] = (0, 0)
        self._anim_to_xy: Tuple[float, float] = (0, 0)
        self._anim_action = ""

    def set_rect(self, rect: pygame.Rect):
        self.rect = rect

    def start_animation(self, action: str, from_node: int, to_node: int):
        """启动从 from_node 到 to_node 的移动动画。"""
        cx = self.rect.centerx
        cy = self.rect.centery
        self._anim_from_xy = (float(cx), float(cy))
        angle_deg = _ACTION_ANGLES.get(action, 0.0)
        angle_rad = _math.radians(angle_deg)
        end_x = cx + _VIS_LINE_LEN * _math.cos(angle_rad)
        end_y = cy + _VIS_LINE_LEN * _math.sin(angle_rad)
        self._anim_to_xy = (end_x, end_y)
        self._anim_action = action
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

    def handle_click(self, mouse_pos: Tuple[int, int], current_node: int) -> Optional[str]:
        """
        检测鼠标点击是否命中某条动作线。
        返回命中的动作名，或 None。
        """
        if self.is_animating():
            return None
        mx, my = mouse_pos
        if not self.rect.collidepoint(mx, my):
            return None
        best_action = None
        best_dist = _VIS_HIT_WIDTH
        for action, (sx, sy), (ex, ey) in self._edge_hitboxes:
            d = _point_to_segment_distance(float(mx), float(my), sx, sy, ex, ey)
            if d < best_dist:
                best_dist = d
                best_action = action
        return best_action

    def draw(self, screen: pygame.Surface, font_sm: pygame.font.Font,
             current_node: int, explored_edges: Optional[Set[Tuple[int, str]]] = None,
             hover_pos: Optional[Tuple[int, int]] = None):
        """
        绘制可视化图：当前节点 + 所有可用动作的线。
        explored_edges: 训练阶段已探索边集合（用于标记已试过的边）
        """
        # 背景框
        pygame.draw.rect(screen, (38, 40, 48), self.rect, border_radius=12)
        pygame.draw.rect(screen, (70, 76, 90), self.rect, 2, border_radius=12)

        cx = self.rect.centerx
        cy = self.rect.centery

        self._edge_hitboxes.clear()

        # 检查是否在动画中
        if self.is_animating():
            elapsed = time.perf_counter() - self._anim_start_time
            t = min(1.0, elapsed / _VIS_ANIM_DURATION)
            # 缓动函数 (ease-out quad)
            eased = 1.0 - (1.0 - t) ** 2
            anim_x = self._anim_from_xy[0] + (self._anim_to_xy[0] - self._anim_from_xy[0]) * eased
            anim_y = self._anim_from_xy[1] + (self._anim_to_xy[1] - self._anim_from_xy[1]) * eased
            # 绘制动画中的动作线（颜色对应）
            color = ACTION_COLORS.get(self._anim_action, (200, 200, 200))
            pygame.draw.line(screen, color,
                             (int(self._anim_from_xy[0]), int(self._anim_from_xy[1])),
                             (int(self._anim_to_xy[0]), int(self._anim_to_xy[1])),
                             _VIS_LINE_WIDTH)
            # 绘制移动中的节点标记
            pygame.draw.circle(screen, (255, 255, 255), (int(anim_x), int(anim_y)), _VIS_NODE_RADIUS)
            pygame.draw.circle(screen, color, (int(anim_x), int(anim_y)), _VIS_NODE_RADIUS, 3)
            label = code_to_station_name(current_node)
            txt = font_sm.render(label, True, (40, 40, 50))
            txt_r = txt.get_rect(center=(int(anim_x), int(anim_y)))
            screen.blit(txt, txt_r)
            return

        # 正常绘制：当前节点在中心，周围是可用动作的线
        # 先绘制线条
        for act in ACTION_NAMES:
            dest = get_next_node(current_node, act)
            if dest is None:
                continue
            color = ACTION_COLORS.get(act, (200, 200, 200))
            angle_deg = _ACTION_ANGLES.get(act, 0.0)
            angle_rad = _math.radians(angle_deg)
            end_x = cx + _VIS_LINE_LEN * _math.cos(angle_rad)
            end_y = cy + _VIS_LINE_LEN * _math.sin(angle_rad)

            # 检查鼠标是否悬停在此线上
            line_alpha = 255
            line_width = _VIS_LINE_WIDTH
            if hover_pos and self.rect.collidepoint(hover_pos[0], hover_pos[1]):
                d = _point_to_segment_distance(float(hover_pos[0]), float(hover_pos[1]),
                                                float(cx), float(cy), end_x, end_y)
                if d < _VIS_HIT_WIDTH:
                    line_width = _VIS_LINE_WIDTH + 3  # 加粗高亮

            # 已探索标记（颜色变淡）
            if explored_edges and (current_node, act) in explored_edges:
                color = tuple(min(255, c + 60) for c in color)

            pygame.draw.line(screen, color, (cx, cy), (int(end_x), int(end_y)), line_width)
            self._edge_hitboxes.append((act, (float(cx), float(cy)), (end_x, end_y)))

            # 在线末端画一个小圆点（表示可达的未知节点）
            pygame.draw.circle(screen, color, (int(end_x), int(end_y)), 8)

            # 在线旁标注动作名和按键
            key = ACTION_KEYS[act]
            label_x = cx + (_VIS_LINE_LEN + 20) * _math.cos(angle_rad)
            label_y = cy + (_VIS_LINE_LEN + 20) * _math.sin(angle_rad)

            tried_mark = ""
            if explored_edges and (current_node, act) in explored_edges:
                tried_mark = " ✓"
            act_label = f"[{key}] {act}{tried_mark}"
            act_surf = font_sm.render(act_label, True, color)
            act_rect = act_surf.get_rect(center=(int(label_x), int(label_y)))
            screen.blit(act_surf, act_rect)

        # 绘制中心节点
        pygame.draw.circle(screen, (255, 255, 255), (cx, cy), _VIS_NODE_RADIUS)
        pygame.draw.circle(screen, (100, 140, 220), (cx, cy), _VIS_NODE_RADIUS, 3)
        node_label = code_to_station_name(current_node)
        node_surf = font_sm.render(node_label, True, (40, 40, 50))
        node_rect = node_surf.get_rect(center=(cx, cy))
        screen.blit(node_surf, node_rect)

        # 图例（按交通工具类型，3 种）
        legend_x = self.rect.x + 8
        legend_y = self.rect.bottom - len(_TRANSPORT_COLORS) * 16 - 8
        for transport_name, transport_color in _TRANSPORT_COLORS.items():
            pygame.draw.line(screen, transport_color, (legend_x, legend_y + 6), (legend_x + 16, legend_y + 6), 3)
            legend_surf = font_sm.render(f" {transport_name}", True, (180, 180, 195))
            screen.blit(legend_surf, (legend_x + 18, legend_y - 2))
            legend_y += 16


# ── 渲染各阶段 ───────────────────────────────────────────

def _render_train_phase(
    screen, font_lg, font_md, font_sm, pad_x, text_max_w,
    current_node, train_goal, explored_edges, total_edges,
    last_action_msg, vis_widget: _VisGraphWidget,
    hover_pos: Optional[Tuple[int, int]] = None,
):
    """绘制训练阶段界面（含可视化图）。"""
    W, H = screen.get_size()
    rate = len(explored_edges) / total_edges if total_edges > 0 else 0.0
    y = 16
    y = _blit_wrapped(screen, font_lg, "训练阶段 — 自由探索", (220, 220, 255), pad_x, y, text_max_w)
    y += 8
    y = _blit_wrapped(screen, font_md,
        f"当前位置：{code_to_station_name(current_node)}（编码 {current_node}）",
        (180, 230, 180), pad_x, y, text_max_w)
    y += 4
    y = _blit_wrapped(screen, font_md,
        f"目标位置：{code_to_station_name(train_goal)}（编码 {train_goal}）",
        (230, 200, 180), pad_x, y, text_max_w)
    y += 8
    # 探索率进度条
    bar_x, bar_y, bar_w, bar_h = pad_x, y, text_max_w, 24
    pygame.draw.rect(screen, (60, 60, 70), (bar_x, bar_y, bar_w, bar_h))
    fill_w = int(bar_w * rate)
    bar_color = (80, 200, 120) if rate < 1.0 else (50, 255, 100)
    pygame.draw.rect(screen, bar_color, (bar_x, bar_y, fill_w, bar_h))
    rate_text = f"探索率：{rate:.0%}（{len(explored_edges)}/{total_edges}）"
    screen.blit(font_sm.render(rate_text, True, (255, 255, 255)), (bar_x + 6, bar_y + 3))
    y += bar_h + 10
    y = _blit_wrapped(screen, font_sm,
        "说明：点击彩色线或按快捷键选择交通工具。探索率达到 100% 后进入测试阶段。",
        (190, 190, 210), pad_x, y, text_max_w)
    y += 10
    if last_action_msg:
        y = _blit_wrapped(screen, font_md, last_action_msg, (255, 220, 140), pad_x, y, text_max_w)
        y += 8

    # 可视化图
    vis_top = y + 6
    vis_size = min(W - pad_x * 2, H - vis_top - 30, 340)
    vis_rect = pygame.Rect((W - vis_size) // 2, vis_top, vis_size, vis_size)
    vis_widget.set_rect(vis_rect)
    vis_widget.draw(screen, font_sm, current_node, explored_edges=explored_edges, hover_pos=hover_pos)

    _blit_wrapped(screen, font_sm, "ESC：退出（数据会保存）", (140, 140, 160), pad_x, H - 24, text_max_w)


def _render_test_phase(
    screen, font_lg, font_md, font_sm, pad_x, text_max_w,
    test_trial_idx, test_trials_count, test_current_node, test_goal_node, test_step,
    vis_widget: _VisGraphWidget,
    hover_pos: Optional[Tuple[int, int]] = None,
):
    """绘制测试阶段界面（含可视化图）。"""
    W, H = screen.get_size()
    y = 16
    y = _blit_wrapped(screen, font_lg, "测试阶段 — 导航任务", (255, 220, 200), pad_x, y, text_max_w)
    y += 8
    y = _blit_wrapped(screen, font_md,
        f"试次：{test_trial_idx + 1} / {test_trials_count}",
        (190, 210, 230), pad_x, y, text_max_w)
    y += 4
    y = _blit_wrapped(screen, font_md,
        f"当前位置：{code_to_station_name(test_current_node)}（编码 {test_current_node}）",
        (180, 230, 180), pad_x, y, text_max_w)
    y += 4
    y = _blit_wrapped(screen, font_md,
        f"目标位置：{code_to_station_name(test_goal_node)}（编码 {test_goal_node}）",
        (255, 200, 160), pad_x, y, text_max_w)
    y += 4
    y = _blit_wrapped(screen, font_sm,
        f"本试次已用步数：{test_step}",
        (180, 180, 200), pad_x, y, text_max_w)
    y += 10
    y = _blit_wrapped(screen, font_sm,
        "点击彩色线或按快捷键选择下一步交通工具。",
        (190, 190, 210), pad_x, y, text_max_w)

    # 可视化图
    vis_top = y + 6
    vis_size = min(W - pad_x * 2, H - vis_top - 30, 340)
    vis_rect = pygame.Rect((W - vis_size) // 2, vis_top, vis_size, vis_size)
    vis_widget.set_rect(vis_rect)
    vis_widget.draw(screen, font_sm, test_current_node, hover_pos=hover_pos)

    _blit_wrapped(screen, font_sm, "ESC：退出（数据会保存）", (140, 140, 160), pad_x, H - 24, text_max_w)


def _render_finished_phase(
    screen, font_lg, font_md, font_sm, pad_x, text_max_w,
    test_trials, test_trial_steps,
):
    """绘制实验结束界面。"""
    y = 60
    y = _blit_wrapped(screen, font_lg, "实验结束", (220, 255, 220), pad_x, y, text_max_w)
    y += 16
    y = _blit_wrapped(screen, font_md,
        f"已完成 {len(test_trials)} 个导航试次。",
        (200, 220, 210), pad_x, y, text_max_w)
    y += 8
    for i, steps in enumerate(test_trial_steps):
        s, g = test_trials[i]
        opt = bfs_distance(s, g)
        y = _blit_wrapped(screen, font_sm,
            f"  试次 {i+1}：{code_to_station_name(s)} → {code_to_station_name(g)}"
            f"  步数 {steps}（最短 {opt}）",
            (190, 200, 210), pad_x, y, text_max_w)
        y += 2
    y += 12
    _blit_wrapped(screen, font_sm, "按 ESC 退出（数据已保存）。", (170, 180, 190), pad_x, y, text_max_w)


# ── 主函数 ───────────────────────────────────────────────

def main(
    start_with_test: bool = False,
    test_trials_override: Optional[List[Tuple[int, int]]] = None,
    session_metadata: Optional[Dict[str, Any]] = None,
):
    """
    实验流程：
    1. 训练阶段 — 自由探索 9 节点图，探索率达 100% 后进入测试。
    2. 测试阶段 — 9 个 trial，每个 trial 给定起点和目标，到达即完成。

    参数：
    - start_with_test=True 时跳过训练，直接进入测试阶段。
    """
    pygame.init()
    # 禁用 IME 文本输入模式，确保中文输入法下 Q/W/E/R/T 等字母键
    # 能正常产生 KEYDOWN 事件，而不是被输入法拦截
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
    running = True

    # ── 数据记录 ──────────────────────────────────────────
    data_root = trajectory_raw_dir()
    os.makedirs(data_root, exist_ok=True)
    session_start = datetime.datetime.now()
    session_log: List[Dict] = []

    def log_step(phase, trial_id, step, from_node, action, to_node, is_valid, extra=None):
        entry = {
            "phase": phase, "trial_id": trial_id, "step": step,
            "timestamp": time.time(), "from_node": from_node,
            "action": action, "to_node": to_node, "is_valid": is_valid,
        }
        if extra:
            entry.update(extra)
        session_log.append(entry)

    def save_session():
        map_label = EXPERIMENT_MAPS[0][0] if EXPERIMENT_MAPS else ""
        map_file = EXPERIMENT_MAPS[0][1] if EXPERIMENT_MAPS else ""
        map_id = os.path.splitext(os.path.basename(map_file))[0] if map_file else ""
        return export_navigation_session_to_legacy_xlsx(
            data_root=data_root,
            session_start=session_start,
            session_end=datetime.datetime.now(),
            map_id=map_id,
            map_structure=map_label or map_id,
            steps=session_log,
            test_trials=test_trials,
            trial_summaries=[],
            session_metadata=session_metadata,
            code_to_cell=None,
            participant_id="Navigation6_User",
            task_type="Navigation6_Test",
        )

    # ── 阶段状态 ──────────────────────────────────────────
    PHASE_TRAIN = "train"
    PHASE_TEST = "test"
    PHASE_FINISHED = "finished"
    phase = PHASE_TRAIN

    current_node = random.choice(NODE_IDS)
    explored_edges: Set[Tuple[int, str]] = set()
    total_edges = total_valid_actions()
    train_step = 0
    train_goal = random.choice([n for n in NODE_IDS if n != current_node])
    last_action_msg = ""

    test_trials: List[Tuple[int, int]] = []
    test_trial_idx = 0
    test_step = 0
    test_current_node = 1
    test_goal_node = 1
    test_trial_steps: List[int] = []
    phase_prompt_time = time.perf_counter()

    # ── 可视化图小部件 ────────────────────────────────────
    vis_widget = _VisGraphWidget()

    def exploration_rate():
        return len(explored_edges) / total_edges if total_edges > 0 else 0.0

    def start_test_phase():
        nonlocal phase, test_trials, test_trial_idx, test_step
        nonlocal test_current_node, test_goal_node, test_trial_steps
        phase = PHASE_TEST
        if test_trials_override:
            test_trials = [
                (int(pair[0]), int(pair[1]))
                for pair in test_trials_override
            ]
        else:
            test_trials = generate_test_trials(min_distance=2)
        test_trial_idx = 0
        test_step = 0
        test_trial_steps = []
        s, g = test_trials[0]
        test_current_node, test_goal_node = s, g
        return time.perf_counter()

    if start_with_test:
        phase_prompt_time = start_test_phase()

    def advance_test_trial():
        nonlocal test_trial_idx, test_step, test_current_node, test_goal_node, phase, phase_prompt_time
        test_trial_steps.append(test_step)
        test_trial_idx += 1
        test_step = 0
        if test_trial_idx >= len(test_trials):
            phase = PHASE_FINISHED
        else:
            s, g = test_trials[test_trial_idx]
            test_current_node, test_goal_node = s, g
            phase_prompt_time = time.perf_counter()

    def _process_action(action: str, source: str = "key"):
        """处理一个动作（来自键盘或鼠标点击），返回是否有效执行。"""
        nonlocal current_node, train_step, last_action_msg, train_goal
        nonlocal test_current_node, test_step, phase_prompt_time, phase

        if vis_widget.is_animating():
            return False

        if phase == PHASE_TRAIN:
            rt_ms = (time.perf_counter() - phase_prompt_time) * 1000.0
            dest = get_next_node(current_node, action)
            if dest is not None:
                explored_edges.add((current_node, action))
                train_step += 1
                log_step(PHASE_TRAIN, 0, train_step, current_node, action, dest, True,
                         {"exploration_rate": exploration_rate(),
                          "reaction_time_ms": round(rt_ms, 3),
                          "input_source": source})
                # 启动动画
                vis_widget.start_animation(action, current_node, dest)
                last_action_msg = (
                    f"执行「{action}」→ 移动到 "
                    f"{code_to_station_name(dest)}（编码 {dest}）"
                )
                current_node = dest
                if current_node == train_goal:
                    train_goal = random.choice(
                        [n for n in NODE_IDS if n != current_node]
                    )
                if exploration_rate() >= 1.0:
                    phase_prompt_time = start_test_phase()
                else:
                    phase_prompt_time = time.perf_counter()
                return True
            else:
                last_action_msg = f"动作「{action}」在当前位置不可用。"
                log_step(PHASE_TRAIN, 0, train_step, current_node, action, None, False,
                         {"reaction_time_ms": round(rt_ms, 3), "input_source": source})
                phase_prompt_time = time.perf_counter()
                return False

        elif phase == PHASE_TEST:
            rt_ms = (time.perf_counter() - phase_prompt_time) * 1000.0
            dest = get_next_node(test_current_node, action)
            if dest is not None:
                test_step += 1
                log_step(PHASE_TEST, test_trial_idx + 1, test_step,
                         test_current_node, action, dest, True,
                         {"goal_node": test_goal_node,
                          "reaction_time_ms": round(rt_ms, 3),
                          "input_source": source,
                          "optimal_distance": bfs_distance(
                              test_trials[test_trial_idx][0], test_goal_node)})
                # 启动动画
                vis_widget.start_animation(action, test_current_node, dest)
                test_current_node = dest
                if test_current_node == test_goal_node:
                    advance_test_trial()
                else:
                    phase_prompt_time = time.perf_counter()
                return True
            else:
                log_step(PHASE_TEST, test_trial_idx + 1, test_step,
                         test_current_node, action, None, False,
                         {"goal_node": test_goal_node,
                          "reaction_time_ms": round(rt_ms, 3),
                          "input_source": source})
                phase_prompt_time = time.perf_counter()
                return False

        return False

    # ══════════════════════════════════════════════════════
    # 主循环：事件收集 → 状态更新 → 渲染
    # ══════════════════════════════════════════════════════
    while running:
        # 获取鼠标位置用于悬停高亮
        hover_pos = pygame.mouse.get_pos()

        # 1. 收集事件
        events = pygame.event.get()
        for ev in events:
            if ev.type == pygame.QUIT:
                running = False

        # 过滤出按键事件 + TEXTINPUT 事件（IME 兼容）
        key_events = [ev for ev in events if ev.type == pygame.KEYDOWN]
        text_events = [ev for ev in events if ev.type == pygame.TEXTINPUT]
        click_events = [ev for ev in events if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1]

        # 如果 KEYDOWN 没有捕获到字母键但 TEXTINPUT 有，则从 TEXTINPUT 构造虚拟按键
        # 这是为了兼容中文输入法开启时字母键被 IME 拦截的情况
        _TEXT_TO_ACTION = {"q": "公交(前)", "e": "公交(后)", "a": "地铁(前)", "d": "地铁(后)", "w": "环线"}
        mapped_key_actions = {_KEY_TO_ACTION.get(ev.key) for ev in key_events if ev.type == pygame.KEYDOWN}
        for tev in text_events:
            ch = tev.text.lower()
            if ch in _TEXT_TO_ACTION and _TEXT_TO_ACTION[ch] not in mapped_key_actions:
                fake_key = _TEXT_TO_FAKE_KEY.get(ch)
                if fake_key is not None:
                    key_events.append(_FakeKeyEvent(fake_key))

        if not running:
            break

        # 2. 处理鼠标点击（选择动作线）
        if not vis_widget.is_animating():
            for cev in click_events:
                if phase in (PHASE_TRAIN, PHASE_TEST):
                    cur = current_node if phase == PHASE_TRAIN else test_current_node
                    clicked_action = vis_widget.handle_click(cev.pos, cur)
                    if clicked_action is not None:
                        _process_action(clicked_action, source="click")
                        break

        # 3. 处理按键
        for ev in key_events:
            if ev.key == pygame.K_ESCAPE:
                running = False
                break

            if phase in (PHASE_TRAIN, PHASE_TEST):
                action = _KEY_TO_ACTION.get(ev.key)
                if action is None:
                    continue
                _process_action(action, source="key")

            elif phase == PHASE_FINISHED:
                pass  # ESC already handled above

        if not running:
            break

        # 4. 渲染
        screen.fill((28, 28, 32))
        if phase == PHASE_TRAIN:
            _render_train_phase(
                screen, font_lg, font_md, font_sm, pad_x, text_max_w,
                current_node, train_goal, explored_edges, total_edges,
                last_action_msg, vis_widget, hover_pos=hover_pos,
            )
        elif phase == PHASE_TEST:
            _render_test_phase(
                screen, font_lg, font_md, font_sm, pad_x, text_max_w,
                test_trial_idx, len(test_trials),
                test_current_node, test_goal_node, test_step,
                vis_widget, hover_pos=hover_pos,
            )
        elif phase == PHASE_FINISHED:
            _render_finished_phase(
                screen, font_lg, font_md, font_sm, pad_x, text_max_w,
                test_trials, test_trial_steps,
            )

        pygame.display.flip()
        clock.tick(30)

    # ── 退出保存 ──────────────────────────────────────────
    save_session()
    pygame.quit()


if __name__ == "__main__":
    main()


def main_test_only() -> None:
    """仅运行测试阶段入口（跳过训练阶段）。"""
    main(start_with_test=True)
