"""
加载 rl_data 下的轨迹 CSV/Excel，转为 (participant_id, map_id, episode, step, s, a, s') 序列。
s, s' 为位置编码 1..N；a 为动作标签字符串（与练习 action_label 一致）或保留原始 Action_Type/Action_Detail。
"""
import csv
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

# 项目根与 navigation6 根（与 to_position_code 一致）
_analysis_dir = os.path.dirname(os.path.abspath(__file__))
_nav5_root = os.path.normpath(os.path.join(_analysis_dir, "..", ".."))
_project_root = os.path.normpath(os.path.join(_nav5_root, "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 主程序 EXPERIMENT_MAPS 中 (显示名, 文件名) 的映射，用于 Map_Structure -> map_id
DEFAULT_MAP_STRUCTURE_TO_ID = {
    "地图1774095558": "map_1774095558",
    "Barbell": "Barbell",
}


def _read_trajectory_table(filepath: str) -> List[Dict[str, Any]]:
    """读单文件为行字典列表。支持 csv 与 xlsx。"""
    path = Path(filepath)
    if not path.exists():
        return []
    if HAS_PANDAS and path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path)
        return df.to_dict("records")
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def load_trajectory_csv(
    filepath: str,
    map_structure_to_id: Optional[Dict[str, str]] = None,
    maps_dir: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    加载单份轨迹 CSV/Excel，输出 (participant_id, map_id, episode, step, s, a, s') 行列表。
    s 为当前步位置编码，s' 为下一步位置编码（由下一行 Grid 得到）；a 为 action_label 字符串（Action_Type + Action_Detail 组合）。
    """
    from .to_position_code import get_position_encoder_cached

    rows = _read_trajectory_table(filepath)
    if not rows:
        return []

    map_structure_to_id = map_structure_to_id or DEFAULT_MAP_STRUCTURE_TO_ID
    get_encoder = get_position_encoder_cached(maps_dir=maps_dir)

    out: List[Dict[str, Any]] = []
    for i, r in enumerate(rows):
        participant_id = r.get("Participant", "")
        map_structure = r.get("Map_Structure", "")
        map_id = map_structure_to_id.get(map_structure, map_structure)
        if map_id.endswith(".json"):
            map_id = map_id.replace(".json", "")
        try:
            encoder = get_encoder(map_id)
        except Exception:
            continue
        try:
            gx = int(r.get("Grid_X", 0))
            gy = int(r.get("Grid_Y", 0))
        except (TypeError, ValueError):
            continue
        s = encoder(gx, gy)
        if s == 0:
            continue
        episode = r.get("Episode_ID", 0)
        step = r.get("Step_Index", 0)
        action_type = r.get("Action_Type", "")
        action_detail = str(r.get("Action_Detail", ""))
        action_label = f"{action_type}|{action_detail}".strip("|")

        s_next: int = 0
        if i + 1 < len(rows) and rows[i + 1].get("Episode_ID") == episode:
            rn = rows[i + 1]
            try:
                gx_next = int(rn.get("Grid_X", 0))
                gy_next = int(rn.get("Grid_Y", 0))
                s_next = encoder(gx_next, gy_next)
            except (TypeError, ValueError):
                pass
        out.append({
            "participant_id": participant_id,
            "map_id": map_id,
            "episode": episode,
            "step": step,
            "s": s,
            "a": action_label,
            "s_next": s_next,
            "action_type": action_type,
            "action_detail": action_detail,
        })
    return out


def load_trajectory_dir(
    rl_data_root: str,
    map_structure_to_id: Optional[Dict[str, str]] = None,
    maps_dir: Optional[str] = None,
    pattern: str = "game_log_*.csv",
) -> List[Dict[str, Any]]:
    """
    遍历 rl_data_root 下所有子目录中的 game_log_*.csv（及同名的 .xlsx），合并轨迹表。
    """
    root = Path(rl_data_root)
    if not root.is_dir():
        # 兼容旧默认：项目根 rl_data/
        legacy = Path(_project_root) / "rl_data"
        if legacy.is_dir():
            root = legacy
        else:
            return []
    all_rows: List[Dict[str, Any]] = []
    for subdir in root.iterdir():
        if not subdir.is_dir():
            continue
        for f in subdir.glob(pattern):
            all_rows.extend(
                load_trajectory_csv(str(f), map_structure_to_id=map_structure_to_id, maps_dir=maps_dir)
            )
        if not all_rows and HAS_PANDAS:
            for f in subdir.glob("game_log_*.xlsx"):
                all_rows.extend(
                    load_trajectory_csv(str(f), map_structure_to_id=map_structure_to_id, maps_dir=maps_dir)
                )
    return all_rows
