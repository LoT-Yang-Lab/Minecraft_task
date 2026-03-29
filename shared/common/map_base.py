"""
基础地图生成器
提供四种基础地图结构：Barbell, Grid, Path, Ladder
"""
from typing import Dict, Tuple, Optional
from .room import Room


class BaseMapGenerator:
    """基础地图生成器"""
    
    def __init__(self):
        self.rooms: Dict[int, Room] = {}
    
    def create_room(self, x: int, y: int) -> int:
        """
        创建房间
        
        Args:
            x, y: 逻辑坐标
            
        Returns:
            房间ID
        """
        rid = y * 100 + x
        if rid not in self.rooms:
            self.rooms[rid] = Room(rid, (x, y))
        return rid
    
    def connect_rooms(self, rid1: int, rid2: int, direction: str):
        """
        连接两个房间
        
        Args:
            rid1: 房间1的ID
            rid2: 房间2的ID
            direction: 从房间1到房间2的方向
        """
        reverse_dirs = {
            "north": "south", "south": "north",
            "east": "west", "west": "east"
        }
        rev = reverse_dirs[direction]
        
        if rid1 in self.rooms and rid2 in self.rooms:
            self.rooms[rid1].add_door(direction, rid2)
            self.rooms[rid2].add_door(rev, rid1)
    
    def disconnect_rooms(self, x: int, y: int, direction: str):
        """
        断开房间连接（制造墙壁）
        
        Args:
            x, y: 房间逻辑坐标
            direction: 要断开的方向
        """
        rid = y * 100 + x
        if rid not in self.rooms:
            return
        
        self.rooms[rid].remove_door(direction)
        
        # 处理反向连接
        dx, dy = {
            'north': (0, -1), 'south': (0, 1),
            'east': (1, 0), 'west': (-1, 0)
        }[direction]
        
        rev = {
            'north': 'south', 'south': 'north',
            'east': 'west', 'west': 'east'
        }[direction]
        
        rid2 = (y + dy) * 100 + (x + dx)
        if rid2 in self.rooms:
            self.rooms[rid2].remove_door(rev)
    
    def place_fragment(self, x: int, y: int, item: str):
        """在指定位置放置物品"""
        rid = y * 100 + x
        if rid in self.rooms:
            self.rooms[rid].fragment = item
    
    def get_room(self, x: int, y: int) -> Optional[Room]:
        """获取指定位置的房间"""
        rid = y * 100 + x
        return self.rooms.get(rid)
    
    def setup_barbell(self) -> int:
        """
        生成Barbell（杠铃型）地图
        
        Returns:
            起始房间ID
        """
        # 左侧块 (x=0,1, rows=0-3)
        for r in range(4):
            for c in range(2):
                self.create_room(c, r)
        
        # 右侧块 (x=4,5, rows=0-3)
        for r in range(4):
            for c in range(4, 6):
                self.create_room(c, r)
        
        # 中间走廊 (x=2,3, rows=1,2)
        for r in [1, 2]:
            for c in range(2, 4):
                self.create_room(c, r)
        
        # 建立全连接
        for rid, room in self.rooms.items():
            x, y = room.logical_pos
            # 东向连接
            if (y * 100 + (x + 1)) in self.rooms:
                self.connect_rooms(rid, y * 100 + (x + 1), "east")
            # 南向连接
            if ((y + 1) * 100 + x) in self.rooms:
                self.connect_rooms(rid, (y + 1) * 100 + x, "south")
        
        # 墙壁设置
        self.disconnect_rooms(2, 1, 'east')  # 上方走廊中间断开
        self.disconnect_rooms(2, 2, 'west')  # Room (2,2) 左侧墙
        self.disconnect_rooms(4, 2, 'west')  # Room (4,2) 左侧墙
        
        return 0  # 起始房间ID
    
    def setup_grid(self) -> int:
        """
        生成Grid（网格型）地图
        
        Returns:
            起始房间ID
        """
        for y in range(4):
            for x in range(5):
                rid = self.create_room(x, y)
                if x > 0:
                    self.connect_rooms(rid, y * 100 + (x - 1), "west")
                if y > 0:
                    self.connect_rooms(rid, (y - 1) * 100 + x, "north")
        
        return 202  # 起始房间ID (2, 2)
    
    def setup_path(self) -> int:
        """
        生成Path（路径型）地图
        
        Returns:
            起始房间ID
        """
        path_coords = []
        width = 6
        
        # 第一行：从左到右
        for x in range(width):
            path_coords.append((x, 0))
        
        # 第二行：从右到左
        for x in range(width - 1, -1, -1):
            path_coords.append((x, 1))
        
        # 第三行：从左到右
        for x in range(width):
            path_coords.append((x, 2))
        
        # 创建房间并连接
        prev_rid = None
        for (x, y) in path_coords:
            rid = self.create_room(x, y)
            if prev_rid is not None:
                prev_room = self.rooms[prev_rid]
                px, py = prev_room.logical_pos
                if x > px:
                    self.connect_rooms(prev_rid, rid, "east")
                elif x < px:
                    self.connect_rooms(prev_rid, rid, "west")
                elif y > py:
                    self.connect_rooms(prev_rid, rid, "south")
            prev_rid = rid
        
        return 0  # 起始房间ID
    
    def setup_ladder(self) -> int:
        """
        生成Ladder（梯子型）地图
        
        Returns:
            起始房间ID
        """
        # 上层 (y=0)
        for x in range(7):
            self.create_room(x, 0)
        
        # 下层 (y=2)
        for x in range(7):
            self.create_room(x, 2)
        
        # 中间连接房间 (y=1, x=3)
        self.create_room(3, 1)
        
        # 水平连接
        for x in range(6):
            self.connect_rooms(0 * 100 + x, 0 * 100 + (x + 1), "east")
            self.connect_rooms(2 * 100 + x, 2 * 100 + (x + 1), "east")
        
        # 垂直连接
        self.connect_rooms(0 * 100 + 3, 1 * 100 + 3, "south")
        self.connect_rooms(1 * 100 + 3, 2 * 100 + 3, "south")
        
        return 0  # 起始房间ID
    
    def assign_sequential_ids(self):
        """为所有房间分配顺序ID (1, 2, 3...)"""
        sorted_keys = sorted(self.rooms.keys())
        for idx, key in enumerate(sorted_keys):
            self.rooms[key].seq_id = idx + 1
    
    def generate(self, map_type: str) -> Tuple[Dict[int, Room], int]:
        """
        生成指定类型的地图
        
        Args:
            map_type: 地图类型 ("Barbell", "Grid", "Path", "Ladder")
            
        Returns:
            (rooms字典, 起始房间ID)
        """
        self.rooms = {}
        start_rid = 0
        
        if map_type == "Barbell":
            start_rid = self.setup_barbell()
        elif map_type == "Grid":
            start_rid = self.setup_grid()
        elif map_type == "Path":
            start_rid = self.setup_path()
        elif map_type == "Ladder":
            start_rid = self.setup_ladder()
        else:
            raise ValueError(f"Unknown map type: {map_type}")
        
        # 分配顺序ID
        self.assign_sequential_ids()
        
        return self.rooms, start_rid

