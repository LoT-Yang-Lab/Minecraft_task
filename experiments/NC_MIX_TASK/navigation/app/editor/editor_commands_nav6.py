"""
Navigation6 地图编辑器命令模式实现
"""
from typing import Optional, List, Any, Tuple, Dict
from .editor_data_nav6 import EditorMapDataNav6


class EditorCommand:
    def execute(self) -> bool:
        raise NotImplementedError()
    def undo(self) -> bool:
        raise NotImplementedError()
    def get_description(self) -> str:
        return "未知命令"


class CommandHistory:
    def __init__(self, max_history: int = 100):
        self.history: List[EditorCommand] = []
        self.redo_stack: List[EditorCommand] = []
        self.max_history = max_history

    def execute_command(self, command: EditorCommand) -> bool:
        if command.execute():
            self.history.append(command)
            self.redo_stack.clear()
            if len(self.history) > self.max_history:
                self.history.pop(0)
            return True
        return False

    def undo(self) -> Optional[EditorCommand]:
        if not self.history:
            return None
        command = self.history.pop()
        if command.undo():
            self.redo_stack.append(command)
            return command
        self.history.append(command)
        return None

    def redo(self) -> Optional[EditorCommand]:
        if not self.redo_stack:
            return None
        command = self.redo_stack.pop()
        if command.execute():
            self.history.append(command)
            return command
        self.redo_stack.append(command)
        return None

    def can_undo(self) -> bool:
        return len(self.history) > 0
    def can_redo(self) -> bool:
        return len(self.redo_stack) > 0
    def clear(self):
        self.history.clear()
        self.redo_stack.clear()


class AddRoomCommand(EditorCommand):
    def __init__(self, editor_data: EditorMapDataNav6, x: int, y: int):
        self.editor_data = editor_data
        self.x, self.y = x, y
        self.room_id = None
    def execute(self) -> bool:
        self.room_id = self.y * 100 + self.x
        return self.editor_data.add_room(self.x, self.y)
    def undo(self) -> bool:
        return self.editor_data.remove_room(self.room_id) if self.room_id else False
    def get_description(self) -> str:
        return f"添加房间 ({self.x}, {self.y})"


class RemoveRoomCommand(EditorCommand):
    def __init__(self, editor_data: EditorMapDataNav6, rid: int):
        self.editor_data = editor_data
        self.rid = rid
        self.saved_room_data: Optional[Dict[str, Any]] = None
    def execute(self) -> bool:
        room = self.editor_data.rooms.get(self.rid)
        if not room:
            return False
        from shared.common.room import Room
        self.saved_room_data = {
            "logical_pos": room.logical_pos, "seq_id": room.seq_id,
            "doors": dict(room.doors), "is_obstacle": room.is_obstacle,
            "is_target": room.is_target, "visited": room.visited,
        }
        return self.editor_data.remove_room(self.rid)
    def undo(self) -> bool:
        if not self.saved_room_data:
            return False
        from shared.common.room import Room
        room = Room(self.rid, self.saved_room_data["logical_pos"])
        room.seq_id = self.saved_room_data["seq_id"]
        room.doors = self.saved_room_data["doors"]
        room.is_obstacle = self.saved_room_data["is_obstacle"]
        room.is_target = self.saved_room_data["is_target"]
        room.visited = self.saved_room_data["visited"]
        self.editor_data.rooms[self.rid] = room
        self.editor_data._assign_sequential_ids()
        return True
    def get_description(self) -> str:
        return f"移除房间 ID:{self.rid}"


class ToggleDoorCommand(EditorCommand):
    def __init__(self, editor_data: EditorMapDataNav6, x: int, y: int, direction: str):
        self.editor_data = editor_data
        self.x, self.y, self.direction = x, y, direction
        self.was_added = False
    def execute(self) -> bool:
        rid = self.y * 100 + self.x
        room = self.editor_data.rooms.get(rid)
        if not room:
            return False
        self.was_added = self.direction not in room.doors
        return self.editor_data.toggle_door(self.x, self.y, self.direction)
    def undo(self) -> bool:
        return self.editor_data.toggle_door(self.x, self.y, self.direction)
    def get_description(self) -> str:
        return f"{'添加' if self.was_added else '删除'}门 ({self.x}, {self.y}) {self.direction}"


