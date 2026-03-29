"""
Navigation 基础地图生成器（由旧版 navigation 迁移）。
"""
import random
from collections import deque
from typing import Dict, Tuple, List, Optional, Set

from shared.common.map_base import BaseMapGenerator
from shared.common.room import Room
from shared.config import NavigationConfig


class NavigationMapGenerator(BaseMapGenerator):
    """导航地图生成器：障碍物 + 熵 + 可见性 + 复杂度。"""

    def __init__(self, target_entropy: float = 0.5):
        super().__init__()
        self.target_entropy: float = target_entropy
        self.map_type: str = ""
        self.obstacle_map: Dict[Tuple[int, int], bool] = {}
        self.entropy_value: float = 0.0
        self.complexity_value: float = 0.0
        self.visibility_network: Dict[Tuple[int, int], Set[Tuple[int, int]]] = {}

    def generate_with_obstacles(
        self,
        map_type: str,
        target_entropy: Optional[float] = None,
        max_attempts: int = 20,
    ) -> Tuple[Dict[int, Room], int, float, float]:
        if target_entropy is not None:
            self.target_entropy = target_entropy
        self.map_type = map_type

        rooms, start_rid = self.generate(map_type)

        total_cells = len(self.rooms) * 9
        target_obstacle_count = self._calculate_obstacle_count(total_cells, self.target_entropy)

        start_room = self.rooms.get(start_rid)
        if start_room:
            sx, sy = start_room.logical_pos
            start_grid = (sx * 3 + 1, sy * 3 + 1)
        else:
            start_grid = (1, 1)

        target_room = self._pick_target_room(start_rid)
        if target_room:
            tx, ty = target_room.logical_pos
            target_grid = (tx * 3 + 1, ty * 3 + 1)
            target_room.is_target = True
        else:
            target_grid = start_grid

        self.obstacle_map.clear()
        for _attempt in range(max_attempts):
            self.obstacle_map.clear()
            path = self._find_path(start_grid, target_grid, use_doors=True)
            if not path:
                path = [start_grid, target_grid] if start_grid != target_grid else [start_grid]

            protected: Set[Tuple[int, int]] = set(path)
            protected.add(start_grid)
            protected.add(target_grid)
            for pos in path:
                x, y = pos
                for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                    protected.add((x + dx, y + dy))

            available = []
            for room in self.rooms.values():
                lx, ly = room.logical_pos
                for dy in range(3):
                    for dx in range(3):
                        gx, gy = lx * 3 + dx, ly * 3 + dy
                        if (gx, gy) not in protected:
                            available.append((gx, gy))

            if target_obstacle_count > 0 and available:
                count = min(target_obstacle_count, len(available))
                positions = self._distribute_obstacles_uniformly(available, count)
                for pos in positions:
                    self.obstacle_map[pos] = True

            verify = self._find_path(start_grid, target_grid, use_doors=True)
            if verify:
                break

        obstacle_count = len(self.obstacle_map)
        self.entropy_value = obstacle_count / total_cells if total_cells > 0 else 0.0

        self._build_visibility_network()
        self.complexity_value = self._calculate_complexity()

        return self.rooms, start_rid, self.entropy_value, self.complexity_value

    def _calculate_obstacle_count(self, total_cells: int, target_entropy: float) -> int:
        if target_entropy <= 0:
            return 0
        count = int(total_cells * target_entropy)
        return max(0, min(count, total_cells - 2))

    def _distribute_obstacles_uniformly(self, available: List[Tuple[int, int]], count: int) -> List[Tuple[int, int]]:
        if count >= len(available):
            return list(available)
        return random.sample(available, count)

    def _find_path(
        self,
        start: Tuple[int, int],
        target: Tuple[int, int],
        use_doors: bool = True,
    ) -> Optional[List[Tuple[int, int]]]:
        if start == target:
            return [start]

        visited: Set[Tuple[int, int]] = {start}
        queue: deque = deque()
        queue.append((start, [start]))

        while queue:
            (cx, cy), path = queue.popleft()
            for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                nx, ny = cx + dx, cy + dy
                if (nx, ny) in visited:
                    continue
                if (nx, ny) in self.obstacle_map:
                    continue
                if not self._grid_in_any_room(nx, ny):
                    continue
                if use_doors and not self._can_move_between(cx, cy, nx, ny):
                    continue
                visited.add((nx, ny))
                new_path = path + [(nx, ny)]
                if (nx, ny) == target:
                    return new_path
                queue.append(((nx, ny), new_path))
        return None

    def _grid_in_any_room(self, gx: int, gy: int) -> bool:
        lx, ly = gx // 3, gy // 3
        rid = ly * 100 + lx
        return rid in self.rooms

    def _can_move_between(self, x1: int, y1: int, x2: int, y2: int) -> bool:
        lx1, ly1 = x1 // 3, y1 // 3
        lx2, ly2 = x2 // 3, y2 // 3
        rid1 = ly1 * 100 + lx1
        rid2 = ly2 * 100 + lx2

        if rid1 == rid2:
            return True

        if rid1 not in self.rooms or rid2 not in self.rooms:
            return False

        dx, dy = lx2 - lx1, ly2 - ly1
        if abs(dx) + abs(dy) != 1:
            return False

        if dx == 1:
            direction = "east"
        elif dx == -1:
            direction = "west"
        elif dy == 1:
            direction = "south"
        else:
            direction = "north"

        room1 = self.rooms[rid1]
        neighbors = room1.doors.get(direction, [])
        if isinstance(neighbors, list):
            return rid2 in neighbors
        return neighbors == rid2

    def _build_visibility_network(self):
        self.visibility_network = {}
        vis_range = getattr(NavigationConfig, "VISIBILITY_RANGE", 5)

        walkable = set()
        for room in self.rooms.values():
            lx, ly = room.logical_pos
            for dy in range(3):
                for dx in range(3):
                    gx, gy = lx * 3 + dx, ly * 3 + dy
                    if (gx, gy) not in self.obstacle_map:
                        walkable.add((gx, gy))

        for cell in walkable:
            visible: Set[Tuple[int, int]] = set()
            cx, cy = cell
            for other in walkable:
                ox, oy = other
                if abs(ox - cx) + abs(oy - cy) <= vis_range:
                    visible.add(other)
            self.visibility_network[cell] = visible

    def _calculate_complexity(self) -> float:
        if not self.visibility_network:
            return 0.0
        total_visible = sum(len(v) for v in self.visibility_network.values())
        avg_visible = total_visible / len(self.visibility_network)
        if avg_visible <= 0:
            return 1.0
        return 1.0 / avg_visible

    def _pick_target_room(self, start_rid: int) -> Optional[Room]:
        if not self.rooms:
            return None

        start_room = self.rooms.get(start_rid)
        if not start_room:
            return None

        sx, sy = start_room.logical_pos
        best_room = None
        best_dist = -1

        for rid, room in self.rooms.items():
            if rid == start_rid:
                continue
            rx, ry = room.logical_pos
            dist = abs(rx - sx) + abs(ry - sy)
            if dist > best_dist:
                best_dist = dist
                best_room = room

        return best_room
