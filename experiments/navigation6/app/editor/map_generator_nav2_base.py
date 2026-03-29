"""
Navigation2 地图生成器基类（迁移到 Navigation6 内部使用）。
"""
import random
import json
import os
from typing import Dict, Tuple, List, Optional, Set

from experiments.navigation6.app.editor.map_generator_base import NavigationMapGenerator
from shared.common.room import Room
from shared.config import Navigation2Config


class Navigation2MapGenerator(NavigationMapGenerator):
    """城市交通导航地图生成器：地铁路径 + 传送门（边缘）。"""

    def __init__(self, target_entropy: float = 0.5):
        super().__init__(target_entropy)
        self.subway_path: List[Tuple[int, int]] = []
        self.portal_pairs: List[Tuple[Tuple[int, int], Tuple[int, int]]] = []
        self.subway_stations: List[Tuple[int, int]] = []
        self.single_cells: Set[Tuple[int, int]] = set()
        self.single_cell_doors: Dict[Tuple[int, int], Set[str]] = {}
        self.start_pos: Optional[Tuple[int, int]] = None
        self.target_pos: Optional[Tuple[int, int]] = None

    def generate_with_obstacles(
        self,
        map_type: str,
        target_entropy: Optional[float] = None,
        max_attempts: int = 20,
        custom_map_file: Optional[str] = None,
    ):
        if custom_map_file:
            apply_entropy = getattr(self, "_apply_target_entropy_only_for_custom", False)
            result = self.load_from_json(custom_map_file, apply_target_entropy_only=apply_entropy)
            if result:
                return result
            print(f"警告: 无法加载自定义地图 {custom_map_file}，回退到标准地图生成")

        result = super().generate_with_obstacles(map_type, target_entropy, max_attempts)
        self.subway_path = []
        self.portal_pairs = []
        self.subway_stations = []
        self.single_cells = set()
        self.single_cell_doors = {}
        if not self.rooms:
            return result
        start_rid = result[1]
        start_room = self.rooms.get(start_rid)
        target_room = next((r for r in self.rooms.values() if getattr(r, "is_target", False)), None)
        if start_room:
            start_grid = (start_room.logical_pos[0] * 3 + 1, start_room.logical_pos[1] * 3 + 1)
        else:
            start_grid = (1, 1)
        if target_room:
            target_grid = (target_room.logical_pos[0] * 3 + 1, target_room.logical_pos[1] * 3 + 1)
            target_lx, target_ly = target_room.logical_pos
        else:
            target_grid = start_grid
            target_lx, target_ly = 0, 0
        self._build_subway_path()
        self._place_portals(start_grid, target_grid, target_lx, target_ly)
        return result

    def load_from_json(self, filepath: str, apply_target_entropy_only: bool = False) -> Optional[Tuple[Dict[int, Room], int, float, float]]:
        try:
            if not os.path.isabs(filepath):
                maps_dir = os.path.join(os.path.dirname(__file__), "..", "maps")
                filepath = os.path.join(maps_dir, filepath)

            if not os.path.exists(filepath):
                print(f"地图文件不存在: {filepath}")
                return None

            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.rooms.clear()
            self.obstacle_map.clear()
            self.subway_path = []
            self.portal_pairs = []
            self.subway_stations = []
            self.single_cells = set()
            self.single_cell_doors = {}

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

            self.subway_path = [tuple(pos) for pos in data.get("subway_path", [])]
            self.subway_stations = [tuple(pos) for pos in data.get("subway_stations", [])]
            self.portal_pairs = [(tuple(ent), tuple(ext)) for ent, ext in data.get("portal_pairs", [])]
            self.single_cells = {tuple(pos) for pos in data.get("single_cells", [])}
            self.single_cell_doors = {}
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

            total_cells = len(self.rooms) * 9
            start_grid = self.start_pos if self.start_pos else (1, 1)
            target_grid = self.target_pos if self.target_pos else start_grid

            if apply_target_entropy_only:
                path = self._find_path(start_grid, target_grid, use_doors=True)
                if not path:
                    path = [start_grid, target_grid] if start_grid != target_grid else [start_grid]
                protected_set = set(path)
                protected_set.add(start_grid)
                protected_set.add(target_grid)
                protected_set.update(self.subway_path)
                protected_set.update(self.subway_stations)
                protected_set.update(self.single_cells)
                for entrance, exit_pos in self.portal_pairs:
                    protected_set.add(entrance)
                    protected_set.add(exit_pos)
                for pos in path:
                    x, y = pos
                    for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                        protected_set.add((x + dx, y + dy))
                available_positions = []
                for room in self.rooms.values():
                    lx, ly = room.logical_pos
                    for dy in range(3):
                        for dx in range(3):
                            gx, gy = lx * 3 + dx, ly * 3 + dy
                            if (gx, gy) not in protected_set:
                                available_positions.append((gx, gy))
                target_obstacle_count = self._calculate_obstacle_count(total_cells, self.target_entropy)
                if target_obstacle_count > 0 and available_positions:
                    if target_obstacle_count > len(available_positions):
                        target_obstacle_count = len(available_positions)
                    obstacle_positions = self._distribute_obstacles_uniformly(available_positions, target_obstacle_count)
                    for pos in obstacle_positions:
                        self.obstacle_map[pos] = True
            else:
                for pos in data.get("obstacle_map", []):
                    self.obstacle_map[tuple(pos)] = True
                current_obstacle_map = self.obstacle_map.copy()
                current_obstacle_count = len(current_obstacle_map)
                target_obstacle_count = self._calculate_obstacle_count(total_cells, self.target_entropy)

                if target_obstacle_count > current_obstacle_count:
                    path = self._find_path(start_grid, target_grid, use_doors=True)
                    if not path:
                        path = [start_grid, target_grid] if start_grid != target_grid else [start_grid]
                    protected_set = set()
                    protected_set.add(start_grid)
                    protected_set.add(target_grid)
                    protected_set.update(self.subway_path)
                    protected_set.update(self.subway_stations)
                    protected_set.update(self.single_cells)
                    for entrance, exit_pos in self.portal_pairs:
                        protected_set.add(entrance)
                        protected_set.add(exit_pos)
                    protected_set.update(current_obstacle_map.keys())
                    for pos in path:
                        x, y = pos
                        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                            protected_set.add((x + dx, y + dy))
                    available_positions = []
                    for room in self.rooms.values():
                        lx, ly = room.logical_pos
                        for dy in range(3):
                            for dx in range(3):
                                gx, gy = lx * 3 + dx, ly * 3 + dy
                                if (gx, gy) not in protected_set:
                                    available_positions.append((gx, gy))
                    additional_count = target_obstacle_count - current_obstacle_count
                    if additional_count > 0 and len(available_positions) > 0:
                        if additional_count > len(available_positions):
                            additional_count = len(available_positions)
                        obstacle_positions = self._distribute_obstacles_uniformly(available_positions, additional_count)
                        for pos in obstacle_positions:
                            self.obstacle_map[pos] = True
                        print(
                            f"  根据熵值添加了 {len(obstacle_positions)} 个障碍物"
                            f"（目标: {target_obstacle_count}, 已有: {current_obstacle_count}）"
                        )

            obstacle_count = len(self.obstacle_map)
            self.entropy_value = obstacle_count / total_cells if total_cells > 0 else 0.0
            self._build_visibility_network()
            self.complexity_value = self._calculate_complexity()

            start_rid = 0
            if self.start_pos:
                lx, ly = self.start_pos[0] // 3, self.start_pos[1] // 3
                start_rid = ly * 100 + lx
            elif self.rooms:
                start_rid = sorted(self.rooms.keys())[0]

            print(f"成功加载自定义地图: {os.path.basename(filepath)}")
            print(f"  房间数: {len(self.rooms)}")
            print(f"  地铁路径点: {len(self.subway_path)}")
            print(f"  地铁站点: {len(self.subway_stations)}")
            print(f"  传送门: {len(self.portal_pairs)}")
            print(f"  障碍物: {len(self.obstacle_map)}")

            return self.rooms, start_rid, self.entropy_value, self.complexity_value

        except Exception as e:
            print(f"加载地图文件失败: {e}")
            import traceback

            traceback.print_exc()
            return None

    def _sync_single_cell_doors_both_sides(self) -> None:
        opposite = {"north": "south", "south": "north", "east": "west", "west": "east"}
        delta = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
        for (gx, gy), dirs in list(self.single_cell_doors.items()):
            for d in dirs:
                dx, dy = delta[d]
                nb = (gx + dx, gy + dy)
                if nb in self.single_cells:
                    self.single_cell_doors.setdefault(nb, set()).add(opposite[d])

    def _rooms_connected(self, gx1: int, gy1: int, gx2: int, gy2: int) -> bool:
        lx1, ly1 = gx1 // 3, gy1 // 3
        lx2, ly2 = gx2 // 3, gy2 // 3
        rid1 = ly1 * 100 + lx1
        rid2 = ly2 * 100 + lx2
        if rid1 == rid2:
            return True
        if rid1 not in self.rooms or rid2 not in self.rooms:
            return False
        dx, dy = lx2 - lx1, ly2 - ly1
        if abs(dx) + abs(dy) != 1:
            return False
        direction = (dx == 1 and "east") or (dx == -1 and "west") or (dy == 1 and "south") or (dy == -1 and "north")
        r1 = self.rooms[rid1]
        return rid2 in (r1.doors.get(direction) or [])

    def _build_subway_path(self):
        if self.map_type == "Barbell":
            room_sequence = [
                (0, 0),
                (1, 0),
                (0, 1),
                (1, 1),
                (2, 1),
                (3, 1),
                (2, 2),
                (3, 2),
                (4, 2),
                (5, 2),
                (4, 1),
                (5, 1),
                (4, 0),
                (5, 0),
            ]
        elif self.map_type == "Grid":
            room_sequence = [(0, 2), (1, 2), (2, 2), (3, 2), (4, 2)]
        elif self.map_type == "Path":
            room_sequence = [(x, 0) for x in range(6)] + [(x, 1) for x in range(5, -1, -1)] + [(x, 2) for x in range(6)]
        elif self.map_type == "Ladder":
            room_sequence = [(0, 0), (1, 0), (2, 0), (3, 0), (3, 1), (3, 2), (2, 2), (1, 2), (0, 2)]
        else:
            room_sequence = []
        raw = []
        for lx, ly in room_sequence:
            rid = ly * 100 + lx
            if rid in self.rooms:
                gx, gy = lx * 3 + 1, ly * 3 + 1
                if (gx, gy) not in getattr(self, "obstacle_map", {}):
                    raw.append((gx, gy))
        if not raw:
            self.subway_path = []
            return
        valid = [raw[0]]
        for i in range(1, len(raw)):
            if self._rooms_connected(valid[-1][0], valid[-1][1], raw[i][0], raw[i][1]):
                valid.append(raw[i])
            else:
                next_room_id = self._get_room_id_for_grid(raw[i][0], raw[i][1])
                prev_room_id = self._get_room_id_for_grid(valid[-1][0], valid[-1][1])
                if next_room_id and prev_room_id and next_room_id != prev_room_id:
                    valid.append(raw[i])
                elif len(valid) < 4:
                    continue
                else:
                    break
        self.subway_path = valid

    def _get_room_id_for_grid(self, gx: int, gy: int) -> Optional[int]:
        lx, ly = gx // 3, gy // 3
        return ly * 100 + lx

    def _place_portals(self, start_grid: Tuple[int, int], target_grid: Tuple[int, int], target_lx: int, target_ly: int):
        max_lx = max(r.logical_pos[0] for r in self.rooms.values())
        max_ly = max(r.logical_pos[1] for r in self.rooms.values())
        subway_path_set = set(self.subway_path)
        edge_cells = []
        for _rid, room in self.rooms.items():
            lx, ly = room.logical_pos
            if lx != 0 and lx != max_lx and ly != 0 and ly != max_ly:
                continue
            gx, gy = lx * 3 + 1, ly * 3 + 1
            if (gx, gy) in self.obstacle_map:
                continue
            if (gx, gy) == target_grid or (gx, gy) == start_grid:
                continue
            if (gx, gy) in subway_path_set:
                continue
            edge_cells.append((gx, gy, lx, ly))
        if len(edge_cells) < 2:
            self.portal_pairs = []
            return
        min_dist = getattr(Navigation2Config, "PORTAL_MIN_DIST_FROM_TARGET", 2)
        entrance_candidates = [(gx, gy, lx, ly) for gx, gy, lx, ly in edge_cells]
        exit_candidates = [
            (gx, gy, lx, ly)
            for gx, gy, lx, ly in edge_cells
            if abs(lx - target_lx) + abs(ly - target_ly) >= min_dist
        ]
        if not exit_candidates:
            exit_candidates = entrance_candidates
        entrance = random.choice(entrance_candidates)
        entrance_pos = (entrance[0], entrance[1])
        exit_options = [(c[0], c[1]) for c in exit_candidates if (c[0], c[1]) != entrance_pos]
        if not exit_options:
            self.portal_pairs = []
            return
        exit_pos = random.choice(exit_options)
        self.portal_pairs = [(entrance_pos, exit_pos)]
