#!/usr/bin/env python3
"""
Navigation6 练习阶段独立入口：学习阶段（拖拽+反馈）→ 测试阶段（无反馈）→ 完成页。
participant_id（环境变量/命令行）、seed；默认地图见 EXPERIMENT_MAPS[0]。
有有效地图 JSON 时按所选条件预生成学习/测试序列（仅在 1–2、3–4… 成对内控制 R/D/C 联合分布与状态链）；选图后若未用 -c 指定，则被试在窗口内用 1–4 选择中性代号 DD/DR/DC/DCR；否则回退为随机打乱。
"""
import argparse
import os
import random
import sys
from datetime import datetime
from pathlib import Path

import pygame

# 确保项目根在 sys.path 中：.../Minecraft8.0/experiments/navigation6/practice_main.py -> .../Minecraft8.0
_this_file = Path(__file__).resolve()
_this_dir = _this_file.parent  # experiments/navigation6
_project_root = _this_file.parents[2]
_project_root_str = str(_project_root)
if _project_root_str not in sys.path:
    sys.path.insert(0, _project_root_str)

from experiments.navigation6.app.experiment.main import (
    EXPERIMENT_MAPS,
    _resolve_map_path,
    build_position_encoding,
)
from experiments.navigation6.app.experiment.game import GameNavigation6
from shared.common.recorder import RLDataRecorder
from experiments.navigation6.app.practice.practice.question_generator import QuestionGenerator
from experiments.navigation6.app.practice.practice.practice_manager import PracticeManager, PracticePhase
from experiments.navigation6.app.practice.practice.practice_ui import PracticeUI
from experiments.navigation6.app.practice.practice.data_recorder import PracticeDataRecorder
from experiments.navigation6.app.practice.practice.pair_sequence import (
    PARTICIPANT_CONDITION_CODE,
    PairCondition,
    build_sequenced_pools,
    parse_pair_condition,
)
from experiments.navigation6.app.practice.practice.transit_practice_modes import (
    TRANSIT_MODE_TO_RDC,
    load_transit_modes_for_map,
)


DEFAULT_MAP_NAME, DEFAULT_MAP_FILE = EXPERIMENT_MAPS[0]
# 全题库大小 = N；学习阶段长度 2N、测试阶段 N（有地图时由 pair_condition 预生成定序序列；无地图时打乱）。
# 若测试阶段总体正确率 < 0.8，则自动重新开始一轮新的学习+测试（有预生成时会重新抽样序列）。
LEARNING_REPETITIONS = 2
MIN_TEST_ACCURACY = 0.8
WINDOW_W = 640
WINDOW_H = 520


