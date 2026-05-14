"""
数据记录器
用于记录实验数据（两个任务共用）
"""
import datetime
import os
import csv

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


class RLDataRecorder:
    """强化学习数据记录器"""
    
    def __init__(self, participant_id="RL_Agent_01", task_type="Unknown", output_root: str | None = None):
        self.participant_id = participant_id
        self.task_type = task_type
        self.timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        # 输出根目录可配置：
        # 1) 显式传参 output_root
        # 2) 环境变量 RL_DATA_ROOT
        # 3) 默认 "rl_data"（兼容旧行为）
        root = output_root or os.environ.get("RL_DATA_ROOT") or "rl_data"
        self.data_dir = os.path.join(root, self.timestamp_str)
        os.makedirs(self.data_dir, exist_ok=True)
        self.memory_buffer = []
        self.episode_count = 0
        self.step_count = 0
        print(f"Data Recorder Initialized. Output directory: {self.data_dir}")
        print(f"Task Type: {task_type}, Participant: {participant_id}")

    def start_episode(self):
        """开始新的episode"""
        self.episode_count += 1
        self.step_count = 0

    def log_action(self, episode, step, map_type, current_room_id, pos_x, pos_y,
                   backpack, action_name, action_detail, reward, is_valid, game_over,
                   **kwargs):
        """
        记录动作数据
        
        Args:
            episode: Episode ID
            step: Step index
            map_type: 地图类型
            current_room_id: 当前房间ID
            pos_x, pos_y: 位置坐标
            backpack: 背包内容（导航任务可为空）
            action_name: 动作名称
            action_detail: 动作详情
            reward: 奖励值
            is_valid: 动作是否有效
            game_over: 是否游戏结束
            **kwargs: 额外字段（如熵值、复杂度等）
        """
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
        # 添加额外字段（如导航任务的熵值、复杂度等）
        record.update(kwargs)
        self.memory_buffer.append(record)

    def save_to_file(self):
        """保存数据到文件"""
        if not self.memory_buffer:
            return
        
        filename_base = f"{self.data_dir}/game_log_{self.participant_id}"
        
        # 尝试保存为Excel
        if HAS_PANDAS:
            try:
                pd.DataFrame(self.memory_buffer).to_excel(
                    f"{filename_base}.xlsx", index=False
                )
                print(f"Data saved to Excel: {filename_base}.xlsx")
                return
            except Exception as e:
                print(f"Excel error: {e}")

        # 保存为CSV
        try:
            keys = self.memory_buffer[0].keys()
            with open(f"{filename_base}.csv", 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(self.memory_buffer)
            print(f"Data saved to CSV: {filename_base}.csv")
        except Exception as e:
            print(f"CSV error: {e}")

