"""
混合效应一致率分析（路线B）：
- 从轨迹和规范策略生成长表（participant_id, map_id, baseline, match）
- 可按被试×地图聚合
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp
from typing import Any, Dict, Iterable, List, Optional, Tuple


BaselineName = str  # "qmdp" 或 "astar"


@dataclass(frozen=True)
class LongRow:
    participant_id: str
    map_id: str
    baseline: BaselineName
    match: int  # 0/1


@dataclass(frozen=True)
class AggRow:
    participant_id: str
    map_id: str
    baseline: BaselineName
    n_steps: int
    n_match: int

    @property
    def rate(self) -> float:
        return (self.n_match / self.n_steps) if self.n_steps else 0.0


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def build_consistency_long_table(
    trajectory_rows: List[Dict[str, Any]],
    optimal_qmdp: Optional[Dict[int, int]] = None,
    optimal_astar: Optional[Dict[int, int]] = None,
    *,
    participant_key: str = "participant_id",
    map_key: str = "map_id",
    state_key: str = "s",
    next_key: str = "s_next",
) -> List[LongRow]:
    """
    从轨迹与两种 baseline 的最优策略构建长表：
    每个实际步 (s -> s_next) 对应最多两行（QMDP / A*），字段：
      - participant_id, map_id
      - baseline: "qmdp" 或 "astar"
      - match: 0/1 是否与该 baseline 的 optimal_next 一致
    若某 baseline 为 None，则忽略该 baseline。
    """
    out: List[LongRow] = []
    use_q = optimal_qmdp is not None
    use_a = optimal_astar is not None
    if not (use_q or use_a):
        return out

    for r in trajectory_rows:
        pid = str(r.get(participant_key, "") or "")
        mid = str(r.get(map_key, "") or "")
        if not pid or not mid:
            continue
        s = _safe_int(r.get(state_key, 0))
        s_next = _safe_int(r.get(next_key, 0))
        if s <= 0:
            continue
        if use_q:
            opt = optimal_qmdp.get(s)
            m = 1 if (opt is not None and s_next == opt) else 0
            out.append(LongRow(participant_id=pid, map_id=mid, baseline="qmdp", match=m))
        if use_a:
            opt = optimal_astar.get(s)
            m = 1 if (opt is not None and s_next == opt) else 0
            out.append(LongRow(participant_id=pid, map_id=mid, baseline="astar", match=m))
    return out


def aggregate_by_participant_map(
    long_rows: Iterable[LongRow],
) -> List[AggRow]:
    """
    将长表聚合到 (participant_id, map_id, baseline) 层级：
      - n_steps: 步数
      - n_match: 一致步数
    用于被试×地图层面的分析或回退 logistic 回归。
    """
    tmp: Dict[Tuple[str, str, BaselineName], Tuple[int, int]] = {}
    for r in long_rows:
        key = (r.participant_id, r.map_id, r.baseline)
        total, match = tmp.get(key, (0, 0))
        total += 1
        match += int(r.match)
        tmp[key] = (total, match)
    out: List[AggRow] = []
    for (pid, mid, base), (n_steps, n_match) in tmp.items():
        out.append(AggRow(participant_id=pid, map_id=mid, baseline=base, n_steps=n_steps, n_match=n_match))
    return out


@dataclass(frozen=True)
class EffectSummary:
    coef: float
    se: float
    z: Optional[float]
    p: Optional[float]
    ci_low: Optional[float]
    ci_high: Optional[float]
    or_value: Optional[float]
    or_ci_low: Optional[float]
    or_ci_high: Optional[float]


@dataclass(frozen=True)
class MixedModelResult:
    enabled: bool
    model: str
    baseline_name: str
    warning: Optional[str]
    fixed_effects: Dict[str, EffectSummary]


def _exp_or_none(x: Optional[float]) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(exp(x))
    except Exception:
        return None


def fit_mixed_logit(
    long_rows: List[LongRow],
    *,
    min_participants: int = 3,
    min_steps: int = 20,
) -> MixedModelResult:
    """
    高层接口：在给定长表上拟合 baseline（一元）效应：
      - 优先尝试 statsmodels 的 GLM（logit）+ cluster-robust（按 participant 聚类）
        （当前实现使用被试×地图聚合表 + 权重作为一个简化版；如未来需要可切换到真正的 GLMM）。
      - 若样本太少或没有 statsmodels，则返回 enabled=False 并给出 warning。
    假设 baseline 只有 "qmdp" 与 "astar" 两类，其中 "qmdp" 为参考水平。
    """
    # 基本检查
    if not long_rows:
        return MixedModelResult(
            enabled=False,
            model="none",
            baseline_name="baseline[T.astar]",
            warning="no_data",
            fixed_effects={},
        )
    # 统计被试与总步数
    participants = {r.participant_id for r in long_rows}
    total_steps = len(long_rows)
    if len(participants) < min_participants or total_steps < min_steps:
        return MixedModelResult(
            enabled=False,
            model="none",
            baseline_name="baseline[T.astar]",
            warning="too_few_clusters_or_steps",
            fixed_effects={},
        )

    try:
        import pandas as pd  # type: ignore
        import statsmodels.api as sm  # type: ignore
    except Exception:
        return MixedModelResult(
            enabled=False,
            model="none",
            baseline_name="baseline[T.astar]",
            warning="statsmodels_or_pandas_not_available",
            fixed_effects={},
        )

    # 聚合到被试×地图层（每单元一个观测，使用 freq_weights）
    agg_rows = aggregate_by_participant_map(long_rows)
    if not agg_rows:
        return MixedModelResult(
            enabled=False,
            model="none",
            baseline_name="baseline[T.astar]",
            warning="no_agg_data",
            fixed_effects={},
        )

    data = {
        "participant_id": [r.participant_id for r in agg_rows],
        "map_id": [r.map_id for r in agg_rows],
        "baseline": [r.baseline for r in agg_rows],
        "n_steps": [r.n_steps for r in agg_rows],
        "n_match": [r.n_match for r in agg_rows],
    }
    df = pd.DataFrame(data)
    # 响应为成功率，用权重表示步数
    df["y"] = df["n_match"] / df["n_steps"]
    df["baseline_astar"] = (df["baseline"] == "astar").astype(float)

    # 只保留两类 baseline 的单元
    df = df[df["baseline"].isin(["qmdp", "astar"])]
    if df.empty or df["baseline"].nunique() < 2:
        return MixedModelResult(
            enabled=False,
            model="none",
            baseline_name="baseline[T.astar]",
            warning="single_baseline_only",
            fixed_effects={},
        )

    try:
        # 使用带权重的 logit 回归，并按 participant 聚类计算稳健标准误
        model = sm.GLM(
            df["y"],
            sm.add_constant(df[["baseline_astar"]]),
            family=sm.families.Binomial(),
            freq_weights=df["n_steps"],
        )
        result = model.fit(cov_type="cluster", cov_kwds={"groups": df["participant_id"]})
    except Exception as e:  # pragma: no cover - 防御性
        return MixedModelResult(
            enabled=False,
            model="glm_failed",
            baseline_name="baseline[T.astar]",
            warning=f"glm_fit_failed: {e}",
            fixed_effects={},
        )

    # 提取固定效应
    params = result.params
    bse = result.bse
    conf_int = result.conf_int(alpha=0.05)
    pvalues = result.pvalues

    fixed: Dict[str, EffectSummary] = {}
    for name in params.index:
        coef = float(params[name])
        se = float(bse.get(name, float("nan")))
        p = float(pvalues.get(name, float("nan")))
        ci_low = float(conf_int.loc[name, 0]) if name in conf_int.index else None
        ci_high = float(conf_int.loc[name, 1]) if name in conf_int.index else None
        z_val: Optional[float]
        try:
            z_val = coef / se if se not in (0.0, float("nan")) else None
        except Exception:
            z_val = None
        or_val = _exp_or_none(coef)
        or_low = _exp_or_none(ci_low)
        or_high = _exp_or_none(ci_high)
        fixed[name] = EffectSummary(
            coef=coef,
            se=se,
            z=z_val,
            p=p,
            ci_low=ci_low,
            ci_high=ci_high,
            or_value=or_val,
            or_ci_low=or_low,
            or_ci_high=or_high,
        )

    return MixedModelResult(
        enabled=True,
        model="logit_cluster_robust",
        baseline_name="baseline_astar",
        warning=None,
        fixed_effects=fixed,
    )

