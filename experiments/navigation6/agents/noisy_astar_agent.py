from __future__ import annotations

import random
from typing import List

from experiments.navigation6.agents.base_agent import AgentAction, AgentObservation, BaseNav6Agent
from experiments.navigation6.agents.pure_astar_agent import PureAStarAgent


class NoisyAStarAgent(BaseNav6Agent):
    """
    epsilon-greedy 版本：
    - 以 epsilon 概率随机选一个合法动作；
    - 否则按 pure A* 最优动作执行。
    """

    def __init__(self, pure_agent: PureAStarAgent, epsilon: float = 0.1, seed: int = 20260319):
        if epsilon < 0.0 or epsilon > 1.0:
            raise ValueError("epsilon 必须在 [0, 1] 范围内。")
        self.pure_agent = pure_agent
        self.epsilon = float(epsilon)
        self.rng = random.Random(seed)

    def select_action(self, obs: AgentObservation, actions: List[AgentAction]) -> AgentAction:
        if not actions:
            raise ValueError("当前状态无可执行动作。")
        if self.rng.random() < self.epsilon:
            return self.rng.choice(actions)
        return self.pure_agent.select_action(obs, actions)