class ToggleObstacleCommand(EditorCommand):
    def __init__(self, editor_data: EditorMapDataNav6, gx: int, gy: int):
        self.editor_data, self.gx, self.gy = editor_data, gx, gy
        self.was_added = False
    def execute(self) -> bool:
        self.was_added = (self.gx, self.gy) not in self.editor_data.obstacle_map
        return self.editor_data.toggle_obstacle(self.gx, self.gy)
    def undo(self) -> bool:
        return self.editor_data.toggle_obstacle(self.gx, self.gy)
    def get_description(self) -> str:
        return f"{'添加' if self.was_added else '删除'}障碍物 ({self.gx}, {self.gy})"


class ToggleSingleCellCommand(EditorCommand):
    def __init__(self, editor_data: EditorMapDataNav6, gx: int, gy: int):
        self.editor_data, self.gx, self.gy = editor_data, gx, gy
        self.was_added = False
    def execute(self) -> bool:
        self.was_added = (self.gx, self.gy) not in self.editor_data.single_cells
        return self.editor_data.toggle_single_cell(self.gx, self.gy)
    def undo(self) -> bool:
        return self.editor_data.toggle_single_cell(self.gx, self.gy)
    def get_description(self) -> str:
        return f"{'添加' if self.was_added else '删除'}单格可行走 ({self.gx}, {self.gy})"


class ToggleSingleCellDoorCommand(EditorCommand):
    def __init__(self, editor_data: EditorMapDataNav6, gx: int, gy: int, direction: str):
        self.editor_data, self.gx, self.gy, self.direction = editor_data, gx, gy, direction
        self.was_added = False
    def execute(self) -> bool:
        self.was_added = self.direction not in self.editor_data.get_single_cell_doors(self.gx, self.gy)
        return self.editor_data.toggle_single_cell_door(self.gx, self.gy, self.direction)
    def undo(self) -> bool:
        return self.editor_data.toggle_single_cell_door(self.gx, self.gy, self.direction)
    def get_description(self) -> str:
        return f"{'添加' if self.was_added else '删除'}单格门 ({self.gx},{self.gy}) {self.direction}"


class AddSubwayPathPointCommand(EditorCommand):
    def __init__(self, editor_data: EditorMapDataNav6, gx: int, gy: int):
        self.editor_data, self.gx, self.gy = editor_data, gx, gy
    def execute(self) -> bool:
        return self.editor_data.add_subway_path_point(self.gx, self.gy)
    def undo(self) -> bool:
        return self.editor_data.remove_subway_path_point(self.gx, self.gy)
    def get_description(self) -> str:
        return f"添加地铁路径点 ({self.gx}, {self.gy})"


class RemoveSubwayPathPointCommand(EditorCommand):
    def __init__(self, editor_data: EditorMapDataNav6, gx: int, gy: int):
        self.editor_data, self.gx, self.gy = editor_data, gx, gy
        self.was_station = False
    def execute(self) -> bool:
        self.was_station = (self.gx, self.gy) in self.editor_data.subway_stations
        return self.editor_data.remove_subway_path_point(self.gx, self.gy)
    def undo(self) -> bool:
        if self.editor_data.add_subway_path_point(self.gx, self.gy):
            if self.was_station:
                self.editor_data.subway_stations.add((self.gx, self.gy))
            return True
        return False
    def get_description(self) -> str:
        return f"移除地铁路径点 ({self.gx}, {self.gy})"


class ToggleSubwayStationCommand(EditorCommand):
    def __init__(self, editor_data: EditorMapDataNav6, gx: int, gy: int):
        self.editor_data, self.gx, self.gy = editor_data, gx, gy
        self.was_added = False
    def execute(self) -> bool:
        self.was_added = (self.gx, self.gy) not in self.editor_data.subway_stations
        return self.editor_data.toggle_subway_station(self.gx, self.gy)
    def undo(self) -> bool:
        return self.editor_data.toggle_subway_station(self.gx, self.gy)
    def get_description(self) -> str:
        return f"{'添加' if self.was_added else '删除'}地铁站点 ({self.gx}, {self.gy})"


