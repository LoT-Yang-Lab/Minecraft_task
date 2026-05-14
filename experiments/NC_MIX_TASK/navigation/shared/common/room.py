"""
房间类
表示游戏中的房间单元
"""
from typing import Dict, Optional, Tuple, List, Union


class Room:
    """房间类。doors 为「方向 → 目标房间 ID 列表」，支持同一方向多扇门（多条连线）。"""

    def __init__(self, room_id: int, logical_pos: Tuple[int, int]):
        """
        初始化房间
        
        Args:
            room_id: 房间ID（原始坐标ID，如 201）
            logical_pos: 逻辑位置 (x, y)
        """
        self.id = room_id              # 原始坐标ID (e.g., 201)
        self.seq_id = 0                 # 顺序ID (e.g., 1, 2, 3...)
        self.logical_pos = logical_pos  # 逻辑位置 (x, y)
        self.fragment = None            # 房间中的物品/碎片
        self.doors: Dict[str, List[int]] = {}  # 门连接 {方向: [目标房间ID, ...]}，同方向可多个
        self.visited = False            # 是否已访问
        self.is_obstacle = False        # 是否为障碍物（导航任务用）
        self.is_target = False          # 是否为目标点（导航任务用）

    def add_door(self, direction: str, target_id: int):
        """添加一条门连接（同方向可有多条，不重复添加）。"""
        if direction not in self.doors:
            self.doors[direction] = []
        if target_id not in self.doors[direction]:
            self.doors[direction].append(target_id)

    def remove_door(self, direction: str, target_id: Optional[int] = None):
        """移除门连接。若指定 target_id 则只移该目标，否则移掉该方向全部。"""
        if direction not in self.doors:
            return
        if target_id is not None:
            self.doors[direction] = [x for x in self.doors[direction] if x != target_id]
        if target_id is None or not self.doors[direction]:
            self.doors.pop(direction, None)

    def has_door(self, direction: str) -> bool:
        """检查是否有指定方向的门"""
        return bool(self.doors.get(direction))

    def get_neighbor_id(self, direction: str) -> Optional[int]:
        """获取指定方向的第一个邻居房间ID（兼容旧逻辑）。"""
        lst = self.doors.get(direction)
        if not lst:
            return None
        return lst[0] if isinstance(lst, list) else lst

    def get_neighbor_ids(self, direction: str) -> List[int]:
        """获取指定方向的所有目标房间ID列表。"""
        lst = self.doors.get(direction)
        if not lst:
            return []
        return list(lst) if isinstance(lst, list) else [lst]

