"""
从 cogmap_nav6 输出构建 POMDP InternalModel。
状态 0..N-1 对应位置编码 1..N；动作为「下一状态索引」（即 action a = 前往状态 a），
仅当邻接矩阵有边时转移有效，否则停留；完全可观测 O(obs|s',a)=1 iff obs==s'。
"""
import os
import sys
from typing import Any, Dict, Optional, Tuple

import numpy as np

# 项目根与参考项目（pgm-toolkit）
_this_dir = os.path.dirname(os.path.abspath(__file__))
_nav5_root = os.path.normpath(os.path.join(_this_dir, "..", ".."))
_project_root = os.path.normpath(os.path.join(_nav5_root, "..", ".."))
_ref_src = os.path.join(_project_root, "参考代码", "策略提取参考项目", "pgm-toolkit-main", "src")
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
if os.path.isdir(_ref_src) and _ref_src not in sys.path:
    sys.path.insert(0, _ref_src)


def build_internal_model_from_cogmap(
    cogmap_result: Dict[str, Any],
    step_reward: float = -1.0,
    goal_reward: float = 10.0,
    action_cost: Optional[np.ndarray] = None,
    discount_factor: float = 0.95,
    slip_prob: float = 0.0,
):
    """
    从 compute_nav6_cogmap 的返回结果构建 InternalModel。

    状态与动作：状态 i (0-indexed) 对应位置编码 i+1。动作为「下一状态索引」a：
    - 若 adj[s,a]==1 则 T(s,a,a)=1（或加入滑移后概率分配）；
    - 若 adj[s,a]==0 则 T(s,a,s)=1（停留）。
    观测：完全可观测，O(s', a, o) = 1 iff o == s'。
    奖励：每步 step_reward，到达 target 状态得 goal_reward。

    Returns:
        (InternalModel, action_to_next_state_map)
        action_to_next_state_map: 在状态 s 下，action_index -> next_state (0-indexed)；
            即 action_index 就是 next_state，用于与行为数据中的 participant_choice (1-indexed) 对齐时：optimal_next = policy_action + 1。
    """
    from pgm_toolkit.dynamical_models.pomdp.model.internal_model import InternalModel

    N = int(cogmap_result["N"])
    adj = np.asarray(cogmap_result["adj"], dtype=np.float64)
    target_code = cogmap_result.get("target_code")
    target_idx = (int(target_code) - 1) if target_code and target_code >= 1 else None

    num_states = N
    num_actions = N  # action a = go to state a
    num_observations = N

    # T[s, a, s']: 从 s 执行 a（去状态 a）到 s'
    T = np.zeros((num_states, num_actions, num_states))
    for s in range(num_states):
        for a in range(num_actions):
            if adj[s, a] > 0:
                if slip_prob <= 0:
                    T[s, a, a] = 1.0
                else:
                    T[s, a, a] = 1.0 - slip_prob
                    T[s, a, s] = slip_prob
            else:
                T[s, a, s] = 1.0
    # 归一化
    T = T / T.sum(axis=2, keepdims=True)

    # O[s', a, o]: 完全可观测，观测 o = s'
    O = np.zeros((num_states, num_actions, num_observations))
    for s in range(num_states):
        for a in range(num_actions):
            O[s, a, s] = 1.0

    # R_ext[s, a]: 步代价 + 到达目标奖励
    R_ext = np.full((num_states, num_actions), step_reward, dtype=np.float64)
    if target_idx is not None:
        for s in range(num_states):
            if adj[s, target_idx] > 0:
                R_ext[s, target_idx] = goal_reward
    if action_cost is None:
        action_cost = np.zeros(num_actions)

    model = InternalModel(
        num_states=num_states,
        num_actions=num_actions,
        num_observations=num_observations,
        transition_matrix=T,
        observation_matrix=O,
        external_reward_matrix=R_ext,
        action_cost=action_cost,
        discount_factor=discount_factor,
    )
    # action_index 即 next_state (0-indexed)；行为数据用 1-indexed code，所以 optimal_next_code = action_index + 1
    return model, None
