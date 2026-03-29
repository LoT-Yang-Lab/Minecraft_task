"""
Navigation 编辑器数据基类（由 Navigation2 迁移）。
"""
from typing import Dict, Set, Optional, Tuple, List, Any
from datetime import datetime

from shared.common.room import Room


class EditorMapDataNav2:
    """Navigation2 编辑器地图数据模型。"""

    def __init__(self):
        self.rooms: Dict[int, Room] = {}
        self.obstacle_map: Dict[Tuple[int, int], bool] = {}
        self.subway_path: List[Tuple[int, int]] = []
        self.subway_stations: Set[Tuple[int, int]] = set()
        self.portal_pairs: List[Tuple[Tuple[int, int], Tuple[int, int]]] = []
        self.single_cells: Set[Tuple[int, int]] = set()
        self.single_cell_doors: Dict[Tuple[int, int], Set[str]] = {}
        self.start_pos: Optional[Tuple[int, int]] = None
        self.target_pos: Optional[Tuple[int, int]] = None
        self.metadata: Dict[str, Any] = {
            "name": "未命名地图",
            "author": "",
            "description": "",
            "created_date": datetime.now().strftime("%Y-%m-%d"),
            "modified_date": datetime.now().strftime("%Y-%m-%d"),
        }

        self.selected_room_ids: Set[int] = set()
        self.selected_cell: Optional[Tuple[int, int]] = None
        self.portal_entrance: Optional[Tuple[int, int]] = None

    def add_room(self, x: int, y: int) -> bool:
        rid = y * 100 + x
        if rid in self.rooms:
            return False

        room = Room(rid, (x, y))
        self.rooms[rid] = room
        self._assign_sequential_ids()
        return True

    def remove_room(self, rid: int) -> bool:
        if rid not in self.rooms:
            return False

        room = self.rooms[rid]
        for direction in list(room.doors.keys()):
            self.remove_door_bidirectional(rid, direction)

        lx, ly = room.logical_pos
        for dx in range(3):
            for dy in range(3):
                gx, gy = lx * 3 + dx, ly * 3 + dy
                if (gx, gy) in self.obstacle_map:
                    del self.obstacle_map[(gx, gy)]

        for dx in range(3):
            for dy in range(3):
                gx, gy = lx * 3 + dx, ly * 3 + dy
                self.subway_stations.discard((gx, gy))

        self.subway_path = [p for p in self.subway_path if not self._is_in_room(p, lx, ly)]
        self.portal_pairs = [
            (ent, ext)
            for ent, ext in self.portal_pairs
            if not (self._is_in_room(ent, lx, ly) or self._is_in_room(ext, lx, ly))
        ]

        if self.start_pos and self._is_in_room(self.start_pos, lx, ly):
            self.start_pos = None
        if self.target_pos and self._is_in_room(self.target_pos, lx, ly):
            self.target_pos = None

        if rid in self.selected_room_ids:
            self.selected_room_ids.remove(rid)

        del self.rooms[rid]
        self._assign_sequential_ids()
        return True

    def _is_in_room(self, pos: Tuple[int, int], lx: int, ly: int) -> bool:
        gx, gy = pos
        room_gx_min, room_gy_min = lx * 3, ly * 3
        room_gx_max, room_gy_max = room_gx_min + 2, room_gy_min + 2
        return room_gx_min <= gx <= room_gx_max and room_gy_min <= gy <= room_gy_max

    def get_room_at(self, x: int, y: int) -> Optional[Room]:
        rid = y * 100 + x
        return self.rooms.get(rid)

    def get_room_by_grid(self, gx: int, gy: int) -> Optional[Room]:
        lx, ly = gx // 3, gy // 3
        return self.get_room_at(lx, ly)

    def add_door_bidirectional(self, rid1: int, rid2: int, direction: str) -> bool:
        if rid1 not in self.rooms or rid2 not in self.rooms:
            return False

        room1, room2 = self.rooms[rid1], self.rooms[rid2]
        if room1.is_obstacle or room2.is_obstacle:
            return False

        reverse_dirs = {"north": "south", "south": "north", "east": "west", "west": "east"}
        rev = reverse_dirs[direction]
        room1.add_door(direction, rid2)
        room2.add_door(rev, rid1)
        return True

    def remove_door_bidirectional(self, rid: int, direction: str) -> bool:
        if rid not in self.rooms:
            return False

        room = self.rooms[rid]
        if not room.doors.get(direction):
            return False

        neighbor_rid = room.get_neighbor_id(direction)
        if neighbor_rid not in self.rooms:
            room.remove_door(direction)
            return True

        reverse_dirs = {"north": "south", "south": "north", "east": "west", "west": "east"}
        rev = reverse_dirs[direction]
        room.remove_door(direction, neighbor_rid)
        self.rooms[neighbor_rid].remove_door(rev, rid)
        return True

    def toggle_door(self, x: int, y: int, direction: str) -> bool:
        rid = y * 100 + x
        if rid not in self.rooms:
            return False

        room = self.rooms[rid]
        dx_map = {"north": 0, "south": 0, "east": 1, "west": -1}
        dy_map = {"north": -1, "south": 1, "east": 0, "west": 0}
        neighbor_x = x + dx_map[direction]
        neighbor_y = y + dy_map[direction]
        neighbor_rid = neighbor_y * 100 + neighbor_x

        if neighbor_rid not in self.rooms:
            return False

        if direction in room.doors:
            return self.remove_door_bidirectional(rid, direction)
        return self.add_door_bidirectional(rid, neighbor_rid, direction)

    def toggle_obstacle(self, gx: int, gy: int) -> bool:
        pos = (gx, gy)
        if pos in self.obstacle_map:
            del self.obstacle_map[pos]
            return True
        room = self.get_room_by_grid(gx, gy)
        if room:
            self.obstacle_map[pos] = True
            return True
        return False

    def is_obstacle(self, gx: int, gy: int) -> bool:
        return (gx, gy) in self.obstacle_map

    def toggle_single_cell(self, gx: int, gy: int) -> bool:
        pos = (gx, gy)
        if pos in self.single_cells:
            self.single_cells.discard(pos)
            self.single_cell_doors.pop(pos, None)
            return True
        if self.get_room_by_grid(gx, gy) is not None:
            return False
        if (gx, gy) in self.obstacle_map:
            return False
        self.single_cells.add(pos)
        return True

    def toggle_single_cell_door(self, gx: int, gy: int, direction: str) -> bool:
        pos = (gx, gy)
        if pos not in self.single_cells:
            return False
        if direction not in ("north", "south", "east", "west"):
            return False
        doors = self.single_cell_doors.setdefault(pos, set())
        is_removing = direction in doors
        if is_removing:
            doors.discard(direction)
            if not doors:
                del self.single_cell_doors[pos]
        else:
            doors.add(direction)

        opposite = {"north": "south", "south": "north", "east": "west", "west": "east"}[direction]
        dx, dy = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}[direction]
        neighbor = (gx + dx, gy + dy)
        if neighbor in self.single_cells:
            nb_doors = self.single_cell_doors.setdefault(neighbor, set())
            if is_removing:
                nb_doors.discard(opposite)
                if not nb_doors:
                    self.single_cell_doors.pop(neighbor, None)
            else:
                nb_doors.add(opposite)
        return True

    def get_single_cell_doors(self, gx: int, gy: int) -> Set[str]:
        return self.single_cell_doors.get((gx, gy), set()).copy()

    def _sync_single_cell_doors_both_sides(self) -> None:
        opposite = {"north": "south", "south": "north", "east": "west", "west": "east"}
        delta = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
        for (gx, gy), dirs in list(self.single_cell_doors.items()):
            for d in dirs:
                dx, dy = delta[d]
                nb = (gx + dx, gy + dy)
                if nb in self.single_cells:
                    self.single_cell_doors.setdefault(nb, set()).add(opposite[d])

    def add_subway_path_point(self, gx: int, gy: int) -> bool:
        pos = (gx, gy)
        if not self.subway_path:
            self.subway_path.append(pos)
            return True
        if pos == self.subway_path[0] and len(self.subway_path) >= 2:
            self.subway_path.append(pos)
            return True
        if pos in self.subway_path:
            return False
        self.subway_path.append(pos)
        return True

    def remove_subway_path_point(self, gx: int, gy: int) -> bool:
        pos = (gx, gy)
        if not self.subway_path:
            return False
        if len(self.subway_path) >= 2 and self.subway_path[0] == pos and self.subway_path[-1] == pos:
            self.subway_path.pop()
            self.subway_stations.discard(pos)
            return True
        if pos in self.subway_path:
            self.subway_path.remove(pos)
            self.subway_stations.discard(pos)
            return True
        return False

    def clear_subway_path(self):
        self.subway_path.clear()
        self.subway_stations.clear()

    def toggle_subway_station(self, gx: int, gy: int) -> bool:
        pos = (gx, gy)
        if pos not in self.subway_path:
            return False
        if pos in self.subway_stations:
            self.subway_stations.remove(pos)
        else:
            self.subway_stations.add(pos)
        return True

    def is_subway_station(self, gx: int, gy: int) -> bool:
        return (gx, gy) in self.subway_stations

    def set_portal_entrance(self, gx: int, gy: int) -> bool:
        self.portal_entrance = (gx, gy)
        return True

    def set_portal_exit(self, gx: int, gy: int) -> bool:
        if self.portal_entrance is None:
            return False

        entrance = self.portal_entrance
        exit_pos = (gx, gy)
        if entrance == exit_pos:
            self.portal_entrance = None
            return False

        self.portal_pairs.append((entrance, exit_pos))
        self.portal_entrance = None
        return True

    def cancel_portal_creation(self):
        self.portal_entrance = None

    def remove_portal_pair(self, entrance: Tuple[int, int], exit_pos: Tuple[int, int]) -> bool:
        pair = (entrance, exit_pos)
        if pair in self.portal_pairs:
            self.portal_pairs.remove(pair)
            return True
        reverse_pair = (exit_pos, entrance)
        if reverse_pair in self.portal_pairs:
            self.portal_pairs.remove(reverse_pair)
            return True
        return False

    def get_portal_at(self, gx: int, gy: int) -> Optional[Tuple[Tuple[int, int], Tuple[int, int]]]:
        pos = (gx, gy)
        for entrance, exit_pos in self.portal_pairs:
            if entrance == pos or exit_pos == pos:
                return (entrance, exit_pos)
        return None

    def set_start_pos(self, gx: int, gy: int) -> bool:
        if self.is_obstacle(gx, gy):
            return False
        room = self.get_room_by_grid(gx, gy)
        if room or (gx, gy) in self.single_cells:
            self.start_pos = (gx, gy)
            return True
        return False

    def set_target_pos(self, gx: int, gy: int) -> bool:
        if self.is_obstacle(gx, gy):
            return False
        room = self.get_room_by_grid(gx, gy)
        if room or (gx, gy) in self.single_cells:
            self.target_pos = (gx, gy)
            for r in self.rooms.values():
                r.is_target = False
            if room:
                room.is_target = True
            return True
        return False

    def select_room(self, rid: int, clear_existing: bool = True) -> None:
        if clear_existing:
            self.selected_room_ids.clear()
        if rid in self.rooms:
            self.selected_room_ids.add(rid)

    def toggle_select_room(self, rid: int) -> None:
        if rid in self.selected_room_ids:
            self.selected_room_ids.remove(rid)
        elif rid in self.rooms:
            self.selected_room_ids.add(rid)

    def clear_selection(self) -> None:
        self.selected_room_ids.clear()
        self.selected_cell = None

    def select_cell(self, gx: int, gy: int) -> None:
        self.selected_cell = (gx, gy)

    def calculate_map_bounds(self) -> Tuple[int, int, int, int]:
        all_x: List[int] = []
        all_y: List[int] = []
        for room in self.rooms.values():
            all_x.append(room.logical_pos[0])
            all_y.append(room.logical_pos[1])
        for gx, gy in self.single_cells:
            all_x.append(gx // 3)
            all_y.append(gy // 3)
        if not all_x and not all_y:
            return 0, 0, 0, 0
        return min(all_x), max(all_x), min(all_y), max(all_y)

    def calculate_map_size(self) -> Tuple[int, int]:
        min_x, max_x, min_y, max_y = self.calculate_map_bounds()
        if not self.rooms and not self.single_cells:
            return 0, 0
        return (max_x - min_x + 1), (max_y - min_y + 1)

    def to_dict(self) -> Dict[str, Any]:
        rooms_data = []
        for rid, room in self.rooms.items():
            room_data = {
                "id": rid,
                "logical_pos": list(room.logical_pos),
                "seq_id": room.seq_id,
                "doors": list(room.doors.keys()),
                "is_target": room.is_target,
                "is_obstacle": room.is_obstacle,
                "visited": room.visited,
            }
            rooms_data.append(room_data)

        return {
            "version": "1.0",
            "metadata": self.metadata,
            "rooms": rooms_data,
            "obstacle_map": [[gx, gy] for gx, gy in self.obstacle_map.keys()],
            "subway_path": [[gx, gy] for gx, gy in self.subway_path],
            "subway_stations": [[gx, gy] for gx, gy in self.subway_stations],
            "portal_pairs": [[[ent[0], ent[1]], [ext[0], ext[1]]] for ent, ext in self.portal_pairs],
            "single_cells": [[gx, gy] for gx, gy in self.single_cells],
            "single_cell_doors": [[gx, gy, d] for (gx, gy), dirs in self.single_cell_doors.items() for d in dirs],
            "start_pos": list(self.start_pos) if self.start_pos else None,
            "target_pos": list(self.target_pos) if self.target_pos else None,
        }

    def from_dict(self, data: Dict[str, Any]) -> bool:
        try:
            self.rooms.clear()
            self.obstacle_map.clear()
            self.subway_path.clear()
            self.subway_stations.clear()
            self.portal_pairs.clear()
            self.single_cells.clear()
            self.single_cell_doors.clear()
            self.selected_room_ids.clear()
            self.selected_cell = None
            self.start_pos = None
            self.target_pos = None
            self.portal_entrance = None

            self.metadata = data.get("metadata", {})

            for room_data in data.get("rooms", []):
                rid = room_data["id"]
                logical_pos = tuple(room_data["logical_pos"])
                room = Room(rid, logical_pos)
                room.seq_id = room_data.get("seq_id", 0)
                room.is_obstacle = room_data.get("is_obstacle", False)
                room.is_target = room_data.get("is_target", False)
                room.visited = room_data.get("visited", False)
                self.rooms[rid] = room

            for room_data in data.get("rooms", []):
                rid = room_data["id"]
                room = self.rooms[rid]
                x, y = room.logical_pos
                for direction in room_data.get("doors", []):
                    dx_map = {"north": 0, "south": 0, "east": 1, "west": -1}
                    dy_map = {"north": -1, "south": 1, "east": 0, "west": 0}
                    neighbor_x = x + dx_map[direction]
                    neighbor_y = y + dy_map[direction]
                    neighbor_rid = neighbor_y * 100 + neighbor_x
                    if neighbor_rid in self.rooms:
                        room.add_door(direction, neighbor_rid)

            for pos in data.get("obstacle_map", []):
                self.obstacle_map[tuple(pos)] = True

            self.subway_path = [tuple(pos) for pos in data.get("subway_path", [])]
            self.subway_stations = {tuple(pos) for pos in data.get("subway_stations", [])}
            self.portal_pairs = [(tuple(ent), tuple(ext)) for ent, ext in data.get("portal_pairs", [])]
            self.single_cells = {tuple(pos) for pos in data.get("single_cells", [])}

            self.single_cell_doors.clear()
            for item in data.get("single_cell_doors", []):
                if len(item) >= 3:
                    gx, gy, d = item[0], item[1], item[2]
                    pos = (gx, gy)
                    if pos in self.single_cells and d in ("north", "south", "east", "west"):
                        self.single_cell_doors.setdefault(pos, set()).add(d)
            self._sync_single_cell_doors_both_sides()

            if data.get("start_pos"):
                self.start_pos = tuple(data["start_pos"])
            if data.get("target_pos"):
                self.target_pos = tuple(data["target_pos"])

            self._assign_sequential_ids()
            return True
        except Exception as e:
            print(f"加载地图数据失败: {e}")
            return False

    def _assign_sequential_ids(self):
        if not self.rooms:
            return
        sorted_rooms = sorted(self.rooms.items(), key=lambda item: (item[1].logical_pos[1], item[1].logical_pos[0]))
        for idx, (_rid, room) in enumerate(sorted_rooms):
            room.seq_id = idx + 1

    def validate_map(self) -> List[str]:
        errors = []

        if len(self.subway_path) > 1:
            for i in range(len(self.subway_path) - 1):
                p1, p2 = self.subway_path[i], self.subway_path[i + 1]
                dx, dy = abs(p1[0] - p2[0]), abs(p1[1] - p2[1])
                if dx + dy > 1:
                    errors.append(f"地铁路径不连续：点 {i} 和 {i+1} 之间距离过大")

        for station in self.subway_stations:
            if station not in self.subway_path:
                errors.append(f"地铁站点 {station} 不在路径上")

        def _valid_pos(gx: int, gy: int) -> bool:
            return self.get_room_by_grid(gx, gy) is not None or (gx, gy) in self.single_cells

        if self.start_pos:
            if self.is_obstacle(*self.start_pos):
                errors.append("起始点在障碍物上")
            elif not _valid_pos(*self.start_pos):
                errors.append("起始点不在房间或单格可行走区内")
        if self.target_pos:
            if self.is_obstacle(*self.target_pos):
                errors.append("目标点在障碍物上")
            elif not _valid_pos(*self.target_pos):
                errors.append("目标点不在房间或单格可行走区内")

        return errors