class SetTransitSegmentCurveCommand(EditorCommand):
    """设置展平线路索引下某路径段的弧度偏置（仅影响编辑器可视化）。"""

    def __init__(self, editor_data: EditorMapDataNav6, flat_line_idx: int, seg_idx: int, new_value: float):
        self.editor_data = editor_data
        self.flat_line_idx = flat_line_idx
        self.seg_idx = seg_idx
        self.new_value = float(new_value)
        self.old_value: Optional[float] = None

    def execute(self) -> bool:
        self.old_value = self.editor_data.get_segment_curve_value(self.flat_line_idx, self.seg_idx)
        if self.old_value is None:
            return False
        if abs(self.old_value - self.new_value) < 1e-9:
            return False
        return self.editor_data.set_segment_curve_value(self.flat_line_idx, self.seg_idx, self.new_value)

    def undo(self) -> bool:
        if self.old_value is None:
            return False
        return self.editor_data.set_segment_curve_value(self.flat_line_idx, self.seg_idx, self.old_value)

    def get_description(self) -> str:
        return f"线路段弧度 [{self.flat_line_idx}:{self.seg_idx}] → {self.new_value:.2f}"


class SetTransitSegmentStraightCommand(EditorCommand):
    """某路径段是否强制直线绘制（仅编辑器可视化）。"""

    def __init__(self, editor_data: EditorMapDataNav6, flat_line_idx: int, seg_idx: int, new_straight: bool):
        self.editor_data = editor_data
        self.flat_line_idx = flat_line_idx
        self.seg_idx = seg_idx
        self.new_straight = bool(new_straight)
        self.old_straight: Optional[bool] = None

    def execute(self) -> bool:
        self.old_straight = self.editor_data.get_segment_straight(self.flat_line_idx, self.seg_idx)
        if self.old_straight is None:
            return False
        if self.old_straight == self.new_straight:
            return False
        return self.editor_data.set_segment_straight(self.flat_line_idx, self.seg_idx, self.new_straight)

    def undo(self) -> bool:
        if self.old_straight is None:
            return False
        return self.editor_data.set_segment_straight(self.flat_line_idx, self.seg_idx, self.old_straight)

    def get_description(self) -> str:
        return f"线路段直线 [{self.flat_line_idx}:{self.seg_idx}] → {self.new_straight}"


class AddPortalPairCommand(EditorCommand):
    def __init__(self, editor_data: EditorMapDataNav6, entrance: Tuple[int, int], exit_pos: Tuple[int, int]):
        self.editor_data, self.entrance, self.exit_pos = editor_data, entrance, exit_pos
    def execute(self) -> bool:
        if (self.entrance, self.exit_pos) in self.editor_data.portal_pairs:
            return False
        if (self.exit_pos, self.entrance) in self.editor_data.portal_pairs:
            return False
        self.editor_data.portal_pairs.append((self.entrance, self.exit_pos))
        return True
    def undo(self) -> bool:
        return self.editor_data.remove_portal_pair(self.entrance, self.exit_pos)
    def get_description(self) -> str:
        return f"添加传送门 ({self.entrance[0]},{self.entrance[1]}) <-> ({self.exit_pos[0]},{self.exit_pos[1]})"


class RemovePortalPairCommand(EditorCommand):
    def __init__(self, editor_data: EditorMapDataNav6, entrance: Tuple[int, int], exit_pos: Tuple[int, int]):
        self.editor_data, self.entrance, self.exit_pos = editor_data, entrance, exit_pos
    def execute(self) -> bool:
        return self.editor_data.remove_portal_pair(self.entrance, self.exit_pos)
    def undo(self) -> bool:
        if (self.entrance, self.exit_pos) not in self.editor_data.portal_pairs:
            self.editor_data.portal_pairs.append((self.entrance, self.exit_pos))
            return True
        return False
    def get_description(self) -> str:
        return f"移除传送门 ({self.entrance[0]},{self.entrance[1]}) <-> ({self.exit_pos[0]},{self.exit_pos[1]})"


