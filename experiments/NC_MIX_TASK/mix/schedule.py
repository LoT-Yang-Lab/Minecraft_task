from __future__ import annotations

from typing import Any, Dict, List

from crafting.src.proposal5_trial_schedule import build_session_schedule, save_schedule


def navigation_trials_in_runtime_order(session: Dict[str, Any]) -> List[Dict[str, Any]]:
    combined = session.get("combined_order") or []
    if combined:
        return [item["trial"] for item in combined if item["type"] == "navigation"]
    return list(session.get("navigation_trials", []))


def crafting_trials_in_runtime_order(session: Dict[str, Any]) -> List[Dict[str, Any]]:
    combined = session.get("combined_order") or []
    if combined:
        return [item["trial"] for item in combined if item["type"] == "crafting"]
    return list(session.get("crafting_trials", []))


__all__ = [
    "build_session_schedule",
    "save_schedule",
    "navigation_trials_in_runtime_order",
    "crafting_trials_in_runtime_order",
]
