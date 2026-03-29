from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from experiments.navigation6.agents.base_agent import AgentAction, AgentObservation, BaseNav6Agent
from experiments.navigation6.analysis.normative.solve_astar import astar_path


class PureAStarAgent(BaseNav6Agent):
    """
    纯 A* agent：
    - 在当前未完成目标中选择路径代价最小的目标；
    - 执行该目标最短路径的第一步动作。
    """

    def __init__(self, neighbors_0idx: Sequence[Sequence[int]]):
        self.neighbors = neighbors_0idx

    def _path_cost_and_next(self, current_code: int, target_code: int) -> Tuple[float, Optional[int]]:
        res = astar_path(
            start_idx=current_code - 1,
            goal_idx=target_code - 1,
            neighbors=self.neighbors,
            h=None,  # 无启发函数时退化为 Dijkstra/BFS，仍为最短路
        )
        if not res:
            return float("inf"), None
        if len(res.path) < 2:
            return 0.0, current_code
        return float(res.cost), res.path[1] + 1

    def select_action(self, obs: AgentObservation, actions: List[AgentAction]) -> AgentAction:
        if not actions:
            raise ValueError("当前状态无可执行动作。")

        remaining = obs.remaining_targets
        # 若两个目标都已达成，runner 不应再调此函数；保底返回第一个动作。
        if not remaining:
            return actions[0]

        # 选最近目标（平局按编码稳定排序）
        target_choices = []
        for t in sorted(remaining):
            cost, next_code = self._path_cost_and_next(obs.current_code, t)
            target_choices.append((cost, t, next_code))
        target_choices.sort(key=lambda x: (x[0], x[1]))
        _best_cost, _best_target, best_next_code = target_choices[0]

        if best_next_code is not None:
            for action in actions:
                if action.next_code == best_next_code:
                    return action

        # 兜底：若理论下一步未在当前动作集中，选使“到最近目标路径代价”最小的动作。
        fallback_scored = []
        for action in actions:
            action_best_cost = float("inf")
            for t in remaining:
                c, _ = self._path_cost_and_next(action.next_code, t)
                action_best_cost = min(action_best_cost, c)
            fallback_scored.append((action_best_cost, action.next_code, action))
        fallback_scored.sort(key=lambda x: (x[0], x[1]))
        return fallback_scored[0][2]