class SetStartPosCommand(EditorCommand):
    def __init__(self, editor_data: EditorMapDataNav6, gx: int, gy: int):
        self.editor_data, self.gx, self.gy = editor_data, gx, gy
        self.old_pos: Optional[Tuple[int, int]] = None
    def execute(self) -> bool:
        self.old_pos = self.editor_data.start_pos
        return self.editor_data.set_start_pos(self.gx, self.gy)
    def undo(self) -> bool:
        self.editor_data.start_pos = self.old_pos
        return True
    def get_description(self) -> str:
        return f"设置起始点 ({self.gx}, {self.gy})"


class SetTargetPosCommand(EditorCommand):
    def __init__(self, editor_data: EditorMapDataNav6, gx: int, gy: int):
        self.editor_data, self.gx, self.gy = editor_data, gx, gy
        self.old_pos = None
        self.old_target_room_id = None
    def execute(self) -> bool:
        self.old_pos = self.editor_data.target_pos
        if self.old_pos:
            room = self.editor_data.get_room_by_grid(*self.old_pos)
            self.old_target_room_id = room.id if room else None
        return self.editor_data.set_target_pos(self.gx, self.gy)
    def undo(self) -> bool:
        for room in self.editor_data.rooms.values():
            room.is_target = False
        if self.old_pos:
            self.editor_data.target_pos = self.old_pos
            if self.old_target_room_id:
                r = self.editor_data.rooms.get(self.old_target_room_id)
                if r:
                    r.is_target = True
        else:
            self.editor_data.target_pos = None
        return True
    def get_description(self) -> str:
        return f"设置目标点 ({self.gx}, {self.gy})"


class CommandFactory:
    @staticmethod
    def create_add_room_command(editor_data: EditorMapDataNav6, x: int, y: int): return AddRoomCommand(editor_data, x, y)
    @staticmethod
    def create_remove_room_command(editor_data: EditorMapDataNav6, rid: int): return RemoveRoomCommand(editor_data, rid)
    @staticmethod
    def create_toggle_door_command(editor_data: EditorMapDataNav6, x: int, y: int, direction: str): return ToggleDoorCommand(editor_data, x, y, direction)
    @staticmethod
    def create_toggle_obstacle_command(editor_data: EditorMapDataNav6, gx: int, gy: int): return ToggleObstacleCommand(editor_data, gx, gy)
    @staticmethod
    def create_toggle_single_cell_command(editor_data: EditorMapDataNav6, gx: int, gy: int): return ToggleSingleCellCommand(editor_data, gx, gy)
    @staticmethod
    def create_toggle_single_cell_door_command(editor_data: EditorMapDataNav6, gx: int, gy: int, direction: str): return ToggleSingleCellDoorCommand(editor_data, gx, gy, direction)
    @staticmethod
    def create_add_subway_path_point_command(editor_data: EditorMapDataNav6, gx: int, gy: int): return AddSubwayPathPointCommand(editor_data, gx, gy)
    @staticmethod
    def create_remove_subway_path_point_command(editor_data: EditorMapDataNav6, gx: int, gy: int): return RemoveSubwayPathPointCommand(editor_data, gx, gy)
    @staticmethod
    def create_toggle_subway_station_command(editor_data: EditorMapDataNav6, gx: int, gy: int): return ToggleSubwayStationCommand(editor_data, gx, gy)
    @staticmethod
    def create_set_transit_segment_curve_command(
        editor_data: EditorMapDataNav6, flat_line_idx: int, seg_idx: int, new_value: float
    ):
        return SetTransitSegmentCurveCommand(editor_data, flat_line_idx, seg_idx, new_value)
    @staticmethod
    def create_set_transit_segment_straight_command(
        editor_data: EditorMapDataNav6, flat_line_idx: int, seg_idx: int, straight: bool
    ):
        return SetTransitSegmentStraightCommand(editor_data, flat_line_idx, seg_idx, straight)
    @staticmethod
    def create_add_portal_pair_command(editor_data: EditorMapDataNav6, entrance: Tuple[int, int], exit_pos: Tuple[int, int]): return AddPortalPairCommand(editor_data, entrance, exit_pos)
    @staticmethod
    def create_set_start_pos_command(editor_data: EditorMapDataNav6, gx: int, gy: int): return SetStartPosCommand(editor_data, gx, gy)
    @staticmethod
    def create_set_target_pos_command(editor_data: EditorMapDataNav6, gx: int, gy: int): return SetTargetPosCommand(editor_data, gx, gy)
