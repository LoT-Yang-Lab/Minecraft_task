#!/usr/bin/env python3
"""
Crafting 练习阶段：流程对齐 navigation6 practice_main（独立入口、编号、选图、
选图后的练习指导语、多轮时长与九石访问覆盖约束、JSON 归档）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pygame

this_dir = os.path.dirname(os.path.abspath(__file__))
if this_dir not in sys.path:
    sys.path.insert(0, this_dir)

from src.bottle_images import BottleImageCache, collect_bottle_asset_dirs, count_loaded_bottles
from src.config_io_crafting import load_trial_list
from src.game_crafting import GameCrafting
from src.main_crafting import (
    ACTION_KEYS,
    WINDOW_H,
    WINDOW_W,
    _action_key_symbol,
    _find_action_by_key,
    _font as _ui_font,
    _potion_index_for_action_key,
    ACTION_BTN_ERROR_S,
    ACTION_BTN_HIGHLIGHT_S,
    draw_ui,
    layout_rects,
)
from src.map_select_crafting import (
    resolve_transition_map_cli_path,
    run_transition_map_selection,
)
from src.participant_id_crafting import run_participant_id_screen
from src.recorder import RLDataRecorder
from src.rules_io_crafting import load_rule_data_with_transition_map
from src.stone_space import STONE_IDS
from src.stone_images import StoneImageCache, collect_stone_asset_dirs, count_loaded_gems

MIN_TRIAL_DURATION_SEC = 5 * 60


def _crafting_root() -> Path:
    return Path(__file__).resolve().parent


def practice_raw_dir(root: Path) -> Path:
    project_root = root.parent
    return project_root / "data" / "crafting" / "raw" / "practice"


def _save_practice_session(path: Path, payload: Dict[str, Any]) -> str:
    path.mkdir(parents=True, exist_ok=True)
    pid = payload.get("participant_id", "anonymous")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(pid)).strip("_") or "anonymous"
    filename = f"crafting_practice_{safe}_{ts}.json"
    out = path / filename
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return str(out)


def _font(size: int) -> pygame.font.Font:
    return _ui_font(size)


def _draw_wrapped(
    screen: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    x: int,
    y: int,
    width: int,
    color: Tuple[int, int, int],
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


def run_practice_guidance_screen(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    *,
    rounds_total: int,
    min_visits: int,
    min_trial_seconds: int,
    map_label: str,
) -> bool:
    """
    被试编号与地图选择之后呈现的指导语；Enter/空格继续，Esc/关闭窗口放弃。
    返回 True 表示进入练习，False 表示退出程序。
    """
    font_title = _font(26)
    font_body = _font(16)
    font_hint = _font(15)
    margin_x = 28
    text_w = WINDOW_W - margin_x * 2
    min_minutes = max(1, min_trial_seconds // 60)

    while True:
        screen.fill((28, 31, 38))
        y = 36
        y = _draw_wrapped(
            screen, font_title, "练习指导", margin_x, y, text_w, (230, 235, 255)
        )
        y += 12
        y = _draw_wrapped(
            screen,
            font_body,
            "本阶段用于正式实验开始前的操作熟悉，不计入正式任务成绩。请认真阅读下列说明，随后将进入练习界面进行自由探索。",
            margin_x,
            y,
            text_w,
            (205, 210, 225),
        )
        y += 8
        y = _draw_wrapped(
            screen,
            font_body,
            "界面说明：屏幕中央为当前石块状态；下方为三瓶魔法药水，可以改变石块的状态，对应键盘 "
            "Q / E（药水 1 正向与逆向）、A / D（药水 2 正向与逆向）、"
            "W（药水 3，神秘转化）。",
            margin_x,
            y,
            text_w,
            (205, 210, 225),
        )
        y += 6
        y = _draw_wrapped(
            screen,
            font_body,
            "右下方区域显示本局起始石块；需要时可按 R 将当前状态重置为该起始石块。",
            margin_x,
            y,
            text_w,
            (205, 210, 225),
        )
        y += 8
        y = _draw_wrapped(
            screen,
            font_body,
            "本练习不设置订单或目标石块任务，请您自行尝试各键，观察状态如何变化，然后尽可能多地记住潜在的转化关系。",
            margin_x,
            y,
            text_w,
            (205, 210, 225),
        )
        y += 8
        y = _draw_wrapped(
            screen,
            font_body,
            f"进度与轮次：练习共分 {rounds_total} 轮。每一轮须同时满足："
            f"（1）九块石头各自被「到达」不少于 {min_visits} 次；"
            f"（2）该轮累计时长不少于 {min_minutes} 分钟。",
            margin_x,
            y,
            text_w,
            (210, 215, 200),
        )
        y += 6
        y = _draw_wrapped(
            screen,
            font_body,
            f"当前地图：{map_label}。全部轮次完成后可按 Esc 结束并保存数据。",
            margin_x,
            y,
            text_w,
            (210, 215, 200),
        )
        _draw_wrapped(
            screen,
            font_hint,
            "Enter / 空格 进入练习  ·  Esc 退出",
            margin_x,
            WINDOW_H - 44,
            text_w,
            (150, 185, 220),
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


@dataclass
class StepLog:
    round_index: int
    step_index: int
    t_sec: float
    from_state: str
    to_state: str
    key_symbol: str
    explore_rate: float
    mastery_rate: float


def _metrics(
    visit_counts: Dict[str, int],
    min_visits: int,
) -> Tuple[float, float, int]:
    n = len(STONE_IDS)
    explored = sum(1 for s in STONE_IDS if visit_counts.get(s, 0) >= 1)
    mastered = sum(1 for s in STONE_IDS if visit_counts.get(s, 0) >= min_visits)
    return (explored / n, mastered / n, mastered)


def main() -> None:
    parser = argparse.ArgumentParser(description="Crafting 练习阶段")
    parser.add_argument("--participant_id", "-p", type=str, default=None, help="被试编号（跳过输入页）")
    parser.add_argument("--rules", type=str, default=None, help="规则 JSON")
    parser.add_argument(
        "--trials",
        type=str,
        default=None,
        help="练习用 trial 列表（默认 data/trials/practice_trial_list_v1.json）",
    )
    parser.add_argument(
        "--transition_map",
        type=str,
        default=None,
        help="跳过选图，直接指定转化地图 JSON（相对 crafting 根或绝对路径）",
    )
    parser.add_argument("--rounds", type=int, default=2, help="练习轮数（默认 2）")
    parser.add_argument("--min-visits", type=int, default=2, help="每块石头最少访问次数（默认 2）")
    parser.add_argument(
        "--min-trial-seconds",
        type=int,
        default=MIN_TRIAL_DURATION_SEC,
        help=f"每轮最短练习时长（秒，默认 {MIN_TRIAL_DURATION_SEC}）",
    )
    args = parser.parse_args()

    root = _crafting_root()
    default_rules = str(root / "data" / "rules" / "crafting_rules_v1.json")
    default_trials = str(root / "data" / "trials" / "practice_trial_list_v1.json")
    rules_path = args.rules or default_rules
    trials_path = args.trials or default_trials

    rounds_total = max(1, int(args.rounds))
    min_visits = max(1, int(args.min_visits))
    min_trial_seconds = max(1, int(args.min_trial_seconds))

    pygame.init()
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption("Crafting - 练习")
    clock = pygame.time.Clock()

    if args.participant_id and str(args.participant_id).strip():
        pid = str(args.participant_id).strip()
    else:
        pid = run_participant_id_screen(screen, clock)
        if pid is None:
            pygame.quit()
            sys.exit(0)

    if args.transition_map:
        try:
            transition_map_path = resolve_transition_map_cli_path(root, args.transition_map)
        except FileNotFoundError as e:
            print(e)
            pygame.quit()
            sys.exit(1)
    else:
        pygame.display.set_caption("Crafting - 选择地图")
        transition_map_path = run_transition_map_selection(screen, clock, root)
        if transition_map_path is None:
            pygame.quit()
            sys.exit(0)

    map_label = Path(transition_map_path).stem
    pygame.display.set_caption("Crafting - 练习指导")
    if not run_practice_guidance_screen(
        screen,
        clock,
        rounds_total=rounds_total,
        min_visits=min_visits,
        min_trial_seconds=min_trial_seconds,
        map_label=map_label,
    ):
        pygame.quit()
        sys.exit(0)

    pygame.display.set_caption("Crafting - 练习")

    stone_dirs = collect_stone_asset_dirs(root)
    img_cache = StoneImageCache(stone_dirs)
    bottle_dirs = collect_bottle_asset_dirs(root)
    bottle_cache = BottleImageCache(bottle_dirs)
    if stone_dirs and count_loaded_gems(img_cache) < 9:
        print(
            f"提示: 宝石图仅 {count_loaded_gems(img_cache)}/9，其余用程序绘制。"
        )
    if bottle_dirs and count_loaded_bottles(bottle_cache) < 3:
        print(
            f"提示: 药水瓶图仅 {count_loaded_bottles(bottle_cache)}/3。"
        )

    rules = load_rule_data_with_transition_map(rules_path, transition_map_path)
    trial_list = load_trial_list(trials_path)

    recorder = RLDataRecorder(participant_id=pid, task_type="Crafting_Practice")
    game = GameCrafting(
        recorder=recorder,
        rules=rules,
        trial_data=trial_list,
        practice_mode=True,
    )

    visit_counts: Dict[str, int] = {s: 0 for s in STONE_IDS}
    c0 = game.current_state_id
    if c0 in visit_counts:
        visit_counts[c0] += 1

    session_t0 = time.time()
    phase = "running"
    running = True
    round_index = 1
    step_logs: List[StepLog] = []
    round_summaries: List[Dict[str, Any]] = []
    round_started_at = time.time()
    step_counter = 0

    highlight_p1_until = 0.0
    highlight_p2_until = 0.0
    highlight_p3_until = 0.0
    error_p1_until = 0.0
    error_p2_until = 0.0
    error_p3_until = 0.0

    def _finish_round() -> None:
        nonlocal phase, round_index, visit_counts, round_started_at, step_counter
        explored_rate, mastery_rate, mastered_count = _metrics(visit_counts, min_visits)
        round_summaries.append(
            {
                "round_index": round_index,
                "duration_sec": round(time.time() - round_started_at, 3),
                "steps": step_counter,
                "explore_rate": explored_rate,
                "mastery_rate": mastery_rate,
                "mastered_stones": mastered_count,
                "min_visits_required": min_visits,
                "visit_counts": dict(visit_counts),
            }
        )
        if round_index >= rounds_total:
            phase = "finished"
            return
        round_index += 1
        step_counter = 0
        round_started_at = time.time()
        if not game.start_next_trial():
            phase = "finished"
            return
        visit_counts = {s: 0 for s in STONE_IDS}
        cs = game.current_state_id
        if cs in visit_counts:
            visit_counts[cs] += 1
        phase = "round_transition"

    font_md = _font(18)
    font_sm = _font(16)

    while running:
        now = time.monotonic()
        lit_p1 = now < highlight_p1_until
        lit_p2 = now < highlight_p2_until
        lit_p3 = now < highlight_p3_until
        err_p1 = now < error_p1_until
        err_p2 = now < error_p2_until
        err_p3 = now < error_p3_until

        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        explored_rate, mastery_rate, mastered_count = _metrics(visit_counts, min_visits)
        elapsed_trial_sec = max(0.0, time.time() - round_started_at)
        time_ok = elapsed_trial_sec >= float(min_trial_seconds)
        mastery_ok = mastery_rate >= 1.0

        trial_id = game.current_trial.trial_id if game.current_trial else "-"
        meta1 = (
            f"练习 · 第 {round_index}/{rounds_total} 轮 · Trial {trial_id} · "
            f"探索 {explored_rate:.0%} · 覆盖达标 {mastery_rate:.0%} ({mastered_count}/9) · 规则 {game.map_id}"
        )
        em = int(elapsed_trial_sec) // 60
        es = int(elapsed_trial_sec) % 60
        tm = min_trial_seconds // 60
        ts = min_trial_seconds % 60
        meta2 = (
            f"本轮 {em:02d}:{es:02d} / {tm:02d}:{ts:02d} · "
            f"时间 {'达标' if time_ok else '未达标'} · 覆盖 {'达标' if mastery_ok else '未达标'} · "
            f"每石>={min_visits}次"
        )

        actions = game.get_available_actions()
        op_slot_rect, action_btn_row, target_rect = layout_rects()

        draw_ui(
            screen=screen,
            game=game,
            img_cache=img_cache,
            bottle_cache=bottle_cache,
            op_slot_rect=op_slot_rect,
            action_btn_row=action_btn_row,
            target_rect=target_rect,
            lit_p1=lit_p1,
            lit_p2=lit_p2,
            lit_p3=lit_p3,
            err_p1=err_p1,
            err_p2=err_p2,
            err_p3=err_p3,
            header_title="Crafting 练习（九石阵）",
            meta_line=meta1,
            meta_line2=meta2,
            target_area_mode="practice",
        )

        if phase == "round_transition":
            banner = font_md.render(
                f"第 {round_index - 1} 轮完成  ·  Enter / 空格 开始第 {round_index} 轮",
                True,
                (140, 220, 140),
            )
            screen.blit(banner, banner.get_rect(center=(WINDOW_W // 2, WINDOW_H - 48)))
        elif phase == "finished":
            b1 = font_md.render(
                f"练习完成：共 {rounds_total} 轮均达标",
                True,
                (140, 220, 140),
            )
            screen.blit(b1, b1.get_rect(center=(WINDOW_W // 2, WINDOW_H - 62)))
            b2 = font_sm.render("Esc 退出并保存数据", True, (170, 170, 190))
            screen.blit(b2, b2.get_rect(center=(WINDOW_W // 2, WINDOW_H - 32)))

        pygame.display.flip()

        if phase == "running":
            for event in events:
                if event.type != pygame.KEYDOWN:
                    continue
                if event.key == pygame.K_ESCAPE:
                    running = False
                    break
                if event.key == pygame.K_r:
                    prev = game.current_state_id
                    if game.clear_operation_slot():
                        nxt = game.current_state_id
                        if nxt in visit_counts:
                            visit_counts[nxt] += 1
                        er, mr, _ = _metrics(visit_counts, min_visits)
                        step_counter += 1
                        step_logs.append(
                            StepLog(
                                round_index=round_index,
                                step_index=step_counter,
                                t_sec=round(time.time() - session_t0, 3),
                                from_state=prev,
                                to_state=nxt,
                                key_symbol="R",
                                explore_rate=er,
                                mastery_rate=mr,
                            )
                        )
                        cur_elapsed = max(0.0, time.time() - round_started_at)
                        if mr >= 1.0 and cur_elapsed >= float(min_trial_seconds):
                            _finish_round()
                    continue

                if event.key in ACTION_KEYS:
                    pi = _potion_index_for_action_key(event.key)
                    sym = _action_key_symbol(event.key)
                    action = _find_action_by_key(game, actions, event.key)
                    prev_state = game.current_state_id

                    def _apply_ok(potion_i: int) -> None:
                        nonlocal highlight_p1_until, highlight_p2_until, highlight_p3_until
                        nonlocal error_p1_until, error_p2_until, error_p3_until
                        if potion_i == 1:
                            highlight_p1_until = now + ACTION_BTN_HIGHLIGHT_S
                            error_p1_until = 0.0
                        elif potion_i == 2:
                            highlight_p2_until = now + ACTION_BTN_HIGHLIGHT_S
                            error_p2_until = 0.0
                        else:
                            highlight_p3_until = now + ACTION_BTN_HIGHLIGHT_S
                            error_p3_until = 0.0

                    def _apply_err(potion_i: int) -> None:
                        nonlocal highlight_p1_until, highlight_p2_until, highlight_p3_until
                        nonlocal error_p1_until, error_p2_until, error_p3_until
                        if potion_i == 1:
                            highlight_p1_until = 0.0
                            error_p1_until = now + ACTION_BTN_ERROR_S
                        elif potion_i == 2:
                            highlight_p2_until = 0.0
                            error_p2_until = now + ACTION_BTN_ERROR_S
                        else:
                            highlight_p3_until = 0.0
                            error_p3_until = now + ACTION_BTN_ERROR_S

                    if pi == 1:
                        if action is not None and game.execute_action(action, source_key=sym):
                            _apply_ok(1)
                            nxt = game.current_state_id
                            if nxt in visit_counts:
                                visit_counts[nxt] += 1
                            step_counter += 1
                            er, mr, _ = _metrics(visit_counts, min_visits)
                            step_logs.append(
                                StepLog(
                                    round_index=round_index,
                                    step_index=step_counter,
                                    t_sec=round(time.time() - session_t0, 3),
                                    from_state=prev_state,
                                    to_state=nxt,
                                    key_symbol=sym,
                                    explore_rate=er,
                                    mastery_rate=mr,
                                )
                            )
                            cur_elapsed = max(0.0, time.time() - round_started_at)
                            if mr >= 1.0 and cur_elapsed >= float(min_trial_seconds):
                                _finish_round()
                        else:
                            _apply_err(1)
                            game.log_invalid_keypress(
                                sym,
                                "invalid_no_action"
                                if action is None
                                else "invalid_execute_failed",
                            )
                    elif pi == 2:
                        if action is not None and game.execute_action(action, source_key=sym):
                            _apply_ok(2)
                            nxt = game.current_state_id
                            if nxt in visit_counts:
                                visit_counts[nxt] += 1
                            step_counter += 1
                            er, mr, _ = _metrics(visit_counts, min_visits)
                            step_logs.append(
                                StepLog(
                                    round_index=round_index,
                                    step_index=step_counter,
                                    t_sec=round(time.time() - session_t0, 3),
                                    from_state=prev_state,
                                    to_state=nxt,
                                    key_symbol=sym,
                                    explore_rate=er,
                                    mastery_rate=mr,
                                )
                            )
                            cur_elapsed = max(0.0, time.time() - round_started_at)
                            if mr >= 1.0 and cur_elapsed >= float(min_trial_seconds):
                                _finish_round()
                        else:
                            _apply_err(2)
                            game.log_invalid_keypress(
                                sym,
                                "invalid_no_action"
                                if action is None
                                else "invalid_execute_failed",
                            )
                    elif pi == 3:
                        if action is not None and game.execute_action(action, source_key=sym):
                            _apply_ok(3)
                            nxt = game.current_state_id
                            if nxt in visit_counts:
                                visit_counts[nxt] += 1
                            step_counter += 1
                            er, mr, _ = _metrics(visit_counts, min_visits)
                            step_logs.append(
                                StepLog(
                                    round_index=round_index,
                                    step_index=step_counter,
                                    t_sec=round(time.time() - session_t0, 3),
                                    from_state=prev_state,
                                    to_state=nxt,
                                    key_symbol=sym,
                                    explore_rate=er,
                                    mastery_rate=mr,
                                )
                            )
                            cur_elapsed = max(0.0, time.time() - round_started_at)
                            if mr >= 1.0 and cur_elapsed >= float(min_trial_seconds):
                                _finish_round()
                        else:
                            _apply_err(3)
                            game.log_invalid_keypress(
                                sym,
                                "invalid_no_action"
                                if action is None
                                else "invalid_execute_failed",
                            )

        elif phase == "round_transition":
            for event in events:
                if event.type == pygame.KEYDOWN and event.key in (
                    pygame.K_RETURN,
                    pygame.K_SPACE,
                ):
                    phase = "running"
                    break

        clock.tick(30)

    payload: Dict[str, Any] = {
        "schema": "crafting_practice_v1",
        "participant_id": pid,
        "session_start_iso": datetime.fromtimestamp(session_t0).isoformat(),
        "session_end_iso": datetime.now().isoformat(),
        "duration_sec": round(time.time() - session_t0, 3),
        "transition_map_path": transition_map_path,
        "map_id": game.map_id,
        "rules_path": rules_path,
        "trials_path": trials_path,
        "rounds_total": rounds_total,
        "min_visits": min_visits,
        "min_trial_seconds": min_trial_seconds,
        "round_summaries": round_summaries,
        "steps": [asdict(s) for s in step_logs],
    }
    out = _save_practice_session(practice_raw_dir(root), payload)
    print(f"练习阶段 JSON 已保存: {out}")

    try:
        recorder.save_to_file()
    except Exception:
        pass
    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
