"""
Navigation6 练习题目生成：从地图单步模拟构建 (当前位置编码, 动作) -> 执行后位置编码；
仅公交/地铁/轻轨到站动作。
"""
import os
import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any

# 池项：(question_id, current_code, action_label, action_key, extra, next_code)
PoolItem = Tuple[str, int, str, str, Optional[str], int]


def _make_dummy_recorder():
    from shared.common.recorder import RLDataRecorder
    return RLDataRecorder("Navigation6_Practice", task_type="Navigation6_Practice")


def build_full_pool(map_path: str, map_id: str) -> List[PoolItem]:
    """
    加载地图，构建全池：对每个可行走格、每个可执行动作，执行一步并记录 (current_code, action_*, next_code)。
    使用 GameNavigation6 与八方向动作。
    """
    from experiments.navigation6.app.experiment.game import GameNavigation6
    from experiments.navigation6.app.experiment.main import (
        build_position_encoding,
        get_available_actions,
        execute_action,
    )

    recorder = _make_dummy_recorder()
    game = GameNavigation6(
        recorder,
        map_type=map_id,
        target_entropy=0.5,
        enable_experiment=False,
        custom_map_file=map_path,
    )
    cell_to_code, code_to_cell, _ = build_position_encoding(game)
    n_codes = len(code_to_cell)
    pool: List[PoolItem] = []

    for code in range(1, n_codes + 1):
        cell = code_to_cell.get(code)
        if not cell:
            continue
        gx, gy = cell
        game_ref = GameNavigation6(
            _make_dummy_recorder(),
            map_type=map_id,
            target_entropy=0.5,
            enable_experiment=False,
            custom_map_file=map_path,
        )
        game_ref.player_x, game_ref.player_y = gx, gy
        game_ref.on_subway = False
        game_ref.subway_train_id = -1
        actions = get_available_actions(game_ref)
        for action in actions:
            label, action_key, extra = action
            game_one = GameNavigation6(
                _make_dummy_recorder(),
                map_type=map_id,
                target_entropy=0.5,
                enable_experiment=False,
                custom_map_file=map_path,
            )
            game_one.player_x, game_one.player_y = gx, gy
            game_one.on_subway = False
            game_one.subway_train_id = -1
            ok = execute_action(game_one, action)
            if not ok:
                continue
            next_pos = (game_one.player_x, game_one.player_y)
            next_code = cell_to_code.get(next_pos)
            if next_code is None:
                continue
            extra_str = "" if extra is None else str(extra)
            qid = f"{map_id}|{code}|{action_key}|{extra_str}|{next_code}"
            pool.append((qid, code, label, action_key, extra, next_code))

    return pool


def split_pool(
    full_pool: List[PoolItem],
    learning_size: int,
    test_size: int,
    rng: random.Random,
) -> Tuple[List[PoolItem], List[PoolItem]]:
    """将全池随机划分为学习池与测试池，无交集。"""
    n = len(full_pool)
    if n == 0:
        return [], []
    indices = list(range(n))
    rng.shuffle(indices)
    n_test = min(test_size, n)
    n_learning = min(learning_size, n - n_test)
    if n_learning < 1 and n > n_test:
        n_learning = 1
        n_test = min(test_size, n - 1)
    test_pool = [full_pool[indices[i]] for i in range(n_test)]
    learning_pool = [full_pool[indices[n_test + i]] for i in range(n_learning)]
    return learning_pool, test_pool


@dataclass
class PracticeQuestion:
    """单道练习题：当前编码 + 动作 -> 执行后编码，及候选选项（编码列表）。"""
    question_id: str
    current_code: int
    action_label: str
    action_key: str
    correct_next_code: int
    options: List[int] = field(default_factory=list)


def _make_options(
    correct_next_code: int,
    num_codes: int,
    num_options: int,
    rng: random.Random,
) -> List[int]:
    others = [c for c in range(1, num_codes + 1) if c != correct_next_code]
    n_distract = min(num_options - 1, len(others))
    distractors = rng.sample(others, n_distract)
    options = [correct_next_code] + distractors
    rng.shuffle(options)
    return options


def build_question_from_item(
    item: PoolItem,
    num_codes: int,
    rng: random.Random,
    num_options: int = 5,
) -> PracticeQuestion:
    """从池项生成 PracticeQuestion。"""
    qid, current_code, action_label, action_key, extra, next_code = item
    options = _make_options(next_code, num_codes, num_options, rng)
    return PracticeQuestion(
        question_id=qid,
        current_code=current_code,
        action_label=action_label,
        action_key=action_key,
        correct_next_code=next_code,
        options=options,
    )


class QuestionGenerator:
    """根据地图路径与 map_id 构建全池、划分学习/测试池，并从池项生成题目。"""

    def __init__(
        self,
        map_path: str,
        map_id: str,
        random_seed: Optional[int] = None,
    ):
        self.map_path = map_path
        self.map_id = map_id
        self._rng = random.Random(random_seed)
        self._full_pool = build_full_pool(map_path, map_id)
        self._num_codes = self._count_codes()
        if not self._full_pool:
            raise ValueError(f"题目池为空 map_path={map_path}")

    def _count_codes(self) -> int:
        if not self._full_pool:
            return 0
        return max(max(item[1], item[5]) for item in self._full_pool)

    def get_full_pool(self) -> List[PoolItem]:
        return self._full_pool.copy()

    def split_pool(
        self,
        learning_size: int,
        test_size: int,
    ) -> Tuple[List[PoolItem], List[PoolItem]]:
        return split_pool(
            self._full_pool,
            learning_size,
            test_size,
            self._rng,
        )

    def build_question_from_item(
        self,
        item: PoolItem,
        num_options: int = 5,
    ) -> PracticeQuestion:
        return build_question_from_item(
            item,
            self._num_codes,
            self._rng,
            num_options,
        )

    def shuffle_learning_pool(self, learning_pool: List[PoolItem]) -> None:
        self._rng.shuffle(learning_pool)
