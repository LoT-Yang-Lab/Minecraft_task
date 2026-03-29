#!/usr/bin/env python3
"""
运行 Navigation6 A* 自动被试（无 UI）：
- pure_astar_agent
- noisy_astar_agent (epsilon-greedy)

用法（项目根目录）：
  python experiments/navigation6/scripts/run_agent_experiment.py --agent pure --map map_1774095558.json
  python experiments/navigation6/scripts/run_agent_experiment.py --agent noisy --epsilon 0.1 --seed 42
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

# 允许从任意工作目录直接运行本脚本
_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parents[3]  # .../Minecraft8.0
_PROJECT_ROOT_STR = str(_PROJECT_ROOT)
if _PROJECT_ROOT_STR not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT_STR)

from shared.common.recorder import RLDataRecorder
from experiments.navigation6.agents.base_agent import AgentObservation, BaseNav6Agent
from experiments.navigation6.agents.noisy_astar_agent import NoisyAStarAgent
from experiments.navigation6.agents.pure_astar_agent import PureAStarAgent
from experiments.navigation6.agents.nav6_env_adapter import (
    build_codebook_from_map_data,
    build_neighbors_for_astar,
    build_position_encoding_for_agent,
    build_transition_graph_from_map_data,
    clear_single_target_in_game,
    execute_action,
    get_available_actions,
    get_current_code,
    load_map_json,
    load_trial_sequence,
    resolve_map_path,
)
from experiments.navigation6.app.experiment.game import GameNavigation6
from experiments.navigation6.app.experiment.main import EXPERIMENT_MAPS
from experiments.navigation6.app.paths import get_nav6_root


def _parse_args() -> argparse.Namespace:
    default_map = EXPERIMENT_MAPS[0][1] if EXPERIMENT_MAPS else "map_nav6_sample.json"
    parser = argparse.ArgumentParser(description="运行 Navigation6 A* 自动被试")
    parser.add_argument("--agent", choices=["pure", "noisy"], default="pure", help="agent 类型")
    parser.add_argument("--map", default=default_map, help="地图文件名（assets/maps 下）")
    parser.add_argument("--seed", type=int, default=20260319, help="随机种子（noisy 用）")
    parser.add_argument("--epsilon", type=float, default=0.1, help="noisy 的 epsilon")
    parser.add_argument("--max-steps-per-trial", type=int, default=300, help="每个 trial 的最大步数保护")
    parser.add_argument("--participant-id", default=None, help="日志 participant_id；默认自动生成")
    return parser.parse_args()


def _make_agent(agent_name: str, neighbors_0idx: List[List[int]], epsilon: float, seed: int) -> BaseNav6Agent:
    pure = PureAStarAgent(neighbors_0idx=neighbors_0idx)
    if agent_name == "pure":
        return pure
    return NoisyAStarAgent(pure_agent=pure, epsilon=epsilon, seed=seed)


def _sync_dual_target_meta(game: GameNavigation6, trial_id: int, target_a: int, target_b: int, reached: Set[int]) -> None:
    game.dual_target_trial_id = trial_id
    game.dual_target_A = target_a
    game.dual_target_B = target_b
    game.dual_target_reached_A = target_a in reached
    game.dual_target_reached_B = target_b in reached


def main() -> int:
    args = _parse_args()

    map_path = resolve_map_path(args.map)
    if not os.path.exists(map_path):
        raise FileNotFoundError(f"地图文件不存在：{map_path}")

    trials = load_trial_sequence(args.map)
    map_data = load_map_json(args.map)
    cell_to_code_map, code_to_cell_map = build_codebook_from_map_data(map_data)
    graph_by_code = build_transition_graph_from_map_data(map_data, cell_to_code_map)
    neighbors_0idx = build_neighbors_for_astar(graph_by_code)
    agent = _make_agent(args.agent, neighbors_0idx, args.epsilon, args.seed)

    participant_id = args.participant_id or f"Navigation6_{args.agent}_agent"
    data_root = os.path.join(get_nav6_root(), "data", "raw", "trajectory")
    recorder = RLDataRecorder(participant_id, task_type="Navigation6", output_root=data_root)
    # 让日志中的 Map_Structure 直接对齐分析端可识别的 map_id（如 map_1773511099）
    map_id_for_log = Path(args.map).stem
    game = GameNavigation6(
        recorder=recorder,
        map_type=map_id_for_log,
        target_entropy=0.5,
        enable_experiment=False,
        custom_map_file=map_path,
    )
    clear_single_target_in_game(game)
    cell_to_code, code_to_cell = build_position_encoding_for_agent(game)

    # 与试次表编码空间一致性检查
    if set(code_to_cell.keys()) != set(code_to_cell_map.keys()):
        raise ValueError("运行时编码与试次表编码空间不一致，请检查地图与编码构建规则。")

    total_steps = 0
    finished_trials = 0
    for idx, (target_a, target_b) in enumerate(trials, start=1):
        reached: Set[int] = set()
        _sync_dual_target_meta(game, idx, target_a, target_b, reached)

        steps_this_trial = 0
        while len(reached) < 2:
            current_code = get_current_code(game, cell_to_code)
            if current_code == target_a:
                reached.add(target_a)
            if current_code == target_b:
                reached.add(target_b)
            _sync_dual_target_meta(game, idx, target_a, target_b, reached)
            if len(reached) >= 2:
                break

            actions = get_available_actions(game, cell_to_code)
            if not actions:
                raise RuntimeError(f"trial#{idx} 无可执行动作，当前位置编码={current_code}")

            obs = AgentObservation(
                current_code=current_code,
                target_a=target_a,
                target_b=target_b,
                reached_targets=set(reached),
            )
            selected = agent.select_action(obs, actions)
            ok = execute_action(game, selected)
            if not ok:
                raise RuntimeError(f"trial#{idx} 动作执行失败：{selected}")

            steps_this_trial += 1
            total_steps += 1
            if steps_this_trial >= args.max_steps_per_trial:
                raise RuntimeError(
                    f"trial#{idx} 超过最大步数 {args.max_steps_per_trial}，请检查 agent 策略或增大阈值。"
                )

        finished_trials += 1

    recorder.save_to_file()
    print(
        f"[OK] agent={args.agent} map={args.map} trials={finished_trials}/{len(trials)} total_steps={total_steps} "
        f"participant_id={participant_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

