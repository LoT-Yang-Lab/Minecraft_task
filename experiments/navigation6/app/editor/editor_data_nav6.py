"""
Navigation6 地图编辑器数据模型：单格 + 公交/地铁/轻轨线路（路径+站点）；不再使用房间/门/传送门。
"""
import math
from typing import Dict, Set, Optional, Tuple, List, Any, Union

from experiments.navigation6.app.editor.editor_data_base import EditorMapDataNav2
from shared.common.room import Room

# 八方向：四正交 + 四对角线
REVERSE_DIRS_8 = {
    "north": "south", "south": "north", "east": "west", "west": "east",
    "northwest": "southeast", "southeast": "northwest",
    "northeast": "southwest", "southwest": "northeast",
}
DX_DY_8 = {
    "north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0),
    "northwest": (-1, -1), "northeast": (1, -1), "southwest": (-1, 1), "southeast": (1, 1),
}
ALL_EDITOR_DIRECTIONS = list(DX_DY_8.keys())

# 角度（度）→ 方向名：0=东, 90=北, 180=西, 270=南，四象限为东北/西北/西南/东南
ANGLE_TO_DIRECTION = {
    0: "east", 45: "northeast", 90: "north", 135: "northwest",
    180: "west", 225: "southwest", 270: "south", 315: "southeast",
}


def direction_from_room_centers(lx1: int, ly1: int, lx2: int, ly2: int) -> Optional[str]:
    """
    从房间 A 中心 (lx1, ly1) 指向房间 B 中心 (lx2, ly2) 的向量，量化为 8 方向。
    约定：0°=东，90°=北，180°=西，270°=南；y 轴向下故用 atan2(-dy, dx)。
    若两点重合返回 None。
    """
    return direction_from_points(float(lx1), float(ly1), float(lx2), float(ly2))


def direction_from_points(x1: float, y1: float, x2: float, y2: float) -> Optional[str]:
    """
    从 (x1,y1) 指向 (x2,y2) 的向量量化为 8 方向；适用于房间中心或单格中心（可传小数）。
    若两点重合返回 None。
    """
    dx, dy = x2 - x1, y2 - y1
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return None
    angle_rad = math.atan2(-dy, dx)
    angle_deg = (math.degrees(angle_rad) + 360) % 360
    quantized = round(angle_deg / 45) * 45 % 360
    return ANGLE_TO_DIRECTION.get(quantized, "east")


def _empty_nav6_line() -> Dict[str, Any]:
    """单条公交/地铁/轻轨线路的初始结构（每段弧度 + 是否强制直线绘制）。"""
    return {"path": [], "stations": set(), "segment_curve": [], "segment_straight": []}


