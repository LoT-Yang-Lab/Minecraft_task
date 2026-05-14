"""NC_MIX_TASK：试次进度统一文案（Session / trial / 领域）。"""

from __future__ import annotations

from typing import Optional


def format_session_trial_line(
    *,
    session_label: Optional[str],
    trial_n: int,
    trial_n_total: int,
    domain_zh: str,
) -> str:
    """
    统一格式：「Session X - trial n/N - 导航|合成」；
    无 session 时省略第一段：「trial n/N - 导航|合成」。
    """
    core = f"trial {trial_n}/{trial_n_total} - {domain_zh}"
    if session_label:
        return f"{session_label} - {core}"
    return core
