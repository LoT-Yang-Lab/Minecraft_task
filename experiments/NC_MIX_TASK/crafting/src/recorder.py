"""
Crafting 内嵌数据记录器。
"""

import csv
import datetime
import os
from pathlib import Path

try:
    import pandas as pd

    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


class RLDataRecorder:
    """强化学习数据记录器"""

    def __init__(
        self,
        participant_id="RL_Agent_01",
        task_type="Unknown",
        output_root: str | None = None,
    ):
        self.participant_id = str(participant_id).strip() or "unknown"
        self.task_type = task_type
        self.timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_root = str(Path(__file__).resolve().parents[2] / "data" / "crafting")
        root = output_root or os.environ.get("RL_DATA_ROOT") or default_root
        self.data_dir = os.path.join(root, self.timestamp_str)
        os.makedirs(self.data_dir, exist_ok=True)
        self.memory_buffer = []
        self.episode_count = 0
        self.step_count = 0
        print(f"Data Recorder Initialized. Output directory: {self.data_dir}")
        print(f"Task Type: {self.task_type}, Participant: {self.participant_id}")

    def start_episode(self):
        self.episode_count += 1
        self.step_count = 0

    def log_action(
        self,
        episode,
        step,
        map_type,
        current_room_id,
        pos_x,
        pos_y,
        backpack,
        action_name,
        action_detail,
        reward,
        is_valid,
        game_over,
        **kwargs,
    ):
        self.step_count += 1
        record = {
            "Participant": self.participant_id,
            "Task_Type": self.task_type,
            "Episode_ID": episode,
            "Step_Index": step,
            "Timestamp": datetime.datetime.now().isoformat(),
            "Map_Structure": map_type,
            "Current_Room_ID": current_room_id,
            "Grid_X": pos_x,
            "Grid_Y": pos_y,
            "Backpack_Content": str(backpack),
            "Backpack_Count": len(backpack) if backpack else 0,
            "Action_Type": action_name,
            "Action_Detail": str(action_detail),
            "Action_Valid": is_valid,
            "Reward": reward,
            "Game_Over": game_over,
        }
        record.update(kwargs)
        self.memory_buffer.append(record)

    def save_to_file(self):
        if not self.memory_buffer:
            return

        safe = "".join(
            c if c.isalnum() or c in "-_." else "_"
            for c in self.participant_id
        ).strip("_") or "unknown"
        filename_base = f"{self.data_dir}/game_log_{safe}"

        if HAS_PANDAS:
            try:
                pd.DataFrame(self.memory_buffer).to_excel(
                    f"{filename_base}.xlsx", index=False
                )
                print(f"Data saved to Excel: {filename_base}.xlsx")
                return
            except Exception as e:
                print(f"Excel error: {e}")

        try:
            all_keys = set()
            for row in self.memory_buffer:
                all_keys.update(row.keys())
            fieldnames = sorted(all_keys)
            with open(f"{filename_base}.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(self.memory_buffer)
            print(f"Data saved to CSV: {filename_base}.csv")
        except Exception as e:
            print(f"CSV error: {e}")