class EditorMapDataNav6(EditorMapDataNav2):
    """三类公共交通线路，每类可多线；当前编辑类别由 transit_edit_kind 指定。"""

    def __init__(self):
        super().__init__()
        self.rooms.clear()
        self.portal_pairs.clear()
        self.single_cell_doors.clear()
        self.nav6_transit: Dict[str, List[Dict[str, Any]]] = {
            "bus": [_empty_nav6_line()],
            "metro": [_empty_nav6_line()],
            "light_rail": [_empty_nav6_line()],
        }
        self.transit_edit_kind: str = "bus"
        self.current_subway_line_index: int = 0
        self.subway_lines: List[Dict[str, Any]] = []
        self._rebuild_subway_lines_alias()
        self._sync_current_line_to_base()

    @staticmethod
    def ensure_segment_curve_length(line: Dict[str, Any]) -> None:
        """segment_curve / segment_straight 与 path 段数对齐；弧度 0=自动，straight=True 时该段只画直线。"""
        path = line.get("path", [])
        n = max(0, len(path) - 1)
        sc = line.get("segment_curve")
        if not isinstance(sc, list):
            sc = []
        if len(sc) < n:
            sc = list(sc) + [0.0] * (n - len(sc))
        elif len(sc) > n:
            sc = sc[:n]
        line["segment_curve"] = sc
        st = line.get("segment_straight")
        if not isinstance(st, list):
            st = []
        st_bool = [bool(x) for x in st[:n]]
        if len(st_bool) < n:
            st_bool.extend([False] * (n - len(st_bool)))
        else:
            st_bool = st_bool[:n]
        line["segment_straight"] = st_bool

    def _rebuild_subway_lines_alias(self) -> None:
        """供绘制/兼容：按 bus → metro → light_rail 展平，并附带 kind。"""
        self.subway_lines = []
        for kind, lines in (("bus", self.nav6_transit["bus"]), ("metro", self.nav6_transit["metro"]), ("light_rail", self.nav6_transit["light_rail"])):
            for line in lines:
                self.ensure_segment_curve_length(line)
                self.subway_lines.append({
                    "path": list(line.get("path", [])),
                    "stations": set(line.get("stations", set())),
                    "kind": kind,
                    "segment_curve": list(line.get("segment_curve", [])),
                    "segment_straight": list(line.get("segment_straight", [])),
                })

    def _flat_index_to_kind_line(self, flat_idx: int) -> Optional[Tuple[str, int]]:
        if flat_idx < 0:
            return None
        i = 0
        for kind in ("bus", "metro", "light_rail"):
            for li, _line in enumerate(self.nav6_transit[kind]):
                if i == flat_idx:
                    return kind, li
                i += 1
        return None

    def _kind_line_to_flat_index(self, kind: str, line_idx: int) -> int:
        flat = 0
        for k in ("bus", "metro", "light_rail"):
            for li, _ in enumerate(self.nav6_transit[k]):
                if k == kind and li == line_idx:
                    return flat
                flat += 1
        return 0

    def set_transit_edit_kind(self, kind: str) -> bool:
        if kind not in self.nav6_transit:
            return False
        self.transit_edit_kind = kind
        self.current_subway_line_index = min(self.current_subway_line_index, max(0, len(self.nav6_transit[kind]) - 1))
        self._sync_current_line_to_base()
        return True

    def _get_edit_line(self) -> Optional[Dict[str, Any]]:
        lines = self.nav6_transit.get(self.transit_edit_kind, [])
        if 0 <= self.current_subway_line_index < len(lines):
            return lines[self.current_subway_line_index]
        return None

    def _sync_current_line_to_base(self) -> None:
        line = self._get_edit_line()
        if line:
            self.subway_path = list(line.get("path", []))
            self.subway_stations = set(line.get("stations", set()))
        else:
            self.subway_path = []
            self.subway_stations = set()

    def _sync_base_to_current_line(self) -> None:
        line = self._get_edit_line()
        if line:
            line["path"] = list(self.subway_path)
            line["stations"] = set(self.subway_stations)
            self.ensure_segment_curve_length(line)
        self._rebuild_subway_lines_alias()

    def add_subway_path_point(self, gx: int, gy: int) -> bool:
        """在当前线路末尾添加地铁路径点（支持环线）。"""
        self._sync_current_line_to_base()
        ok = super().add_subway_path_point(gx, gy)
        self._sync_base_to_current_line()
        return ok

    def remove_subway_path_point(self, gx: int, gy: int) -> bool:
        """从当前线路移除地铁路径点。"""
        self._sync_current_line_to_base()
        ok = super().remove_subway_path_point(gx, gy)
        self._sync_base_to_current_line()
        return ok

    def toggle_subway_station(self, gx: int, gy: int) -> bool:
        """在当前线路上切换站点。

        站点通常须在路径上；若格点已标为单格可行走，则允许在此设站并自动将该格加入当前线路路径，
        便于同一换乘格上为公交/地铁/轻轨分别设站（各线路独立路径与站点集合）。
        """
        self._sync_current_line_to_base()
        pos = (gx, gy)
        if pos not in self.subway_path:
            if pos not in self.single_cells:
                return False
            if not super().add_subway_path_point(gx, gy):
                if pos not in self.subway_path:
                    return False
        ok = super().toggle_subway_station(gx, gy)
        self._sync_base_to_current_line()
        return ok

    def calculate_map_bounds(self) -> Tuple[int, int, int, int]:
        """含三类线路路径格点，避免仅线路时边界为空。"""
        all_x: List[int] = []
        all_y: List[int] = []
        for room in self.rooms.values():
            all_x.append(room.logical_pos[0])
            all_y.append(room.logical_pos[1])
        for gx, gy in self.single_cells:
            all_x.append(gx // 3)
            all_y.append(gy // 3)
        for kind in ("bus", "metro", "light_rail"):
            for line in self.nav6_transit.get(kind, []):
                for gx, gy in line.get("path", []):
                    all_x.append(gx // 3)
                    all_y.append(gy // 3)
                for gx, gy in line.get("stations", set()):
                    all_x.append(gx // 3)
                    all_y.append(gy // 3)
        if not all_x and not all_y:
            return 0, 0, 0, 0
        return min(all_x), max(all_x), min(all_y), max(all_y)

    def remove_room(self, rid: int) -> bool:
        return False

    def add_subway_line(self) -> int:
        """在当前交通类别下新增一条线路，返回该类内的线索引。"""
        self._sync_base_to_current_line()
        self.nav6_transit[self.transit_edit_kind].append(_empty_nav6_line())
        self.current_subway_line_index = len(self.nav6_transit[self.transit_edit_kind]) - 1
        self._sync_current_line_to_base()
        self._rebuild_subway_lines_alias()
        return self.current_subway_line_index

    def remove_subway_line(self, line_index: int) -> bool:
        """删除当前交通类别下指定索引的线路。"""
        lines = self.nav6_transit[self.transit_edit_kind]
        if line_index < 0 or line_index >= len(lines) or len(lines) <= 1:
            return False
        self._sync_base_to_current_line()
        lines.pop(line_index)
        if self.current_subway_line_index >= len(lines):
            self.current_subway_line_index = max(0, len(lines) - 1)
        self._sync_current_line_to_base()
        self._rebuild_subway_lines_alias()
        return True

    def set_current_subway_line(self, line_index: int) -> bool:
        lines = self.nav6_transit[self.transit_edit_kind]
        if line_index < 0 or line_index >= len(lines):
            return False
        self._sync_base_to_current_line()
        self.current_subway_line_index = line_index
        self._sync_current_line_to_base()
        return True

    @staticmethod
    def get_room_center_logical_from_room(room: Room) -> Tuple[int, int]:
        """房间逻辑中心用于角度计算，用 (lx, ly) 代表房间位置。"""
        return room.logical_pos

    def get_room_center_logical(self, rid: int) -> Optional[Tuple[int, int]]:
        """返回房间的逻辑中心 (lx, ly)，用于角度计算。"""
        room = self.rooms.get(rid)
        return room.logical_pos if room else None

    def get_segment_curve_value(self, flat_line_idx: int, seg_idx: int) -> Optional[float]:
        kl = self._flat_index_to_kind_line(flat_line_idx)
        if kl is None:
            return None
        kind, li = kl
        line = self.nav6_transit[kind][li]
        self.ensure_segment_curve_length(line)
        sc = line["segment_curve"]
        if seg_idx < 0 or seg_idx >= len(sc):
            return None
        return float(sc[seg_idx])

    def set_segment_curve_value(self, flat_line_idx: int, seg_idx: int, value: float) -> bool:
        kl = self._flat_index_to_kind_line(flat_line_idx)
        if kl is None:
            return False
        kind, li = kl
        line = self.nav6_transit[kind][li]
        self.ensure_segment_curve_length(line)
        sc = line["segment_curve"]
        if seg_idx < 0 or seg_idx >= len(sc):
            return False
        sc[seg_idx] = float(value)
        line["segment_straight"][seg_idx] = False
        self._rebuild_subway_lines_alias()
        return True

    def get_segment_straight(self, flat_line_idx: int, seg_idx: int) -> Optional[bool]:
        kl = self._flat_index_to_kind_line(flat_line_idx)
        if kl is None:
            return None
        kind, li = kl
        line = self.nav6_transit[kind][li]
        self.ensure_segment_curve_length(line)
        st = line["segment_straight"]
        if seg_idx < 0 or seg_idx >= len(st):
            return None
        return bool(st[seg_idx])

    def set_segment_straight(self, flat_line_idx: int, seg_idx: int, straight: bool) -> bool:
        kl = self._flat_index_to_kind_line(flat_line_idx)
        if kl is None:
            return False
        kind, li = kl
        line = self.nav6_transit[kind][li]
        self.ensure_segment_curve_length(line)
        st = line["segment_straight"]
        if seg_idx < 0 or seg_idx >= len(st):
            return False
        st[seg_idx] = bool(straight)
        self._rebuild_subway_lines_alias()
        return True

    def set_door_to_room(self, source_rid: int, direction: str, target_rid: int) -> bool:
        """设置源房间某方向的门线指向目标房间（不要求相邻）。可选：在目标房间设反向门。"""
        if source_rid not in self.rooms or target_rid not in self.rooms:
            return False
        if direction not in ALL_EDITOR_DIRECTIONS:
            return False
        room1, room2 = self.rooms[source_rid], self.rooms[target_rid]
        if room1.is_obstacle or room2.is_obstacle:
            return False
        room1.add_door(direction, target_rid)
        rev = REVERSE_DIRS_8.get(direction)
        if rev is not None:
            room2.add_door(rev, source_rid)
        return True

    def remove_door(self, source_rid: int, direction: str, target_rid: Optional[int] = None) -> bool:
        """移除源房间某方向的门线（若指定 target_rid 则只移该条）；若目标房间有反向门则一并移除。"""
        if source_rid not in self.rooms:
            return False
        room = self.rooms[source_rid]
        if not room.doors.get(direction):
            return False
        if target_rid is not None and target_rid not in (room.doors.get(direction) or []):
            return False
        to_remove = target_rid if target_rid is not None else room.get_neighbor_id(direction)
        room.remove_door(direction, to_remove)
        if to_remove is not None and to_remove in self.rooms:
            rev = REVERSE_DIRS_8.get(direction)
            if rev is not None:
                self.rooms[to_remove].remove_door(rev, source_rid)
        return True

    def add_door_bidirectional(self, rid1: int, rid2: int, direction: str) -> bool:
        """添加双向门线；不要求两房间相邻，只要均在 rooms 内即可。"""
        if rid1 not in self.rooms or rid2 not in self.rooms:
            return False
        if direction not in REVERSE_DIRS_8:
            return False
        room1, room2 = self.rooms[rid1], self.rooms[rid2]
        if room1.is_obstacle or room2.is_obstacle:
            return False
        rev = REVERSE_DIRS_8[direction]
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
        rev = REVERSE_DIRS_8.get(direction)
        if rev is None:
            room.remove_door(direction)
            return True
        room.remove_door(direction, neighbor_rid)
        self.rooms[neighbor_rid].remove_door(rev, rid)
        return True

    def toggle_door(self, x: int, y: int, direction: str) -> bool:
        rid = y * 100 + x
        if rid not in self.rooms:
            return False
        if direction not in DX_DY_8:
            return False
        room = self.rooms[rid]
        dx, dy = DX_DY_8[direction]
        neighbor_x, neighbor_y = x + dx, y + dy
        neighbor_rid = neighbor_y * 100 + neighbor_x
        if neighbor_rid not in self.rooms:
            return False
        if direction in room.doors:
            return self.remove_door_bidirectional(rid, direction)
        return self.add_door_bidirectional(rid, neighbor_rid, direction)

    # 单格门线：与房间一致，方向→目标（房间 rid 或单格 (gx,gy)），不要求相邻
    # single_cell_doors: Dict[Tuple[int,int], Dict[str, Union[int, Tuple[int,int]]]]

    def set_single_cell_door_to(self, gx: int, gy: int, direction: str, target: Union[int, Tuple[int, int]]) -> bool:
        """设置单格 (gx,gy) 某方向门线指向目标（可同方向多目标，追加到列表）。"""
        pos = (gx, gy)
        if pos not in self.single_cells or direction not in ALL_EDITOR_DIRECTIONS:
            return False
        if isinstance(target, int):
            if target not in self.rooms:
                return False
        else:
            if target not in self.single_cells:
                return False
        if not isinstance(self.single_cell_doors.get(pos), dict):
            self.single_cell_doors[pos] = {}
        doors = self.single_cell_doors[pos]
        lst = doors.get(direction)
        if not isinstance(lst, list):
            lst = [lst] if lst is not None else []
        if target in lst:
            return True
        lst.append(target)
        doors[direction] = lst
        rev = REVERSE_DIRS_8.get(direction)
        if rev is not None and isinstance(target, tuple):
            tpos = self.single_cell_doors.setdefault(target, {})
            trev = tpos.get(rev)
            if not isinstance(trev, list):
                trev = [trev] if trev is not None else []
            if pos not in trev:
                trev.append(pos)
            tpos[rev] = trev
        return True

    def remove_single_cell_door(self, gx: int, gy: int, direction: str, target: Optional[Union[int, Tuple[int, int]]] = None) -> bool:
        """移除单格某方向的门线。target 指定时只删该目标，否则删该方向全部。"""
        pos = (gx, gy)
        if pos not in self.single_cells:
            return False
        doors = self.single_cell_doors.get(pos)
        if not doors or direction not in doors:
            return False
        if isinstance(doors, set):
            doors.discard(direction)
            if not doors:
                del self.single_cell_doors[pos]
            return True
        lst = doors[direction]
        if not isinstance(lst, list):
            lst = [lst]
        if target is not None:
            if target not in lst:
                return False
            lst = [t for t in lst if t != target]
        else:
            lst = []
        if not lst:
            doors.pop(direction)
            if not doors:
                del self.single_cell_doors[pos]
        else:
            doors[direction] = lst
        # 若目标为单格且存在反向门，从目标侧移除本条
        if target is not None and isinstance(target, tuple) and target in self.single_cell_doors:
            rev = REVERSE_DIRS_8.get(direction)
            tr = self.single_cell_doors[target]
            if isinstance(tr, dict) and rev:
                trev = tr.get(rev)
                if isinstance(trev, list) and pos in trev:
                    trev = [t for t in trev if t != pos]
                    if not trev:
                        tr.pop(rev, None)
                    else:
                        tr[rev] = trev
                elif trev == pos:
                    tr.pop(rev, None)
                if not tr:
                    del self.single_cell_doors[target]
        return True

    def get_single_cell_doors(self, gx: int, gy: int) -> Dict[str, List[Union[int, Tuple[int, int]]]]:
        """返回单格门线：方向 → 目标列表 [rid 或 (gx,gy), ...]。"""
        val = self.single_cell_doors.get((gx, gy), {})
        if not isinstance(val, dict):
            return {}
        return {d: (v if isinstance(v, list) else [v]) for d, v in val.items()}

    def toggle_single_cell_door(self, gx: int, gy: int, direction: str) -> bool:
        """兼容旧接口：若该方向已有门则移除，否则按相邻格设目标（若相邻格为单格）。"""
        pos = (gx, gy)
        if pos not in self.single_cells or direction not in ALL_EDITOR_DIRECTIONS:
            return False
        doors = self.single_cell_doors.get(pos, {})
        if isinstance(doors, set):
            self.single_cell_doors[pos] = {
                d: (pos[0] + DX_DY_8[d][0], pos[1] + DX_DY_8[d][1])
                for d in doors if d in DX_DY_8 and (pos[0] + DX_DY_8[d][0], pos[1] + DX_DY_8[d][1]) in self.single_cells
            }
            doors = self.single_cell_doors[pos]
        if direction in doors:
            return self.remove_single_cell_door(gx, gy, direction)
        dx, dy = DX_DY_8[direction]
        neighbor = (gx + dx, gy + dy)
        if neighbor in self.single_cells:
            return self.set_single_cell_door_to(gx, gy, direction, neighbor)
        return False

    def _sync_single_cell_doors_both_sides(self) -> None:
        """旧格式加载后不再依赖此方法；保留空实现避免报错。"""
        pass

    def from_dict(self, data: Dict[str, Any]) -> bool:
        try:
            self.rooms.clear()
            self.obstacle_map.clear()
            self.subway_path.clear()
            self.subway_stations.clear()
            self.subway_lines = []
            self.nav6_transit = {
                "bus": [_empty_nav6_line()],
                "metro": [_empty_nav6_line()],
                "light_rail": [_empty_nav6_line()],
            }
            self.transit_edit_kind = "bus"
            self.current_subway_line_index = 0
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
                doors_val = room_data.get("doors")
                if isinstance(doors_val, dict):
                    for direction, targets in doors_val.items():
                        if direction not in ALL_EDITOR_DIRECTIONS:
                            continue
                        for rid in (targets if isinstance(targets, list) else [targets]):
                            if rid in self.rooms:
                                room.add_door(direction, rid)
                elif isinstance(doors_val, list):
                    x, y = room.logical_pos
                    for direction in doors_val:
                        if direction not in DX_DY_8:
                            continue
                        dx, dy = DX_DY_8[direction]
                        neighbor_rid = (y + dy) * 100 + (x + dx)
                        if neighbor_rid in self.rooms:
                            room.add_door(direction, neighbor_rid)

            for pos in data.get("obstacle_map", []):
                self.obstacle_map[tuple(pos)] = True
            def _parse_lines(key: str) -> List[Dict[str, Any]]:
                raw = data.get(key, [])
                if not isinstance(raw, list) or not raw:
                    return [_empty_nav6_line()]
                out: List[Dict[str, Any]] = []
                for line in raw:
                    if not isinstance(line, dict):
                        continue
                    path = [tuple(p) for p in line.get("path", [])]
                    stations = {tuple(p) for p in line.get("stations", [])}
                    sc_raw = line.get("segment_curve")
                    if isinstance(sc_raw, list):
                        segment_curve = [float(x) for x in sc_raw]
                    else:
                        segment_curve = []
                    ss_raw = line.get("segment_straight")
                    if isinstance(ss_raw, list):
                        segment_straight = [bool(x) for x in ss_raw]
                    else:
                        segment_straight = []
                    row = {
                        "path": path,
                        "stations": stations,
                        "segment_curve": segment_curve,
                        "segment_straight": segment_straight,
                    }
                    EditorMapDataNav6.ensure_segment_curve_length(row)
                    out.append(row)
                return out if out else [_empty_nav6_line()]

            if data.get("bus_lines") is not None or data.get("metro_lines") is not None or data.get("light_rail_lines") is not None:
                self.nav6_transit["bus"] = _parse_lines("bus_lines")
                self.nav6_transit["metro"] = _parse_lines("metro_lines")
                self.nav6_transit["light_rail"] = _parse_lines("light_rail_lines")
                self.current_subway_line_index = 0
                self.transit_edit_kind = "bus"
                self._rebuild_subway_lines_alias()
                self._sync_current_line_to_base()
            elif "subway_lines" in data and isinstance(data["subway_lines"], list) and len(data["subway_lines"]) > 0:
                self.nav6_transit["metro"] = []
                for line in data["subway_lines"]:
                    path = [tuple(p) for p in line.get("path", [])]
                    stations = {tuple(p) for p in line.get("stations", [])}
                    sc_raw = line.get("segment_curve")
                    sc = [float(x) for x in sc_raw] if isinstance(sc_raw, list) else []
                    ss_raw = line.get("segment_straight")
                    ss = [bool(x) for x in ss_raw] if isinstance(ss_raw, list) else []
                    row = {"path": path, "stations": stations, "segment_curve": sc, "segment_straight": ss}
                    EditorMapDataNav6.ensure_segment_curve_length(row)
                    self.nav6_transit["metro"].append(row)
                if not self.nav6_transit["metro"]:
                    self.nav6_transit["metro"] = [_empty_nav6_line()]
                self.current_subway_line_index = 0
                self.transit_edit_kind = "metro"
                self._rebuild_subway_lines_alias()
                self._sync_current_line_to_base()
            else:
                self.subway_path = [tuple(p) for p in data.get("subway_path", [])]
                self.subway_stations = {tuple(p) for p in data.get("subway_stations", [])}
                row = {
                    "path": list(self.subway_path),
                    "stations": set(self.subway_stations),
                    "segment_curve": [],
                    "segment_straight": [],
                }
                EditorMapDataNav6.ensure_segment_curve_length(row)
                self.nav6_transit["metro"] = [row]
                self.current_subway_line_index = 0
                self.transit_edit_kind = "metro"
                self._rebuild_subway_lines_alias()
                self._sync_current_line_to_base()
            self.portal_pairs = []
            self.single_cells = {tuple(p) for p in data.get("single_cells", [])}
            self.single_cell_doors.clear()
            def _append_cell_door(p: Tuple[int, int], direction: str, tgt: Union[int, Tuple[int, int]]) -> None:
                self.single_cell_doors.setdefault(p, {})
                lst = self.single_cell_doors[p].get(direction)
                if lst is None:
                    self.single_cell_doors[p][direction] = [tgt]
                elif isinstance(lst, list):
                    if tgt not in lst:
                        lst.append(tgt)
                else:
                    self.single_cell_doors[p][direction] = [lst, tgt] if lst != tgt else [lst]
            _nav6_json = (
                data.get("bus_lines") is not None
                or data.get("metro_lines") is not None
                or data.get("light_rail_lines") is not None
            )
            for item in ([] if _nav6_json else data.get("single_cell_doors", [])):
                if len(item) >= 3:
                    gx, gy, d = item[0], item[1], item[2]
                    pos = (gx, gy)
                    if pos not in self.single_cells or d not in ALL_EDITOR_DIRECTIONS:
                        continue
                    if len(item) >= 5 and item[3] == "room":
                        rid = item[4]
                        if rid in self.rooms:
                            _append_cell_door(pos, d, rid)
                    elif len(item) >= 6 and item[3] == "cell":
                        gx2, gy2 = item[4], item[5]
                        tpos = (gx2, gy2)
                        if tpos in self.single_cells:
                            _append_cell_door(pos, d, tpos)
                            rev = REVERSE_DIRS_8.get(d)
                            if rev is not None:
                                _append_cell_door(tpos, rev, pos)
                    else:
                        dx, dy = DX_DY_8.get(d, (0, 0))
                        tpos = (gx + dx, gy + dy)
                        if tpos in self.single_cells:
                            _append_cell_door(pos, d, tpos)
                            rev = REVERSE_DIRS_8.get(d)
                            if rev is not None:
                                _append_cell_door(tpos, rev, pos)
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

    def _serialize_single_cell_doors(self) -> List[Any]:
        """单格门线：每条存为 [gx, gy, direction, "room", rid] 或 [gx, gy, direction, "cell", gx2, gy2]，同方向多目标多条。"""
        out = []
        for (gx, gy), dirs in self.single_cell_doors.items():
            if not isinstance(dirs, dict):
                continue
            for d, target in dirs.items():
                targets = target if isinstance(target, list) else [target]
                for t in targets:
                    if isinstance(t, int):
                        out.append([gx, gy, d, "room", t])
                    elif isinstance(t, tuple) and len(t) == 2:
                        out.append([gx, gy, d, "cell", t[0], t[1]])
        return out

    def to_dict(self) -> Dict[str, Any]:
        self._sync_base_to_current_line()

        def _pack(kind: str) -> List[Dict[str, Any]]:
            packed: List[Dict[str, Any]] = []
            for line in self.nav6_transit[kind]:
                self.ensure_segment_curve_length(line)
                path = [[gx, gy] for gx, gy in line["path"]]
                stations = [[gx, gy] for gx, gy in line["stations"]]
                d: Dict[str, Any] = {"path": path, "stations": stations}
                sc = line.get("segment_curve", [])
                if isinstance(sc, list) and sc and any(abs(float(x)) > 1e-9 for x in sc):
                    d["segment_curve"] = [round(float(x), 4) for x in sc]
                st = line.get("segment_straight", [])
                if isinstance(st, list) and st and any(st):
                    d["segment_straight"] = [bool(x) for x in st]
                packed.append(d)
            return packed

        return {
            "schema": "navigation6",
            "version": "1.0",
            "metadata": self.metadata,
            "rooms": [],
            "obstacle_map": [[gx, gy] for gx, gy in self.obstacle_map.keys()],
            "bus_lines": _pack("bus"),
            "metro_lines": _pack("metro"),
            "light_rail_lines": _pack("light_rail"),
            "single_cells": [[gx, gy] for gx, gy in self.single_cells],
            "start_pos": list(self.start_pos) if self.start_pos else None,
            "target_pos": list(self.target_pos) if self.target_pos else None,
        }
