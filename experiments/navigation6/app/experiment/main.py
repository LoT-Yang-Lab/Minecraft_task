"""
Navigation6 正式实验模块。

本模块包含两部分：
1. 向后兼容的工具函数（供 practice_main3 等外部脚本 import）
2. 9 节点图实验主函数 main()

图结构（graph9）：
  1  2  3          网格双向连接（上/下/左/右）
  4  5  6          四角单向环路 1→3→9→7→1
  7  8  9

动作按键：上(Q)  下(W)  左(E)  右(R)  环路(T)
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

_KEY_TO_ACTION = {
    # 字母键
    pygame.K_q: "上",
    pygame.K_w: "下",
    pygame.K_e: "左",
    pygame.K_r: "右",
    pygame.K_t: "环路",
    # 方向键
    pygame.K_UP: "上",
    pygame.K_DOWN: "下",
    pygame.K_LEFT: "左",
    pygame.K_RIGHT: "右",
    pygame.K_SPACE: "环路",
    # 小键盘（numpad）
    pygame.K_KP8: "上",
    pygame.K_KP2: "下",
    pygame.K_KP4: "左",
    pygame.K_KP6: "右",
    pygame.K_KP5: "环路",
    # WASD
    pygame.K_i: "上",
    pygame.K_k: "下",
    pygame.K_j: "左",
    pygame.K_l: "右",
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


# ── 渲染各阶段 ───────────────────────────────────────────

def _render_train_phase(
    screen, font_lg, font_md, font_sm, pad_x, text_max_w,
    current_node, train_goal, explored_edges, total_edges,
    last_action_msg,
):
    """绘制训练阶段界面，返回无。"""
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
        "说明：选择动作后会告知你移动到了哪个站点。探索率达到 100% 后进入测试阶段。",
        (190, 190, 210), pad_x, y, text_max_w)
    y += 10
    if last_action_msg:
        y = _blit_wrapped(screen, font_md, last_action_msg, (255, 220, 140), pad_x, y, text_max_w)
        y += 8
    y += 6
    y = _blit_wrapped(screen, font_md, "可选动作：", (210, 210, 225), pad_x, y, text_max_w)
    y += 4
    for act in ACTION_NAMES:
        dest = get_next_node(current_node, act)
        key = ACTION_KEYS[act]
        if dest is not None:
            tried = (current_node, act) in explored_edges
            mark = "✓" if tried else "  "
            color = (160, 160, 170) if tried else (225, 225, 210)
            y = _blit_wrapped(screen, font_sm, f"  [{key}] {act}  {mark}", color, pad_x, y, text_max_w)
        else:
            y = _blit_wrapped(screen, font_sm, f"  [{key}] {act}  （不可用）", (90, 90, 100), pad_x, y, text_max_w)
        y += 2
    y += 10
    _blit_wrapped(screen, font_sm, "ESC：退出（数据会保存）", (140, 140, 160), pad_x, y, text_max_w)


def _render_test_phase(
    screen, font_lg, font_md, font_sm, pad_x, text_max_w,
    test_trial_idx, test_trials_count, test_current_node, test_goal_node, test_step,
):
    """绘制测试阶段界面。"""
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
    y += 12
    y = _blit_wrapped(screen, font_md, "可选动作：", (210, 210, 225), pad_x, y, text_max_w)
    y += 4
    for act in ACTION_NAMES:
        dest = get_next_node(test_current_node, act)
        key = ACTION_KEYS[act]
        if dest is not None:
            y = _blit_wrapped(screen, font_sm, f"  [{key}] {act}", (225, 225, 210), pad_x, y, text_max_w)
        else:
            y = _blit_wrapped(screen, font_sm, f"  [{key}] {act}  （不可用）", (90, 90, 100), pad_x, y, text_max_w)
        y += 2
    y += 10
    _blit_wrapped(screen, font_sm, "ESC：退出（数据会保存）", (140, 140, 160), pad_x, y, text_max_w)


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
    W, H = 760, 680
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Navigation6 — 上(Q) 下(W) 左(E) 右(R) 环路(T)")

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

    # ══════════════════════════════════════════════════════
    # 主循环：事件收集 → 状态更新 → 渲染
    # ══════════════════════════════════════════════════════
    while running:
        # 1. 收集事件
        events = pygame.event.get()
        for ev in events:
            if ev.type == pygame.QUIT:
                running = False

        # 过滤出按键事件 + TEXTINPUT 事件（IME 兼容）
        key_events = [ev for ev in events if ev.type == pygame.KEYDOWN]
        text_events = [ev for ev in events if ev.type == pygame.TEXTINPUT]

        # 如果 KEYDOWN 没有捕获到字母键但 TEXTINPUT 有，则从 TEXTINPUT 构造虚拟按键
        # 这是为了兼容中文输入法开启时字母键被 IME 拦截的情况
        _TEXT_TO_ACTION = {"q": "上", "w": "下", "e": "左", "r": "右", "t": "环路"}
        mapped_key_actions = {_KEY_TO_ACTION.get(ev.key) for ev in key_events if ev.type == pygame.KEYDOWN}
        for tev in text_events:
            ch = tev.text.lower()
            if ch in _TEXT_TO_ACTION and _TEXT_TO_ACTION[ch] not in mapped_key_actions:
                # 构造一个伪 KEYDOWN 事件对象
                class _FakeKeyEvent:
                    def __init__(self, key_code):
                        self.type = pygame.KEYDOWN
                        self.key = key_code
                fake_key = {"q": pygame.K_q, "w": pygame.K_w, "e": pygame.K_e,
                            "r": pygame.K_r, "t": pygame.K_t}.get(ch)
                if fake_key is not None:
                    key_events.append(_FakeKeyEvent(fake_key))

        if key_events:
            print(f"[DEBUG] 收到 {len(key_events)} 个按键事件: "
                  f"{[pygame.key.name(ev.key) for ev in key_events]}, "
                  f"phase={phase}", flush=True)

        if not running:
            break

        # 2. 处理按键
        for ev in key_events:
            if ev.key == pygame.K_ESCAPE:
                running = False
                break

            if phase == PHASE_TRAIN:
                action = _KEY_TO_ACTION.get(ev.key)
                print(f"[DEBUG] TRAIN: key={pygame.key.name(ev.key)}, "
                      f"mapped_action={action}, current_node={current_node}",
                      flush=True)
                if action is None:
                    continue
                rt_ms = (time.perf_counter() - phase_prompt_time) * 1000.0
                dest = get_next_node(current_node, action)
                print(f"[DEBUG] TRAIN: action={action}, dest={dest}", flush=True)
                if dest is not None:
                    explored_edges.add((current_node, action))
                    train_step += 1
                    log_step(PHASE_TRAIN, 0, train_step, current_node, action, dest, True,
                             {"exploration_rate": exploration_rate(), "reaction_time_ms": round(rt_ms, 3)})
                    last_action_msg = (
                        f"执行「{action}」→ 移动到 "
                        f"{code_to_station_name(dest)}（编码 {dest}）"
                    )
                    current_node = dest
                    print(f"[DEBUG] TRAIN: 移动成功! new current_node={current_node}, "
                          f"last_action_msg={last_action_msg}", flush=True)
                    if current_node == train_goal:
                        train_goal = random.choice(
                            [n for n in NODE_IDS if n != current_node]
                        )
                    if exploration_rate() >= 1.0:
                        phase_prompt_time = start_test_phase()
                    else:
                        phase_prompt_time = time.perf_counter()
                else:
                    last_action_msg = f"动作「{action}」在当前位置不可用。"
                    log_step(PHASE_TRAIN, 0, train_step, current_node, action, None, False,
                             {"reaction_time_ms": round(rt_ms, 3)})
                    print(f"[DEBUG] TRAIN: 动作不可用", flush=True)
                    phase_prompt_time = time.perf_counter()

            elif phase == PHASE_TEST:
                action = _KEY_TO_ACTION.get(ev.key)
                if action is None:
                    continue
                rt_ms = (time.perf_counter() - phase_prompt_time) * 1000.0
                dest = get_next_node(test_current_node, action)
                if dest is not None:
                    test_step += 1
                    log_step(PHASE_TEST, test_trial_idx + 1, test_step,
                             test_current_node, action, dest, True,
                             {"goal_node": test_goal_node,
                              "reaction_time_ms": round(rt_ms, 3),
                              "optimal_distance": bfs_distance(
                                  test_trials[test_trial_idx][0], test_goal_node)})
                    test_current_node = dest
                    if test_current_node == test_goal_node:
                        advance_test_trial()
                    else:
                        phase_prompt_time = time.perf_counter()
                else:
                    log_step(PHASE_TEST, test_trial_idx + 1, test_step,
                             test_current_node, action, None, False,
                             {"goal_node": test_goal_node, "reaction_time_ms": round(rt_ms, 3)})
                    phase_prompt_time = time.perf_counter()

            elif phase == PHASE_FINISHED:
                pass  # ESC already handled above

        if not running:
            break

        # 3. 渲染
        screen.fill((28, 28, 32))
        if phase == PHASE_TRAIN:
            _render_train_phase(
                screen, font_lg, font_md, font_sm, pad_x, text_max_w,
                current_node, train_goal, explored_edges, total_edges,
                last_action_msg,
            )
        elif phase == PHASE_TEST:
            _render_test_phase(
                screen, font_lg, font_md, font_sm, pad_x, text_max_w,
                test_trial_idx, len(test_trials),
                test_current_node, test_goal_node, test_step,
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