def _draw_completion_screen(screen: pygame.Surface, manager: PracticeManager) -> None:
    screen.fill((32, 34, 40))
    try:
        font_lg = pygame.font.SysFont("SimHei", 28)
        font_md = pygame.font.SysFont("SimHei", 20)
    except Exception:
        font_lg = pygame.font.SysFont("arial", 28)
        font_md = pygame.font.SysFont("arial", 20)

    stats = manager.get_statistics()
    w, h = screen.get_size()
    cx, y = w // 2, 72

    title = font_lg.render("练习完成", True, (240, 240, 255))
    tr = title.get_rect(centerx=cx, y=y)
    screen.blit(title, tr)
    y += 52

    card_w = 320
    card_rect = pygame.Rect((w - card_w) // 2, y, card_w, 130)
    pygame.draw.rect(screen, (42, 46, 54), card_rect, border_radius=12)
    pygame.draw.rect(screen, (70, 76, 90), card_rect, 1, border_radius=12)
    inner_y = card_rect.y + 24
    for line in [
        f"学习阶段：{stats['learning_count']} 题，正确率 {stats['learning_accuracy']:.0%}",
        f"测试阶段：{stats['test_count']} 题，正确率 {stats['test_accuracy']:.0%}",
        f"总用时：{stats['practice_duration']:.1f} 秒",
    ]:
        surf = font_md.render(line, True, (210, 214, 230))
        screen.blit(surf, (card_rect.centerx - surf.get_width() // 2, inner_y))
        inner_y += 32
    y = card_rect.bottom + 28

    hint = font_md.render("按 ESC 或关闭窗口退出", True, (130, 135, 150))
    hr = hint.get_rect(centerx=cx, y=y)
    screen.blit(hint, hr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Navigation6 练习阶段（三类公共交通）")
    parser.add_argument("--participant_id", "-p", type=str, default=None, help="被试 ID")
    parser.add_argument("--seed", "-s", type=int, default=None, help="随机种子")
    parser.add_argument("--map", "-m", type=str, default=DEFAULT_MAP_FILE, help=f"地图文件名，默认 {DEFAULT_MAP_FILE}")
    parser.add_argument(
        "--pair-condition",
        "-c",
        type=str,
        default=None,
        help="练习条件：same_heavy|rd_heavy|c_heavy|uniform、1–4 或 dd|dr|dc|dcr；省略则在选图后用 1–4 选择（界面显示 DD/DR/DC/DCR）",
    )
    args = parser.parse_args()

    participant_id = args.participant_id or os.environ.get("NAVIGATION5_PARTICIPANT_ID")
    if not participant_id:
        participant_id = f"anonymous_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    random_seed = args.seed
    session_start_iso = datetime.now().isoformat()

    pygame.init()
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption("Navigation6 - 练习（三类公共交通）")
    clock = pygame.time.Clock()

    # 进入练习前先选择地图：与正式实验保持一致体验
    def select_map() -> tuple[str, str]:
        """
        打开一个简单的地图选择界面，返回 (map_id, map_path)。
        若地图文件不存在，则回退为 Barbell 逻辑地图（不推荐，但保证不崩）。
        """
        import pygame as _pg

        selecting = True
        while selecting:
            screen.fill((32, 34, 40))
            try:
                font_lg = _pg.font.SysFont("SimHei", 26)
                font_md = _pg.font.SysFont("SimHei", 20)
                font_sm = _pg.font.SysFont("SimHei", 18)
            except Exception:
                font_lg = _pg.font.SysFont("arial", 26)
                font_md = _pg.font.SysFont("arial", 20)
                font_sm = _pg.font.SysFont("arial", 18)

            y = 40
            title = font_lg.render("Navigation6 练习 - 请选择练习用地图", True, (220, 220, 255))
            screen.blit(title, (40, y))
            y += 42
            subtitle = font_md.render("按数字键选择（1, 2, 3 ...），选定后练习全程使用该地图。", True, (200, 200, 220))
            screen.blit(subtitle, (40, y))
            y += 32

            for i, (name, filename) in enumerate(EXPERIMENT_MAPS):
                line = font_sm.render(f"{i + 1}. {name}  ({filename})", True, (220, 220, 200))
                screen.blit(line, (60, y))
                y += 24
            y += 16
            hint = font_sm.render("ESC: 退出练习", True, (150, 150, 170))
            screen.blit(hint, (40, y))

            _pg.display.flip()

            for ev in _pg.event.get():
                if ev.type == _pg.QUIT:
                    _pg.quit()
                    sys.exit(0)
                if ev.type == _pg.KEYDOWN:
                    if ev.key == _pg.K_ESCAPE:
                        _pg.quit()
                        sys.exit(0)
                    if _pg.K_1 <= ev.key <= _pg.K_9:
                        idx = ev.key - _pg.K_1
                        if 0 <= idx < len(EXPERIMENT_MAPS):
                            name, filename = EXPERIMENT_MAPS[idx]
                            p = _resolve_map_path(filename)
                            if os.path.exists(p):
                                return os.path.splitext(os.path.basename(filename))[0], os.path.abspath(p)
                            else:
                                # 地图文件缺失时退化为 Barbell（逻辑地图）
                                return "Barbell", ""

            clock.tick(30)

        # 理论上不会走到这里
        return "Barbell", ""

    def select_pair_condition() -> PairCondition:
        """选图后：被试用 1–4 选择中性代号 DD / DR / DC / DCR（不展示实验操纵细节）。"""
        import pygame as _pg

        options: list[tuple[PairCondition, str]] = [
            (PairCondition.SAME_HEAVY, PARTICIPANT_CONDITION_CODE[PairCondition.SAME_HEAVY]),
            (PairCondition.RD_HEAVY, PARTICIPANT_CONDITION_CODE[PairCondition.RD_HEAVY]),
            (PairCondition.C_HEAVY, PARTICIPANT_CONDITION_CODE[PairCondition.C_HEAVY]),
            (PairCondition.UNIFORM, PARTICIPANT_CONDITION_CODE[PairCondition.UNIFORM]),
        ]
        while True:
            screen.fill((32, 34, 40))
            try:
                font_lg = _pg.font.SysFont("SimHei", 24)
                font_md = _pg.font.SysFont("SimHei", 18)
                font_sm = _pg.font.SysFont("SimHei", 17)
            except Exception:
                font_lg = _pg.font.SysFont("arial", 24)
                font_md = _pg.font.SysFont("arial", 18)
                font_sm = _pg.font.SysFont("arial", 17)

            y = 36
            title = font_lg.render("请选择本次练习类型", True, (220, 220, 255))
            screen.blit(title, (36, y))
            y += 38
            sub = font_md.render("请任选一项，按对应数字键开始。", True, (190, 195, 210))
            screen.blit(sub, (36, y))
            y += 34
            for i, (_, code) in enumerate(options):
                surf = font_sm.render(f"{i + 1}    {code}", True, (230, 228, 210))
                screen.blit(surf, (56, y))
                y += 30
            y += 16
            hint = font_sm.render("数字键 1–4 确认 · ESC 退出", True, (140, 145, 160))
            screen.blit(hint, (36, y))

            _pg.display.flip()

            for ev in _pg.event.get():
                if ev.type == _pg.QUIT:
                    _pg.quit()
                    sys.exit(0)
                if ev.type == _pg.KEYDOWN:
                    if ev.key == _pg.K_ESCAPE:
                        _pg.quit()
                        sys.exit(0)
                    if _pg.K_1 <= ev.key <= _pg.K_4:
                        idx = ev.key - _pg.K_1
                        if 0 <= idx < len(options):
                            return options[idx][0]

            clock.tick(30)

    map_id, map_path = select_map()

    if args.pair_condition is not None:
        try:
            pair_condition = parse_pair_condition(args.pair_condition)
            pair_condition_source = "cli"
        except ValueError as e:
            print(e)
            pygame.quit()
            sys.exit(2)
    else:
        pair_condition = select_pair_condition()
        pair_condition_source = "ui"

    qgen = QuestionGenerator(map_path=map_path if map_path else "", map_id=map_id, random_seed=random_seed)
    try:
        full_pool = qgen.get_full_pool()
    except ValueError:
        print("题目池为空，请确保地图文件存在且含可行走格与动作。")
        pygame.quit()
        sys.exit(1)
    if not full_pool:
        print("题目池为空，请确保地图文件存在且含可行走格与动作。")
        pygame.quit()
        sys.exit(1)

    min_questions_learning = len(full_pool) * LEARNING_REPETITIONS
    min_questions_test = len(full_pool)

    rng = random.Random(random_seed if random_seed is not None else int(datetime.now().timestamp()))
    seq_diag: dict = {}
    shuffle_learning_between_cycles = True
    regenerate_pools = None
    learning_pool: list = []
    test_pool: list = []
    use_pair_sequence = bool(map_path and os.path.isfile(map_path))
    if use_pair_sequence:
        try:
            transit_modes = load_transit_modes_for_map(map_path)
            learning_pool, test_pool, seq_diag = build_sequenced_pools(
                full_pool,
                transit_modes,
                min_questions_learning,
                min_questions_test,
                pair_condition,
                rng,
            )
            seq_diag["pair_condition"] = pair_condition.value
            shuffle_learning_between_cycles = False
            regen_round = [0]

            def regenerate_pools():
                regen_round[0] += 1
                r = random.Random(
                    (random_seed if random_seed is not None else 0) + regen_round[0] * 1_000_003
                )
                lp, tp, _ = build_sequenced_pools(
                    full_pool,
                    transit_modes,
                    min_questions_learning,
                    min_questions_test,
                    pair_condition,
                    r,
                )
                return lp, tp

        except Exception as ex:
            print(f"预生成练习序列失败（回退为随机打乱）：{ex}")
            use_pair_sequence = False
            shuffle_learning_between_cycles = True
            regenerate_pools = None

    if not use_pair_sequence:
        learning_pool = []
        for _ in range(LEARNING_REPETITIONS):
            learning_pool.extend(full_pool)
        qgen.shuffle_learning_pool(learning_pool)
        test_pool = list(full_pool)
        seq_diag = {
            "pair_sequence_disabled": True,
            "pair_condition": pair_condition.value,
        }
        shuffle_learning_between_cycles = True
        regenerate_pools = None

    manager = PracticeManager(
        question_generator=qgen,
        learning_pool=learning_pool,
        test_pool=test_pool,
        map_id=map_id,
        min_questions_learning=min_questions_learning,
        min_questions_test=min_questions_test,
        consecutive_correct_learning=0,
        accuracy_threshold_learning=0.0,
        min_test_accuracy=MIN_TEST_ACCURACY,
        reset_on_failed_test=True,
        shuffle_learning_between_cycles=shuffle_learning_between_cycles,
        regenerate_pools=regenerate_pools if use_pair_sequence else None,
    )
    code_to_cell = None
    transit_lines_for_ui = None
    if map_path and os.path.exists(map_path):
        dummy_recorder = RLDataRecorder("Navigation6_Practice_Map", task_type="Navigation6_Practice")
        game = GameNavigation6(
            dummy_recorder,
            map_type=map_id,
            target_entropy=0.5,
            enable_experiment=False,
            custom_map_file=map_path,
        )
        _, code_to_cell, _ = build_position_encoding(game)
        transit_lines_for_ui = []
        modes = list(getattr(game, "transit_modes", []) or [])
        for i, line in enumerate(getattr(game, "subway_lines", [])):
            path = list(line.get("path", []))
            if len(path) < 2:
                continue
            mode = modes[i] if i < len(modes) else "metro"
            transit_lines_for_ui.append(
                {
                    "mode": mode,
                    "path": path,
                    "line_index": i,
                    "segment_curve": list(line.get("segment_curve", [])),
                    "segment_straight": list(line.get("segment_straight", [])),
                }
            )
    practice_ui = PracticeUI(
        screen,
        manager,
        code_to_cell=code_to_cell,
        transit_lines=transit_lines_for_ui,
    )
    data_recorder = PracticeDataRecorder(
        # 新目录约定：navigation6/data/raw/practice（保留旧 practice_data 由分析兼容读取）
        output_dir=os.path.join(str(_this_dir), "data", "raw", "practice"),
        participant_id=participant_id,
    )
    data_recorder.set_metadata(
        random_seed=random_seed,
        map_id=map_id,
        session_start_iso=session_start_iso,
        learning_pool_size=manager.get_learning_pool_size(),
        test_pool_size=manager.get_test_pool_size(),
        phase_transition_criterion=(
            f"learning_min_questions={min_questions_learning}, "
            f"test_min_questions={min_questions_test}, "
            f"test_accuracy_threshold>={MIN_TEST_ACCURACY}, "
            f"reset_on_failed_test=True"
        ),
    )
    meta_extra = {
        "pair_condition": pair_condition.value,
        "participant_condition_code": PARTICIPANT_CONDITION_CODE[pair_condition],
        "pair_condition_source": pair_condition_source,
        "mode_mapping_rdc": dict(TRANSIT_MODE_TO_RDC),
        "sequence_length_learning": min_questions_learning,
        "sequence_length_test": min_questions_test,
        "pair_sequence_enabled": use_pair_sequence,
    }
    if use_pair_sequence:
        meta_extra.update(
            {
                "edge_histogram_learning": seq_diag.get("edge_histogram_learning"),
                "edge_histogram_test": seq_diag.get("edge_histogram_test"),
                "bucket_sizes": seq_diag.get("bucket_sizes"),
                "bucket_warnings": seq_diag.get("bucket_warnings"),
                "learning_assign_warnings": seq_diag.get("learning_assign_warnings"),
                "test_assign_warnings": seq_diag.get("test_assign_warnings"),
                "learning_mode_sequence": seq_diag.get("learning_mode_sequence"),
                "test_mode_sequence": seq_diag.get("test_mode_sequence"),
                "test_mode_sequence_source": seq_diag.get("test_mode_sequence_source"),
                "test_instant_transit_coverage": seq_diag.get("test_instant_transit_coverage"),
            }
        )
    else:
        meta_extra["pair_sequence_note"] = seq_diag
    data_recorder.merge_metadata(meta_extra)

    manager.start_new_question()
    running = True
    last_ticks = pygame.time.get_ticks()

    while running:
        events = pygame.event.get()
        for e in events:
            if e.type == pygame.QUIT:
                running = False
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                running = False

        if not running:
            break

        current_ticks = pygame.time.get_ticks()
        dt = (current_ticks - last_ticks) / 1000.0
        last_ticks = current_ticks

        if manager.is_complete():
            _draw_completion_screen(screen, manager)
            pygame.display.flip()
            continue

        triggered = practice_ui.handle_events(events)
        if triggered and not manager.is_learning_phase():
            practice_ui.clear_for_next_question()
            if not manager.is_complete():
                manager.start_new_question()

        if practice_ui.update(dt):
            practice_ui.clear_for_next_question()
            if not manager.is_complete():
                manager.start_new_question()

        # 兜底：当阶段重置（例如测试不达标回到学习）导致 current_question 被清空时，
        # 主循环必须主动拉起下一题，否则界面会停在“无题可答”的卡住状态。
        if (not manager.is_complete()) and (manager.current_question is None):
            practice_ui.clear_for_next_question()
            manager.start_new_question()

        practice_ui.draw(dt)
        pygame.display.flip()
        clock.tick(30)

    data_recorder.add_records(manager.get_all_records())
    out_path = data_recorder.save_to_file(format="json")
    print(f"练习数据已保存: {out_path}")

    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
