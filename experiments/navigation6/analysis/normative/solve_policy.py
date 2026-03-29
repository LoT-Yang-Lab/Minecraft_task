"""
调用参考项目 QMDPPolicy，对给定 InternalModel 求解，导出每状态最优动作（即推荐下一站编码 1..N）。
"""
import os
import sys
from typing import Any, Dict, Optional

# 项目根
_this_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.normpath(os.path.join(_this_dir, "..", "..", "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def solve_qmdp_for_map(
    internal_model: Any,
    max_iterations: int = 200,
    tolerance: float = 1e-6,
) -> Any:
    """
    对 InternalModel 运行 QMDP 值迭代，返回 QMDPPolicy 实例（含 Q, V）。
    """
    from pgm_toolkit.dynamical_models.pomdp.agent.policy import QMDPPolicy

    policy = QMDPPolicy(
        internal_model,
        max_iterations=max_iterations,
        tolerance=tolerance,
        auto_solve=True,
    )
    return policy


def get_optimal_action(policy: Any, state_0indexed: int) -> int:
    """
    在完全可观测下，状态 state_0indexed (0..N-1) 的最优动作为「下一状态索引」。
    返回 1-indexed 的推荐下一站编码，便于与练习 participant_choice 对比。
    """
    from pgm_toolkit.dynamical_models.pomdp.agent.belief import point_belief

    n = policy.model.num_states
    belief = point_belief(n, state_0indexed)
    a = policy.get_action(belief)
    return int(a) + 1  # 0-indexed action = next state index -> 1-indexed code


def get_optimal_next_dict(policy: Any) -> Dict[int, int]:
    """返回 state (1-indexed) -> 推荐下一站 (1-indexed)，供 compare_practice_to_policy 使用。"""
    n = policy.model.num_states
    return {s + 1: get_optimal_action(policy, s) for s in range(n)}


def export_policy_to_dict(policy: Any) -> Dict[str, Any]:
    """导出 Q, V 及每状态推荐下一站 (1-indexed)。"""
    Q = getattr(policy, "Q", None)
    V = getattr(policy, "V", None)
    if Q is None:
        return {}
    n = policy.model.num_states
    optimal_next = [get_optimal_action(policy, s) for s in range(n)]
    return {
        "Q": Q.tolist() if hasattr(Q, "tolist") else Q,
        "V": V.tolist() if V is not None and hasattr(V, "tolist") else (V.tolist() if V is not None else None),
        "optimal_next_code_by_state": optimal_next,  # state 0..n-1 -> 推荐下一站 1..n
        "num_states": n,
    }
