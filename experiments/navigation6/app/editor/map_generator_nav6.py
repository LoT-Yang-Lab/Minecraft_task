"""
Navigation6 地图生成器：仅单格可行走 + 公交/地铁/轻轨三类线路（路径 + 站点）。
JSON 键：bus_lines、metro_lines、light_rail_lines；每项 {path, stations}。
内部拼成 subway_lines 列表供 GameNavigation6 复用列车与即时到站逻辑，并维护 transit_modes。
"""
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from experiments.navigation6.app.editor.map_generator_nav2_base import Navigation2MapGenerator
from shared.common.room import Room

from experiments.navigation6.app.common.transit_curve_geometry import ensure_transit_segment_metadata


def _normalize_transit_line(raw: Dict[str, Any]) -> Dict[str, Any]:
    path = [tuple(p) for p in raw.get("path", [])]
    stations = [tuple(s) for s in raw.get("stations", [])]
    st_set = set(stations)
    station_indices = [i for i, pos in enumerate(path) if pos in st_set]
    if path and 0 not in station_indices:
        station_indices.insert(0, 0)
    if path and len(path) > 1 and (len(path) - 1) not in station_indices:
        station_indices.append(len(path) - 1)
    station_indices = sorted(set(station_indices))
    sc_raw = raw.get("segment_curve")
    sc = [float(x) for x in sc_raw] if isinstance(sc_raw, list) else []
    ss_raw = raw.get("segment_straight")
    ss = [bool(x) for x in ss_raw] if isinstance(ss_raw, list) else []
    row: Dict[str, Any] = {
        "path": path,
        "station_indices": station_indices,
        "segment_curve": sc,
        "segment_straight": ss,
    }
    ensure_transit_segment_metadata(row)
    return row


class Navigation6MapGenerator(Navigation2MapGenerator):
    """Navigation6：无房间/门/传送门；三类公共交通线路。"""

    def load_from_json(self, filepath: str, apply_target_entropy_only: bool = False) -> Optional[Tuple[Dict[int, Room], int, float, float]]:
        try:
            if not os.path.isabs(filepath):
                from experiments.navigation6.app.paths import resolve_map_path
                filepath = resolve_map_path(filepath)

            if not os.path.exists(filepath):
                print(f"地图文件不存在: {filepath}")
                return None

            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.rooms.clear()
            self.obstacle_map.clear()
            self.subway_path = []
            self.subway_stations = []
            self.subway_lines = []
            self.portal_pairs = []
            self.single_cells = set()
            self.single_cell_doors = {}
            self.transit_modes: List[str] = []
            self.bus_lines: List[Dict[str, Any]] = []
            self.metro_lines: List[Dict[str, Any]] = []
            self.light_rail_lines: List[Dict[str, Any]] = []

            for raw in data.get("bus_lines", []) or []:
                if isinstance(raw, dict):
                    norm = _normalize_transit_line(raw)
                    self.bus_lines.append(norm)
            for raw in data.get("metro_lines", []) or []:
                if isinstance(raw, dict):
                    norm = _normalize_transit_line(raw)
                    self.metro_lines.append(norm)
            for raw in data.get("light_rail_lines", []) or []:
                if isinstance(raw, dict):
                    norm = _normalize_transit_line(raw)
                    self.light_rail_lines.append(norm)

            self.subway_lines = []
            for line in self.bus_lines:
                self.subway_lines.append(line)
                self.transit_modes.append("bus")
            for line in self.metro_lines:
                self.subway_lines.append(line)
                self.transit_modes.append("metro")
            for line in self.light_rail_lines:
                self.subway_lines.append(line)
                self.transit_modes.append("light_rail")

            if self.subway_lines:
                self.subway_path = list(self.subway_lines[0].get("path", []))
                st = self.subway_lines[0].get("station_indices", [])
                self.subway_stations = [self.subway_path[i] for i in st if 0 <= i < len(self.subway_path)]
            else:
                self.subway_path = []
                self.subway_stations = []

            self.single_cells = {tuple(pos) for pos in data.get("single_cells", [])}

            if data.get("start_pos"):
                self.start_pos = tuple(data["start_pos"])
            else:
                self.start_pos = None
            if data.get("target_pos"):
                self.target_pos = tuple(data["target_pos"])
            else:
                self.target_pos = None

            all_path_cells: List[Tuple[int, int]] = []
            for line in self.subway_lines:
                all_path_cells.extend(line.get("path", []))

            total_cells = max(1, len(self.single_cells) + len(set(all_path_cells)))
            start_grid = self.start_pos if self.start_pos else ((all_path_cells[0]) if all_path_cells else (0, 0))
            target_grid = self.target_pos if self.target_pos else start_grid

            if apply_target_entropy_only:
                protected_set = set(all_path_cells)
                for line in self.subway_lines:
                    for i in line.get("station_indices", []):
                        if 0 <= i < len(line.get("path", [])):
                            protected_set.add(line["path"][i])
                protected_set.update(self.single_cells)
                if self.start_pos:
                    protected_set.add(self.start_pos)
                if self.target_pos:
                    protected_set.add(self.target_pos)
                available_positions = []
                for gx, gy in set(all_path_cells) | self.single_cells:
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

            self.entropy_value = len(self.obstacle_map) / total_cells if total_cells > 0 else 0.0
            self._build_visibility_network()
            self.complexity_value = self._calculate_complexity()

            start_rid = 0
            print(f"成功加载自定义地图(Navigation6): {os.path.basename(filepath)}")
            return self.rooms, start_rid, self.entropy_value, self.complexity_value

        except Exception as e:
            print(f"加载地图文件失败: {e}")
            import traceback
            traceback.print_exc()
            return None
