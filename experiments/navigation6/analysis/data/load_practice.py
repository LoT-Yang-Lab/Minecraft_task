"""
加载 practice_data 下的 JSON 文件，输出统一记录表。
每条记录包含 participant_id, map_id, phase, trial_index, current_code, options, participant_choice, correct, rt_ms 等。
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional


def load_practice_json(filepath: str) -> List[Dict[str, Any]]:
    """
    加载单份练习 JSON，返回扁平化的记录列表。
    每条记录包含: participant_id, map_id, phase, trial_index, current_code, action_label,
    correct_next_code, participant_choice, correct, rt_ms, attempt_count, options, first_response_ms, timestamp 等。
    """
    path = Path(filepath)
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    records = data.get("records", [])
    participant_id = data.get("participant_id", "")
    map_id = data.get("map_id", "")
    out: List[Dict[str, Any]] = []
    for r in records:
        row = {
            "participant_id": participant_id,
            "map_id": map_id,
            "phase": r.get("phase", ""),
            "trial_index": r.get("trial_index", 0),
            "question_id": r.get("question_id", ""),
            "current_code": r.get("current_code", 0),
            "action_label": r.get("action_label", ""),
            "correct_next_code": r.get("correct_next_code", 0),
            "participant_choice": r.get("participant_choice", 0),
            "correct": r.get("correct", False),
            "rt_ms": r.get("rt_ms", 0.0),
            "attempt_count": r.get("attempt_count", 0),
            "options": r.get("options", []),
            "first_response_ms": r.get("first_response_ms"),
            "timestamp": r.get("timestamp", 0.0),
        }
        out.append(row)
    return out


def load_practice_dir(
    practice_dir: str,
    pattern: str = "*.json",
) -> List[Dict[str, Any]]:
    """
    加载目录下所有匹配的练习 JSON，合并为一张大表。
    """
    path = Path(practice_dir)
    if not path.is_dir():
        # 兼容旧目录：experiments/navigation6/practice_data
        legacy = Path(__file__).resolve().parents[2] / "practice_data"
        if legacy.is_dir():
            path = legacy
        else:
            return []
    all_records: List[Dict[str, Any]] = []
    for f in sorted(path.glob(pattern)):
        if f.name.startswith("."):
            continue
        all_records.extend(load_practice_json(str(f)))
    return all_records
