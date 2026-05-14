"""Navigation6 轨迹导出工具。

将新测试流程中的 session 日志导出为与 3/20 前后旧版轨迹更一致的目录+XLSX 结构。

单 session 默认输出：

    data/raw/trajectory/<timestamp>/game_log_Navigation6_User.xlsx

多 session 实验可通过 ``experiment_output_dir`` 将多个 session 收拢到同一实验目录下，
例如：

    data/raw/trajectory/proposal5_navigation_first_20260329_113500/
        session_01_navigation_game_log_Navigation6_User.xlsx
        session_03_navigation_game_log_Navigation6_User.xlsx
        session_05_mixed_game_log_Navigation6_User.xlsx

其中：
- `Sheet1` 保持旧版 RLDataRecorder 风格的核心列；
- 额外追加导航测试所需的补充列，避免丢失 session / trial 信息；
- 同一工作簿额外写入 `trial_summary`、`planned_trials`、`session_metadata` 等 sheet，
  以替代此前 main2/main.py 手写 JSON 的元数据存储方式。
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

try:
    import pandas as pd

    HAS_PANDAS = True
except ImportError:  # pragma: no cover - fallback only used if pandas is unavailable
    pd = None
    HAS_PANDAS = False


LEGACY_BASE_COLUMNS: List[str] = [
    "Participant",
    "Task_Type",
    "Episode_ID",
    "Step_Index",
    "Timestamp",
    "Map_Structure",
    "Current_Room_ID",
    "Grid_X",
    "Grid_Y",
    "Backpack_Content",
    "Backpack_Count",
    "Action_Type",
    "Action_Detail",
    "Action_Valid",
    "Reward",
    "Game_Over",
    "Entropy",
    "Complexity",
    "DualTrial_ID",
    "DualTarget_A",
    "DualTarget_B",
    "DualTarget_Reached_A",
    "DualTarget_Reached_B",
]

NAV_EXTRA_COLUMNS: List[str] = [
    "Phase",
    "Map_ID",
    "From_Node",
    "To_Node",
    "Goal_Node",
    "Optimal_Distance",
    "Reaction_Time_ms",
    "Elapsed_Trial_Time_ms",
    "Latency_To_First_Move_ms",
    "Total_Response_Time_ms",
    "Max_Actions",
    "Pair_ID",
    "Category",
    "Block_Index",
    "Trial_Outcome",
    "Path_Length",
    "Path_Efficiency",
    "Session_Order",
    "Session_Number",
    "Session_Domain",
    "Session_Seed",
]


def _iso_from_timestamp(value: Any) -> str:
    if isinstance(value, (int, float)):
        try:
            return _dt.datetime.fromtimestamp(value).isoformat()
        except Exception:
            return str(value)
    if isinstance(value, _dt.datetime):
        return value.isoformat()
    return "" if value is None else str(value)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (1, "1", "true", "True", "TRUE", "yes", "Yes"):
        return True
    return False


def _cell_from_code(code_to_cell: Optional[Mapping[int, Tuple[int, int]]], code: Any) -> Tuple[int, int]:
    if not code_to_cell:
        return 0, 0
    try:
        cell = code_to_cell.get(int(code))
    except Exception:
        cell = None
    if not cell:
        return 0, 0
    return _safe_int(cell[0]), _safe_int(cell[1])


def _flatten_metadata_rows(session_metadata: Optional[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    if not session_metadata:
        return []
    rows: List[Dict[str, Any]] = []
    for key, value in session_metadata.items():
        if isinstance(value, list):
            rows.append({"key": key, "value": f"<list> len={len(value)}"})
        elif isinstance(value, dict):
            rows.append({"key": key, "value": f"<dict> keys={','.join(map(str, value.keys()))}"})
        else:
            rows.append({"key": key, "value": value})
    return rows


def _planned_trials_rows(
    test_trials: Sequence[Tuple[int, int]],
    session_metadata: Optional[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    nav_trials = list((session_metadata or {}).get("navigation_trials", []) or [])
    if nav_trials:
        for trial in nav_trials:
            rows.append(
                {
                    "trial_index": trial.get("index"),
                    "block_index": trial.get("block_index"),
                    "pair_id": trial.get("pair_id", ""),
                    "category": trial.get("category", ""),
                    "start": trial.get("start", ""),
                    "goal": trial.get("goal", ""),
                    "d_grid": trial.get("d_grid", ""),
                    "d_loop": trial.get("d_loop", ""),
                    "multiplicity": trial.get("multiplicity", trial.get("m", "")),
                }
            )
        return rows

    for idx, (start, goal) in enumerate(test_trials, start=1):
        rows.append({"trial_index": idx, "start": start, "goal": goal})
    return rows


def _trial_summary_lookup(trial_summaries: Sequence[Mapping[str, Any]]) -> Dict[int, Mapping[str, Any]]:
    lookup: Dict[int, Mapping[str, Any]] = {}
    for summary in trial_summaries:
        trial_id = _safe_int(summary.get("trial_id"), 0)
        if trial_id > 0:
            lookup[trial_id] = summary
    return lookup


def _build_step_rows(
    *,
    participant_id: str,
    task_type: str,
    map_id: str,
    map_structure: str,
    steps: Sequence[Mapping[str, Any]],
    test_trials: Sequence[Tuple[int, int]],
    trial_summaries: Sequence[Mapping[str, Any]],
    session_metadata: Optional[Mapping[str, Any]],
    code_to_cell: Optional[Mapping[int, Tuple[int, int]]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    nav_trials = list((session_metadata or {}).get("navigation_trials", []) or [])
    summary_by_trial = _trial_summary_lookup(trial_summaries)

    session_order = (session_metadata or {}).get("order", "")
    session_number = (session_metadata or {}).get("session", "")
    session_domain = (session_metadata or {}).get("domain", "")
    session_seed = (session_metadata or {}).get("seed", "")

    for step_row in steps:
        trial_id = _safe_int(step_row.get("trial_id"), 0)
        goal_node = _safe_int(step_row.get("goal_node"), 0)
        planned = nav_trials[trial_id - 1] if 1 <= trial_id <= len(nav_trials) else {}
        summary = summary_by_trial.get(trial_id, {})

        from_node = _safe_int(step_row.get("from_node"), 0)
        to_node = _safe_int(step_row.get("to_node"), 0)
        gx, gy = _cell_from_code(code_to_cell, from_node)

        reached_goal_this_row = bool(goal_node and to_node and goal_node == to_node)
        is_terminal_row = reached_goal_this_row or str(step_row.get("action", "")) == "trial_cap_reached"

        action_type = step_row.get("action_key") or step_row.get("action") or ""
        action_detail = step_row.get("action")
        if action_detail in (None, ""):
            action_detail = step_row.get("action_extra", "")

        base_record: Dict[str, Any] = {
            "Participant": participant_id,
            "Task_Type": task_type,
            "Episode_ID": trial_id,
            "Step_Index": _safe_int(step_row.get("step"), 0),
            "Timestamp": _iso_from_timestamp(step_row.get("timestamp")),
            "Map_Structure": map_structure,
            "Current_Room_ID": from_node,
            "Grid_X": gx,
            "Grid_Y": gy,
            "Backpack_Content": "",
            "Backpack_Count": 0,
            "Action_Type": action_type,
            "Action_Detail": "" if action_detail is None else str(action_detail),
            "Action_Valid": _coerce_bool(step_row.get("is_valid")),
            "Reward": 1 if reached_goal_this_row else 0,
            "Game_Over": is_terminal_row,
            "Entropy": step_row.get("Entropy", ""),
            "Complexity": step_row.get("Complexity", ""),
            "DualTrial_ID": trial_id,
            "DualTarget_A": goal_node or planned.get("goal", ""),
            "DualTarget_B": "",
            "DualTarget_Reached_A": reached_goal_this_row,
            "DualTarget_Reached_B": "",
            "Phase": step_row.get("phase", ""),
            "Map_ID": map_id,
            "From_Node": from_node,
            "To_Node": to_node,
            "Goal_Node": goal_node,
            "Optimal_Distance": step_row.get("optimal_distance", summary.get("optimal_distance", "")),
            "Reaction_Time_ms": step_row.get("reaction_time_ms", ""),
            "Elapsed_Trial_Time_ms": step_row.get("elapsed_trial_time_ms", ""),
            "Latency_To_First_Move_ms": step_row.get(
                "latency_to_first_move_ms", summary.get("latency_to_first_move_ms", "")
            ),
            "Total_Response_Time_ms": step_row.get(
                "total_response_time_ms", summary.get("total_response_time_ms", "")
            ),
            "Max_Actions": step_row.get("max_actions", ""),
            "Pair_ID": planned.get("pair_id", ""),
            "Category": planned.get("category", ""),
            "Block_Index": planned.get("block_index", ""),
            "Trial_Outcome": summary.get("outcome", ""),
            "Path_Length": summary.get("path_length", ""),
            "Path_Efficiency": summary.get("path_efficiency", ""),
            "Session_Order": session_order,
            "Session_Number": session_number,
            "Session_Domain": session_domain,
            "Session_Seed": session_seed,
        }
        rows.append(base_record)

    return rows


def export_navigation_session_to_legacy_xlsx(
    *,
    data_root: str,
    session_start: _dt.datetime,
    session_end: Optional[_dt.datetime],
    map_id: str,
    map_structure: str,
    steps: Sequence[Mapping[str, Any]],
    test_trials: Sequence[Tuple[int, int]],
    trial_summaries: Optional[Sequence[Mapping[str, Any]]] = None,
    session_metadata: Optional[Mapping[str, Any]] = None,
    code_to_cell: Optional[Mapping[int, Tuple[int, int]]] = None,
    participant_id: str = "Navigation6_User",
    task_type: str = "Navigation6_Test",
    experiment_output_dir: Optional[str] = None,
) -> str:
    """导出为旧版目录结构下的 XLSX 工作簿。"""
    timestamp_str = session_start.strftime("%Y%m%d_%H%M%S")
    if experiment_output_dir:
        session_dir = Path(experiment_output_dir)
    else:
        session_dir = Path(data_root) / timestamp_str
    session_dir.mkdir(parents=True, exist_ok=True)

    trial_summaries = list(trial_summaries or [])
    rows = _build_step_rows(
        participant_id=participant_id,
        task_type=task_type,
        map_id=map_id,
        map_structure=map_structure,
        steps=list(steps),
        test_trials=list(test_trials),
        trial_summaries=trial_summaries,
        session_metadata=session_metadata,
        code_to_cell=code_to_cell,
    )

    ordered_columns = LEGACY_BASE_COLUMNS + NAV_EXTRA_COLUMNS
    session_number = (session_metadata or {}).get("session")
    session_domain = str((session_metadata or {}).get("domain", "")).strip()
    if experiment_output_dir and session_number:
        domain_part = f"_{session_domain}" if session_domain else ""
        filename_base = session_dir / f"session_{int(session_number):02d}{domain_part}_game_log_{participant_id}"
    else:
        filename_base = session_dir / f"game_log_{participant_id}"

    if not HAS_PANDAS:  # pragma: no cover
        import csv

        csv_path = f"{filename_base}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=ordered_columns)
            writer.writeheader()
            writer.writerows(rows)
        return csv_path

    workbook_path = f"{filename_base}.xlsx"
    step_df = pd.DataFrame(rows, columns=ordered_columns)
    trial_summary_df = pd.DataFrame(list(trial_summaries))
    planned_trials_df = pd.DataFrame(_planned_trials_rows(test_trials, session_metadata))
    crafting_df = pd.DataFrame(list((session_metadata or {}).get("crafting_placeholders", []) or []))
    session_info_df = pd.DataFrame(
        [
            {
                "session_start": session_start.isoformat(),
                "session_end": session_end.isoformat() if session_end else "",
                "map_id": map_id,
                "map_structure": map_structure,
                "participant_id": participant_id,
                "task_type": task_type,
                "steps_logged": len(rows),
                "planned_trials": len(test_trials),
            }
        ]
    )
    metadata_df = pd.DataFrame(_flatten_metadata_rows(session_metadata))

    with pd.ExcelWriter(workbook_path) as writer:
        step_df.to_excel(writer, sheet_name="Sheet1", index=False)
        trial_summary_df.to_excel(writer, sheet_name="trial_summary", index=False)
        planned_trials_df.to_excel(writer, sheet_name="planned_trials", index=False)
        crafting_df.to_excel(writer, sheet_name="crafting_placeholders", index=False)
        session_info_df.to_excel(writer, sheet_name="session_info", index=False)
        metadata_df.to_excel(writer, sheet_name="session_metadata", index=False)

    return workbook_path