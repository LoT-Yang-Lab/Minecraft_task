"""
Navigation6 游戏逻辑：仅公交 / 地铁 / 轻轨三类线路「站到站」移动；单格可行走；无步行方向与传送门。
"""
from collections import deque
from typing import Dict, Optional, Tuple, List, Any, Set, Union
import datetime
import random
import time

from shared.common.recorder import RLDataRecorder
from shared.common.room import Room
from shared.config import Navigation2Config
from experiments.navigation6.app.editor.map_generator_nav6 import Navigation6MapGenerator
from experiments.navigation6.app.editor.editor_data_nav6 import direction_from_room_centers, direction_from_points
from experiments.navigation6.app.common.transit_curve_geometry import ensure_transit_segment_metadata
from experiments.navigation6.app.experiment.experiment_manager import Navigation2ExperimentManager


# 八方向 (dx, dy) 用于步进邻域与路径
WALK_OFFSETS = [
    (0, -1), (0, 1), (1, 0), (-1, 0),
    (1, 1), (1, -1), (-1, 1), (-1, -1),
]


class GameNavigation6:
    """三类公共交通（公交蓝 / 地铁黄 / 轻轨绿）站到站即时移动；单格地图。"""

    def __init__(self, recorder: RLDataRecorder, map_type: str = "Barbell",
                 target_entropy: float = 0.5, enable_experiment: bool = True,
                 custom_map_file: Optional[str] = None,
                 apply_target_entropy_for_custom_map: bool = False):
        self.recorder = recorder
        self.map_type = map_type
        self.target_entropy = target_entropy
        self.enable_experiment = enable_experiment
        self.custom_map_file = custom_map_file
        self.apply_target_entropy_for_custom_map = apply_target_entropy_for_custom_map
        self.rooms: Dict[int, Room] = {}
        self.player_x = 0
        self.player_y = 0
        self.global_counter = 0
        self.game_over = False
        self.win_reason = ""
        self.logs = deque(maxlen=8)
        self.entropy_value = 0.0
        self.complexity_value = 0.0
        self.obstacle_map: Dict[Tuple[int, int], bool] = {}
        self.original_start_pos: Optional[Tuple[int, int]] = None
        self.original_target_pos: Optional[Tuple[int, int]] = None
        self.target_room_id: Optional[int] = None
        self.direction_map = {
            "north": "Up", "south": "Down", "west": "Left", "east": "Right",
            "northwest": "NW", "northeast": "NE", "southwest": "SW", "southeast": "SE",
        }
        self.player_direction = "south"

        self.subway_path: List[Tuple[int, int]] = []
        self.subway_station_indices: List[int] = []
        self.subway_lines: List[Dict[str, Any]] = []  # 多线路: [{"path": [...], "station_indices": [...]}, ...]
        self.subway_line_id: int = 0  # 当前乘坐的线路索引（on_subway 时有效）
        self.portal_pairs: List[Tuple[Tuple[int, int], Tuple[int, int]]] = []
        self.single_cells: Set[Tuple[int, int]] = set()
        self.single_cell_doors: Dict[Tuple[int, int], Dict[str, Union[int, Tuple[int, int], List[Union[int, Tuple[int, int]]]]]] = {}
        self.on_subway = False
        self.subway_path_index = 0
        self.train_states: List[List[Dict[str, Any]]] = []  # 每线路一列列车状态
        self.subway_train_id: int = -1
        self.transit_modes: List[str] = []

        # 双目标导航元数据（仅在正式实验双目标模式下由外层脚本设置；
        # 默认为 None/False，不影响练习阶段和其他调用者）
        self.dual_target_trial_id: Optional[int] = None
        self.dual_target_A: Optional[int] = None
        self.dual_target_B: Optional[int] = None
        self.dual_target_reached_A: bool = False
        self.dual_target_reached_B: bool = False

        if self.enable_experiment:
            self.experiment_manager = Navigation2ExperimentManager({
                'time_per_cell': 2.0, 'coverage_threshold': 0.9
            })
        else:
            self.experiment_manager = None

        self.map_generator = Navigation6MapGenerator(target_entropy)
        if custom_map_file and apply_target_entropy_for_custom_map:
            self.map_generator._apply_target_entropy_only_for_custom = True
        self.setup_level(map_type, custom_map_file)
        self.recorder.start_episode()
        map_display = custom_map_file if custom_map_file else map_type
        self.add_log(f"Map: {map_display} (Entropy: {self.entropy_value:.2f})")
        if self.enable_experiment and self.experiment_manager:
            self.experiment_manager.start_trial(max(1, len(self.rooms)))
            self.add_log("自由探索阶段 - 公交 / 地铁 / 轻轨到站移动")

    def add_log(self, text: str):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"[{timestamp}] {text}")

    def get_room_by_grid(self, gx: int, gy: int) -> Optional[Room]:
        lx, ly = gx // 3, gy // 3
        rid = ly * 100 + lx
        return self.rooms.get(rid)

    def _all_station_positions(self) -> Set[Tuple[int, int]]:
        s: Set[Tuple[int, int]] = set()
        for line in self.subway_lines:
            path = line.get("path", [])
            for i in line.get("station_indices", []):
                if 0 <= i < len(path):
                    s.add(path[i])
        return s

    def _first_station_cell(self) -> Optional[Tuple[int, int]]:
        for line in self.subway_lines:
            path = line.get("path", [])
            for i in line.get("station_indices", []):
                if 0 <= i < len(path):
                    return path[i]
        return None

    @staticmethod
    def _transit_line_is_station_loop(line: Dict[str, Any]) -> bool:
        """
        站点序列中第一站与最后一站为同一网格坐标时视为环线，允许末站再前进回到起点。
        非环线线路到达终点后不再提供「下一站」（与全局 SUBWAY_TRAIN_LOOP 无关）。
        """
        path = line.get("path", [])
        st = line.get("station_indices", [])
        if len(st) < 2:
            return False
        i0, i1 = st[0], st[-1]
        if not (0 <= i0 < len(path) and 0 <= i1 < len(path)):
            return False
        return path[i0] == path[i1]

    def _is_walkable(self, gx: int, gy: int) -> bool:
        if (gx, gy) in self.obstacle_map:
            return False
        if (gx, gy) in self.single_cells:
            return True
        if (gx, gy) in self._all_station_positions():
            return True
        return self.get_room_by_grid(gx, gy) is not None

    def _transit_log_action_type(self, line_index: int) -> str:
        if 0 <= line_index < len(self.transit_modes):
            m = self.transit_modes[line_index]
            if m == "bus":
                return "Bus"
            if m == "metro":
                return "Metro"
            if m == "light_rail":
                return "LightRail"
        return "Metro"

    def _transit_mode_for_line(self, line_index: int) -> str:
        if 0 <= line_index < len(self.transit_modes):
            return self.transit_modes[line_index]
        return "metro"

    @staticmethod
    def _is_bidirectional_mode(mode: str) -> bool:
        return mode in ("bus", "light_rail")

    @staticmethod
    def _grid_direction(from_pos: Tuple[int, int], to_pos: Tuple[int, int]) -> Optional[str]:
        """从 from 到 to 的网格方向：八方向。"""
        dx = to_pos[0] - from_pos[0]
        dy = to_pos[1] - from_pos[1]
        if (dx, dy) == (0, -1): return "north"
        if (dx, dy) == (0, 1): return "south"
        if (dx, dy) == (1, 0): return "east"
        if (dx, dy) == (-1, 0): return "west"
        if (dx, dy) == (-1, -1): return "northwest"
        if (dx, dy) == (1, -1): return "northeast"
        if (dx, dy) == (-1, 1): return "southwest"
        if (dx, dy) == (1, 1): return "southeast"
        return None

    def get_current_room_seq_id(self) -> int:
        r = self.get_room_by_grid(self.player_x, self.player_y)
        return r.seq_id if r else -1

    def _log_step(self, action_name: str, action_detail: str, reward: float, is_valid: bool):
        exp_data = {}
        if self.enable_experiment and self.experiment_manager:
            s = self.experiment_manager.get_experiment_summary()
            exp_data = {
                'Trial_ID': s.get('current_trial', 0), 'Phase': s.get('current_phase', ''),
                'Coverage_Rate': s.get('coverage_rate', 0.0),
                'Visited_Rooms_Count': s.get('visited_rooms_count', 0), 'Total_Rooms': s.get('total_rooms', 0),
                'Test_Remaining_Time': s.get('test_remaining_time'), 'Test_Path_Length': s.get('test_path_length', 0),
                'Test_Optimal_Path_Length': s.get('test_optimal_path_length', 0),
                'Test_Path_Ratio': s.get('test_path_ratio'), 'Test_Success': s.get('test_success'),
                'Used_Subway': s.get('used_subway', 0), 'Used_Portal': s.get('used_portal', 0),
            }
        # 双目标导航元数据（若已在正式实验脚本中设置，则一并写入日志）
        if getattr(self, "dual_target_trial_id", None) is not None:
            exp_data.update({
                "DualTrial_ID": self.dual_target_trial_id,
                "DualTarget_A": self.dual_target_A,
                "DualTarget_B": self.dual_target_B,
                "DualTarget_Reached_A": self.dual_target_reached_A,
                "DualTarget_Reached_B": self.dual_target_reached_B,
            })
        self.recorder.log_action(
            self.recorder.episode_count, self.global_counter, self.map_type,
            self.get_current_room_seq_id(), self.player_x, self.player_y, [],
            action_name, action_detail, reward, is_valid, self.game_over,
            Entropy=self.entropy_value, Complexity=self.complexity_value, **exp_data
        )

    def setup_level(self, map_type: str, custom_map_file: Optional[str] = None):
        self.map_type = map_type
        self.rooms, start_rid, self.entropy_value, self.complexity_value = \
            self.map_generator.generate_with_obstacles(map_type, self.target_entropy, custom_map_file=custom_map_file)
        self.obstacle_map = self.map_generator.obstacle_map
        self.portal_pairs = []
        self.single_cells = set(getattr(self.map_generator, 'single_cells', []))
        self.single_cell_doors = {}

        _gen_lines = getattr(self.map_generator, 'subway_lines', None)
        if _gen_lines and len(_gen_lines) > 0:
            self.subway_lines = []
            for line in _gen_lines:
                path = list(line.get("path", []))
                si = line.get("station_indices")
                if si is not None and len(si) > 0:
                    station_indices = sorted({int(i) for i in si if isinstance(i, int) and i >= 0})
                else:
                    stations = {tuple(p) for p in line.get("stations", [])}
                    station_indices = [i for i, pos in enumerate(path) if tuple(pos) in stations]
                    if path and 0 not in station_indices:
                        station_indices.insert(0, 0)
                    if path and len(path) > 1 and (len(path) - 1) not in station_indices:
                        station_indices.append(len(path) - 1)
                    station_indices.sort()
                row: Dict[str, Any] = {"path": path, "station_indices": station_indices}
                sc_raw = line.get("segment_curve")
                if isinstance(sc_raw, list):
                    row["segment_curve"] = [float(x) for x in sc_raw]
                ss_raw = line.get("segment_straight")
                if isinstance(ss_raw, list):
                    row["segment_straight"] = [bool(x) for x in ss_raw]
                ensure_transit_segment_metadata(row)
                self.subway_lines.append(row)
            self.subway_path = self.subway_lines[0]["path"] if self.subway_lines else []
            self.subway_station_indices = self.subway_lines[0]["station_indices"] if self.subway_lines else []
        else:
            self.subway_path = getattr(self.map_generator, 'subway_path', [])
            if custom_map_file and hasattr(self.map_generator, 'subway_stations') and self.map_generator.subway_stations:
                station_positions = set(self.map_generator.subway_stations)
                self.subway_station_indices = [i for i, pos in enumerate(self.subway_path) if pos in station_positions]
                if self.subway_station_indices and 0 not in self.subway_station_indices:
                    self.subway_station_indices.insert(0, 0)
                if self.subway_station_indices and len(self.subway_path) > 0:
                    if len(self.subway_path) - 1 not in self.subway_station_indices:
                        self.subway_station_indices.append(len(self.subway_path) - 1)
                self.subway_station_indices.sort()
            else:
                self._update_station_indices()
            self.subway_lines = [{"path": list(self.subway_path), "station_indices": list(self.subway_station_indices)}]

        tm = getattr(self.map_generator, "transit_modes", None) or []
        if len(tm) == len(self.subway_lines):
            self.transit_modes = list(tm)
        else:
            self.transit_modes = ["metro"] * len(self.subway_lines)

        target_room = None
        for rid, room in self.rooms.items():
            if getattr(room, 'is_target', False):
                target_room = room
                self.target_room_id = rid
                break
        if custom_map_file and hasattr(self.map_generator, 'start_pos') and self.map_generator.start_pos:
            self.player_x, self.player_y = self.map_generator.start_pos
            if not self._is_walkable(self.player_x, self.player_y):
                if self.rooms:
                    r = self.rooms[sorted(self.rooms.keys())[0]]
                    self.player_x, self.player_y = r.logical_pos[0] * 3 + 1, r.logical_pos[1] * 3 + 1
                elif self.single_cells:
                    first_cell = min(self.single_cells, key=lambda c: (c[0], c[1]))
                    self.player_x, self.player_y = first_cell[0], first_cell[1]
                else:
                    st = self._first_station_cell()
                    if st:
                        self.player_x, self.player_y = st
            self.original_start_pos = (self.player_x, self.player_y)
            start_room = self.get_room_by_grid(self.player_x, self.player_y)
            if start_room:
                start_room.visited = True
        elif start_rid in self.rooms:
            r = self.rooms[start_rid]
            self.player_x = r.logical_pos[0] * 3 + 1
            self.player_y = r.logical_pos[1] * 3 + 1
            r.visited = True
            self.original_start_pos = (self.player_x, self.player_y)
        elif self.rooms:
            r = self.rooms[sorted(self.rooms.keys())[0]]
            self.player_x = r.logical_pos[0] * 3 + 1
            self.player_y = r.logical_pos[1] * 3 + 1
            r.visited = True
            self.original_start_pos = (self.player_x, self.player_y)
        else:
            if self.single_cells:
                first_cell = min(self.single_cells, key=lambda c: (c[0], c[1]))
                self.player_x, self.player_y = first_cell[0], first_cell[1]
            else:
                st = self._first_station_cell()
                self.player_x, self.player_y = st if st else (0, 0)
            self.original_start_pos = (self.player_x, self.player_y)
        if custom_map_file and hasattr(self.map_generator, 'target_pos') and self.map_generator.target_pos:
            self.original_target_pos = self.map_generator.target_pos
        elif target_room:
            self.original_target_pos = (
                target_room.logical_pos[0] * 3 + 1,
                target_room.logical_pos[1] * 3 + 1
            )
        self.on_subway = False
        self.subway_path_index = 0
        self.subway_line_id = 0
        self.subway_train_id = -1
        if not self.subway_lines:
            self._update_station_indices()
        self._ensure_target_not_on_station()
        self._init_trains()

    def _update_station_indices(self):
        path = self.subway_path
        self.subway_station_indices = []
        L = len(path)
        if L == 0:
            return
        if L == 1:
            self.subway_station_indices = [0]
            return
        room_to_indices = {}
        for idx in range(L):
            room_id = self._get_room_for_path_index(idx)
            if room_id is not None:
                if room_id not in room_to_indices:
                    room_to_indices[room_id] = []
                room_to_indices[room_id].append(idx)
        used_rooms = set()
        start_room_id = self._get_room_for_path_index(0)
        end_room_id = self._get_room_for_path_index(L - 1)
        self.subway_station_indices = [0]
        if start_room_id is not None:
            used_rooms.add(start_room_id)
        if L > 1:
            if end_room_id != start_room_id:
                self.subway_station_indices.append(L - 1)
                if end_room_id is not None:
                    used_rooms.add(end_room_id)
            else:
                self.subway_station_indices.append(L - 1)
        unique_rooms = [rid for rid in room_to_indices.keys() if rid not in used_rooms]
        for room_id in unique_rooms:
            if len(self.subway_station_indices) >= 4:
                break
            idx = room_to_indices[room_id][0]
            if idx not in self.subway_station_indices:
                self.subway_station_indices.append(idx)
                used_rooms.add(room_id)
        if len(self.subway_station_indices) < 4:
            for idx in range(1, L - 1):
                if len(self.subway_station_indices) >= 4:
                    break
                if idx not in self.subway_station_indices:
                    room_id = self._get_room_for_path_index(idx)
                    if room_id is not None and room_id not in used_rooms:
                        self.subway_station_indices.append(idx)
                        used_rooms.add(room_id)
        if len(self.subway_station_indices) < 4:
            for idx in range(1, L - 1):
                if len(self.subway_station_indices) >= 4:
                    break
                if idx not in self.subway_station_indices:
                    self.subway_station_indices.append(idx)
        self.subway_station_indices.sort()

    def _get_room_for_path_index(self, idx: int) -> Optional[int]:
        if idx < 0 or idx >= len(self.subway_path):
            return None
        gx, gy = self.subway_path[idx]
        lx, ly = gx // 3, gy // 3
        return ly * 100 + lx

    def _init_trains(self):
        T = getattr(Navigation2Config, 'SUBWAY_TRAIN_PERIOD', 4)
        S = getattr(Navigation2Config, 'SUBWAY_STOP_DURATION', 2)
        self.train_states = []
        for line in self.subway_lines:
            path = line.get("path", [])
            L = len(path)
            stations = [i for i in line.get("station_indices", []) if 0 <= i < L]
            line_trains = []
            if L == 0:
                self.train_states.append(line_trains)
                continue
            if not stations:
                stations = [0] if L else []
            idx0 = stations[0]
            line_trains.append({"path_index": idx0, "state": "stopped", "countdown": S})
            if L >= 2:
                idx1 = next((i for i in stations if i != idx0), None)
                if idx1 is None:
                    idx1 = min(1, L - 1) if min(1, L - 1) != idx0 else L - 1
                line_trains.append({"path_index": idx1, "state": "moving", "countdown": 1})
            self.train_states.append(line_trains)

    def _tick_trains(self):
        T = getattr(Navigation2Config, 'SUBWAY_TRAIN_PERIOD', 4)
        S = getattr(Navigation2Config, 'SUBWAY_STOP_DURATION', 2)
        for line_idx, line in enumerate(self.subway_lines):
            path = line.get("path", [])
            L = len(path)
            if L == 0:
                continue
            line_loop = self._transit_line_is_station_loop(line)
            stations = set(line.get("station_indices", []))
            trains = self.train_states[line_idx] if line_idx < len(self.train_states) else []
            for t in trains:
                t["countdown"] -= 1
                if t["countdown"] > 0:
                    continue
                if t["state"] == "stopped":
                    t["state"] = "moving"
                    t["countdown"] = T
                else:
                    next_idx = t["path_index"] + 1
                    if next_idx >= L:
                        if line_loop:
                            next_idx = 0
                        else:
                            next_idx = L - 1
                            t["state"] = "stopped" if next_idx in stations else "moving"
                            t["countdown"] = S if next_idx in stations else T
                            t["path_index"] = next_idx
                            continue
                    t["path_index"] = next_idx
                    idx = t["path_index"]
                    if idx in stations:
                        t["state"] = "stopped"
                        t["countdown"] = S
                    else:
                        t["state"] = "moving"
                        t["countdown"] = T

    def get_train_can_board_at(self, gx: int, gy: int) -> bool:
        pos = (gx, gy)
        for line_idx, line in enumerate(self.subway_lines):
            path = line.get("path", [])
            stations = set(line.get("station_indices", []))
            trains = self.train_states[line_idx] if line_idx < len(self.train_states) else []
            for t in trains:
                idx = t["path_index"]
                if idx not in stations or idx >= len(path):
                    continue
                if path[idx] == pos and t["state"] == "stopped":
                    return True
        return False

    def get_subway_station_positions(self) -> List[Tuple[int, int]]:
        positions = []
        for line in self.subway_lines:
            path = line.get("path", [])
            for i in line.get("station_indices", []):
                if 0 <= i < len(path):
                    positions.append(path[i])
        return positions

    def get_instant_subway_next_stations(self, px: int, py: int) -> List[Tuple[int, Tuple[int, int]]]:
        """站在站点时，各线路「下一站」的 (line_idx, (gx, gy)) 列表。仅当站点序列为环线（首末站同格）时末站可回到第一站。"""
        out: List[Tuple[int, Tuple[int, int]]] = []
        for line_idx, line in enumerate(self.subway_lines):
            path = line.get("path", [])
            st_indices = line.get("station_indices", [])
            if not path or not st_indices:
                continue
            line_loop = self._transit_line_is_station_loop(line)
            j = None
            for idx, si in enumerate(st_indices):
                if 0 <= si < len(path) and path[si] == (px, py):
                    j = idx
                    break
            if j is None:
                continue
            next_j = j + 1
            if next_j >= len(st_indices):
                if not line_loop:
                    continue
                next_j = 0
            next_si = st_indices[next_j]
            if 0 <= next_si < len(path):
                out.append((line_idx, path[next_si]))
        return out

    def get_instant_subway_prev_stations(self, px: int, py: int) -> List[Tuple[int, Tuple[int, int]]]:
        """
        站在站点时，各线路「上一站」的 (line_idx, (gx, gy)) 列表。
        仅公交/轻轨支持反向；地铁保持单向。
        """
        out: List[Tuple[int, Tuple[int, int]]] = []
        for line_idx, line in enumerate(self.subway_lines):
            mode = self._transit_mode_for_line(line_idx)
            if not self._is_bidirectional_mode(mode):
                continue
            path = line.get("path", [])
            st_indices = line.get("station_indices", [])
            if not path or not st_indices:
                continue
            line_loop = self._transit_line_is_station_loop(line)
            j = None
            for idx, si in enumerate(st_indices):
                if 0 <= si < len(path) and path[si] == (px, py):
                    j = idx
                    break
            if j is None:
                continue
            prev_j = j - 1
            if prev_j < 0:
                if not line_loop:
                    continue
                prev_j = len(st_indices) - 1
            prev_si = st_indices[prev_j]
            if 0 <= prev_si < len(path):
                out.append((line_idx, path[prev_si]))
        return out

    def instant_subway_to_next_station(self, line_index: int) -> bool:
        """站在该线路站点时，立刻移动到该线路下一站。返回是否成功。"""
        if self.game_over:
            return False
        self._check_test_timeout_and_phase()
        if self.game_over:
            return False
        px, py = self.player_x, self.player_y
        next_stations = self.get_instant_subway_next_stations(px, py)
        target_pos = None
        for lidx, pos in next_stations:
            if lidx == line_index:
                target_pos = pos
                break
        if target_pos is None:
            return False
        self.global_counter += 1
        self._tick_trains()
        self.player_x, self.player_y = target_pos[0], target_pos[1]
        if self.enable_experiment and self.experiment_manager:
            self.experiment_manager.record_subway_use(self.global_counter)
        new_room = self.get_room_by_grid(self.player_x, self.player_y)
        if new_room:
            new_room.visited = True
            if (self.enable_experiment and self.experiment_manager
                    and self.experiment_manager.current_phase == Navigation2ExperimentManager.PHASE_FREE_EXPLORATION):
                self.experiment_manager.record_room_visit(new_room.seq_id)
                if self.experiment_manager.is_exploration_complete():
                    self._switch_to_navigation_test()
        if self.original_target_pos and (self.player_x, self.player_y) == self.original_target_pos:
            self._on_reach_target()
        self._log_step(self._transit_log_action_type(line_index), "Instant", Navigation2Config.REWARD_STEP, True)
        return True

    def instant_subway_to_prev_station(self, line_index: int) -> bool:
        """站在该线路站点时，立刻移动到该线路上一站（仅公交/轻轨有效）。"""
        if self.game_over:
            return False
        self._check_test_timeout_and_phase()
        if self.game_over:
            return False
        mode = self._transit_mode_for_line(line_index)
        if not self._is_bidirectional_mode(mode):
            return False
        px, py = self.player_x, self.player_y
        prev_stations = self.get_instant_subway_prev_stations(px, py)
        target_pos = None
        for lidx, pos in prev_stations:
            if lidx == line_index:
                target_pos = pos
                break
        if target_pos is None:
            return False
        self.global_counter += 1
        self._tick_trains()
        self.player_x, self.player_y = target_pos[0], target_pos[1]
        if self.enable_experiment and self.experiment_manager:
            self.experiment_manager.record_subway_use(self.global_counter)
        new_room = self.get_room_by_grid(self.player_x, self.player_y)
        if new_room:
            new_room.visited = True
            if (
                self.enable_experiment
                and self.experiment_manager
                and self.experiment_manager.current_phase == Navigation2ExperimentManager.PHASE_FREE_EXPLORATION
            ):
                self.experiment_manager.record_room_visit(new_room.seq_id)
                if self.experiment_manager.is_exploration_complete():
                    self._switch_to_navigation_test()
        if self.original_target_pos and (self.player_x, self.player_y) == self.original_target_pos:
            self._on_reach_target()
        self._log_step(self._transit_log_action_type(line_index), "InstantPrev", Navigation2Config.REWARD_STEP, True)
        return True

    def is_player_at_subway_station(self) -> bool:
        if self.on_subway:
            return False
        return (self.player_x, self.player_y) in self.get_subway_station_positions()

    def get_subway_arrival_steps_at(self, gx: int, gy: int) -> Optional[int]:
        if (gx, gy) not in set(self.get_subway_station_positions()):
            return None
        if self.get_train_can_board_at(gx, gy):
            return 0
        T = getattr(Navigation2Config, "SUBWAY_TRAIN_PERIOD", 1)
        S = getattr(Navigation2Config, "SUBWAY_STOP_DURATION", 1)
        min_steps = None
        for line_idx, line in enumerate(self.subway_lines):
            path = line.get("path", [])
            L = len(path)
            if L == 0:
                continue
            line_loop = self._transit_line_is_station_loop(line)
            stations = set(line.get("station_indices", []))
            target_station_idx = None
            for i in line.get("station_indices", []):
                if 0 <= i < L and path[i] == (gx, gy):
                    target_station_idx = i
                    break
            if target_station_idx is None:
                continue
            max_steps = L * (T + S + 2) * 2
            trains = self.train_states[line_idx] if line_idx < len(self.train_states) else []
            for train_state in trains:
                t = {"path_index": train_state["path_index"], "state": train_state["state"], "countdown": train_state["countdown"]}
                for step in range(max_steps):
                    if t["path_index"] == target_station_idx and t["state"] == "stopped":
                        if min_steps is None or step < min_steps:
                            min_steps = step
                        break
                    t["countdown"] -= 1
                    if t["countdown"] > 0:
                        continue
                    if t["state"] == "stopped":
                        t["state"] = "moving"
                        t["countdown"] = T
                    else:
                        next_idx = t["path_index"] + 1
                        if next_idx >= L:
                            next_idx = 0 if line_loop else L - 1
                        t["path_index"] = next_idx
                        t["state"] = "stopped" if next_idx in stations else "moving"
                        t["countdown"] = S if next_idx in stations else T
        return min_steps

    def _ensure_target_not_on_station(self):
        if not self.rooms:
            return
        if not self.original_target_pos:
            return
        station_positions = set(self.get_subway_station_positions())
        if self.original_target_pos in station_positions:
            target_room = self.get_room_by_grid(self.original_target_pos[0], self.original_target_pos[1])
            if target_room:
                target_room.is_target = False
            available_rooms = [
                r for r in self.rooms.values()
                if not getattr(r, 'is_target', False) and
                (r.logical_pos[0] * 3 + 1, r.logical_pos[1] * 3 + 1) not in station_positions
            ]
            if available_rooms:
                new_target_room = random.choice(available_rooms)
                new_target_room.is_target = True
                self.target_room_id = new_target_room.id
                self.original_target_pos = (
                    new_target_room.logical_pos[0] * 3 + 1,
                    new_target_room.logical_pos[1] * 3 + 1
                )

    def get_train_positions_for_draw(self) -> List[Tuple[Tuple[int, int], bool]]:
        out = []
        station_positions = set(self.get_subway_station_positions())
        for line_idx, line in enumerate(self.subway_lines):
            path = line.get("path", [])
            stations = set(line.get("station_indices", []))
            trains = self.train_states[line_idx] if line_idx < len(self.train_states) else []
            for t in trains:
                idx = t["path_index"]
                if idx < len(path):
                    pos = path[idx]
                    can_board = (
                        pos in station_positions
                        and idx in stations
                        and t["state"] == "stopped"
                    )
                    out.append((pos, can_board))
        return out

    def get_visible_cells(self) -> Set[Tuple[int, int]]:
        visible = set()
        px, py = self.player_x, self.player_y
        visible.add((px, py))
        if self.on_subway:
            line_idx = self.subway_line_id
            if line_idx < len(self.subway_lines):
                path = self.subway_lines[line_idx]["path"]
                station_set = set(self.subway_lines[line_idx].get("station_indices", []))
                idx = self.subway_path_index
                if 0 <= idx < len(path):
                    for i in range(idx + 1, len(path)):
                        if i in station_set:
                            visible.add(path[i])
                            break
        else:
            station_positions = set(self.get_subway_station_positions())
            if (px, py) in station_positions:
                for line in self.subway_lines:
                    path = line.get("path", [])
                    stations = line.get("station_indices", [])
                    line_loop = self._transit_line_is_station_loop(line)
                    for j, path_idx in enumerate(stations):
                        if 0 <= path_idx < len(path) and path[path_idx] == (px, py):
                            if j + 1 < len(stations):
                                next_idx = stations[j + 1]
                                if 0 <= next_idx < len(path):
                                    visible.add(path[next_idx])
                            elif line_loop and len(stations) > 1:
                                next_idx = stations[0]
                                if 0 <= next_idx < len(path):
                                    visible.add(path[next_idx])
                            break
        if self.original_target_pos:
            visible.add(self.original_target_pos)
        return visible

    def check_move_validity(self, cur_x: int, cur_y: int, next_x: int, next_y: int) -> Tuple[bool, str]:
        """Navigation6 无步行；仅保留接口兼容，恒为不可步行（除原地）。"""
        if (cur_x, cur_y) == (next_x, next_y):
            return True, "Walk"
        return False, "NoWalk"

    def get_move_target(self, px: int, py: int, direction: str) -> Optional[Tuple[int, int]]:
        return None

    def _transit_adjacency(self) -> Dict[Tuple[int, int], Set[Tuple[int, int]]]:
        from collections import defaultdict
        adj: Dict[Tuple[int, int], Set[Tuple[int, int]]] = defaultdict(set)
        for line in self.subway_lines:
            path = line.get("path", [])
            st_idx = line.get("station_indices", [])
            if not st_idx:
                continue
            line_loop = self._transit_line_is_station_loop(line)
            for j, si in enumerate(st_idx):
                if not (0 <= si < len(path)):
                    continue
                u = path[si]
                if j + 1 < len(st_idx):
                    ti = st_idx[j + 1]
                    if 0 <= ti < len(path):
                        v = path[ti]
                        if u != v:
                            adj[u].add(v)
                            adj[v].add(u)
                elif line_loop and len(st_idx) > 1:
                    ti = st_idx[0]
                    if 0 <= ti < len(path):
                        v = path[ti]
                        if u != v:
                            adj[u].add(v)
                            adj[v].add(u)
                if j > 0:
                    ti = st_idx[j - 1]
                    if 0 <= ti < len(path):
                        v = path[ti]
                        if u != v:
                            adj[u].add(v)
                            adj[v].add(u)
        return adj

    def find_shortest_path(self, start: Tuple[int, int], target: Tuple[int, int]) -> Optional[List[Tuple[int, int]]]:
        if start == target:
            return [start]
        adj = self._transit_adjacency()
        queue = deque([(start, [start])])
        visited = {start}
        while queue:
            current, path = queue.popleft()
            for nb in adj.get(current, ()):
                if nb in visited:
                    continue
                visited.add(nb)
                npath = path + [nb]
                if nb == target:
                    return npath
                queue.append((nb, npath))
        return None

    def get_map_diameter(self) -> int:
        if not self.rooms:
            cells = set(self.single_cells) | self._all_station_positions()
            if not cells:
                return 10
            xs = [c[0] for c in cells]
            ys = [c[1] for c in cells]
            return max(max(xs) - min(xs), max(ys) - min(ys), 1) + 1
        room_positions = [room.logical_pos for room in self.rooms.values()]
        max_dist = 0
        for i, pos1 in enumerate(room_positions):
            for pos2 in room_positions[i + 1:]:
                max_dist = max(max_dist, abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1]))
        return max_dist * 3

    def _check_test_timeout_and_phase(self):
        if not self.enable_experiment or not self.experiment_manager:
            return
        if self.experiment_manager.current_phase != Navigation2ExperimentManager.PHASE_NAVIGATION_TEST:
            return
        if self.experiment_manager.check_test_timeout():
            self.game_over = True
            self.win_reason = "测试超时"
            self.experiment_manager.complete_test(False, self.global_counter)
            self.add_log("!!! 测试超时 !!!")

    def wait_one_step(self) -> bool:
        if self.game_over:
            return False
        self._check_test_timeout_and_phase()
        if self.game_over:
            return False
        self.global_counter += 1
        self._tick_trains()
        self.add_log("等待（步数+1）")
        return True

    def move(self, direction: str):
        if self.game_over:
            return
        self._check_test_timeout_and_phase()
        if self.game_over:
            return
        self.global_counter += 1
        self._tick_trains()
        log_dir = self.direction_map.get(direction, direction)
        if self.on_subway:
            line_idx = self.subway_line_id
            path = self.subway_lines[line_idx]["path"] if line_idx < len(self.subway_lines) else []
            trains = self.train_states[line_idx] if line_idx < len(self.train_states) else []
            tid = self.subway_train_id
            if path and 0 <= tid < len(trains):
                train = trains[tid]
                self.subway_path_index = train["path_index"]
                if self.subway_path_index < len(path):
                    self.player_x, self.player_y = path[self.subway_path_index]
            elif path and 0 <= self.subway_path_index < len(path):
                self.player_x, self.player_y = path[self.subway_path_index]
            new_room = self.get_room_by_grid(self.player_x, self.player_y)
            if new_room:
                new_room.visited = True
                if self.enable_experiment and self.experiment_manager:
                    self.experiment_manager.record_trajectory_point(
                        self.player_x, self.player_y, 1.0, log_dir
                    )
                    self.experiment_manager.record_subway_use(self.global_counter)
                if getattr(new_room, 'is_target', False):
                    self._on_reach_target()
            self._log_step(log_dir, "Subway", Navigation2Config.REWARD_STEP, True)
            return
        cur_room = self.get_room_by_grid(self.player_x, self.player_y)
        target_rid = cur_room.get_neighbor_id(direction) if cur_room else None
        if cur_room and target_rid is not None:
            target_room = self.rooms.get(target_rid)
            if target_room:
                target_x = target_room.logical_pos[0] * 3 + 1
                target_y = target_room.logical_pos[1] * 3 + 1
                self.player_x, self.player_y = target_x, target_y
                self.player_direction = direction
                target_room.visited = True
                if self.enable_experiment and self.experiment_manager:
                    self.experiment_manager.record_trajectory_point(target_x, target_y, 1.0, direction)
                    if self.experiment_manager.current_phase == Navigation2ExperimentManager.PHASE_FREE_EXPLORATION:
                        self.experiment_manager.record_room_visit(target_room.seq_id)
                        if self.experiment_manager.is_exploration_complete():
                            self._switch_to_navigation_test()
                if getattr(target_room, 'is_target', False):
                    self._on_reach_target()
                self._log_step(log_dir, "Door", Navigation2Config.REWARD_STEP, True)
                return
        cell_pos = (self.player_x, self.player_y)
        if cell_pos in self.single_cells:
            cell_doors = self.single_cell_doors.get(cell_pos, {})
            if isinstance(cell_doors, dict) and direction in cell_doors:
                raw = cell_doors[direction]
                target = (raw[0] if isinstance(raw, list) else raw)
                if isinstance(target, int):
                    target_room = self.rooms.get(target)
                    if target_room:
                        target_x = target_room.logical_pos[0] * 3 + 1
                        target_y = target_room.logical_pos[1] * 3 + 1
                        self.player_x, self.player_y = target_x, target_y
                        self.player_direction = direction
                        target_room.visited = True
                        if self.enable_experiment and self.experiment_manager:
                            self.experiment_manager.record_trajectory_point(target_x, target_y, 1.0, direction)
                            if self.experiment_manager.current_phase == Navigation2ExperimentManager.PHASE_FREE_EXPLORATION:
                                self.experiment_manager.record_room_visit(target_room.seq_id)
                                if self.experiment_manager.is_exploration_complete():
                                    self._switch_to_navigation_test()
                        if getattr(target_room, 'is_target', False):
                            self._on_reach_target()
                        self._log_step(log_dir, "Door", Navigation2Config.REWARD_STEP, True)
                        return
                elif isinstance(target, tuple) and len(target) == 2:
                    self.player_x, self.player_y = target[0], target[1]
                    self.player_direction = direction
                    self._log_step(log_dir, "Door", Navigation2Config.REWARD_STEP, True)
                    return
        dx, dy = 0, 0
        if direction == "north":
            dy = -1
        elif direction == "south":
            dy = 1
        elif direction == "west":
            dx = -1
        elif direction == "east":
            dx = 1
        elif direction == "northwest":
            dx, dy = -1, -1
        elif direction == "northeast":
            dx, dy = 1, -1
        elif direction == "southwest":
            dx, dy = -1, 1
        elif direction == "southeast":
            dx, dy = 1, 1
        target_x = self.player_x + dx
        target_y = self.player_y + dy
        valid, reason = self.check_move_validity(self.player_x, self.player_y, target_x, target_y)
        if valid:
            self.player_x, self.player_y = target_x, target_y
            self.player_direction = direction
            new_room = self.get_room_by_grid(target_x, target_y)
            if new_room:
                new_room.visited = True
                if self.enable_experiment and self.experiment_manager:
                    self.experiment_manager.record_trajectory_point(target_x, target_y, 1.0, direction)
                    if self.experiment_manager.current_phase == Navigation2ExperimentManager.PHASE_FREE_EXPLORATION:
                        self.experiment_manager.record_room_visit(new_room.seq_id)
                        if self.experiment_manager.is_exploration_complete():
                            self._switch_to_navigation_test()
                if getattr(new_room, 'is_target', False):
                    self._on_reach_target()
            elif (target_x, target_y) == self.original_target_pos:
                self._on_reach_target()
            self._log_step(log_dir, reason, Navigation2Config.REWARD_STEP, True)
        else:
            self.add_log(f"移动失败 ({reason})")
            self._log_step(log_dir, reason, Navigation2Config.REWARD_INVALID_MOVE, False)

    def _find_next_station_forward(self, start_idx: int, max_idx: int) -> Optional[int]:
        stations = set(self.subway_station_indices)
        for idx in range(start_idx, max_idx + 1):
            if idx in stations:
                return idx
        return None

    def _get_stopped_train_at_station(self, gx: int, gy: int) -> Optional[Tuple[int, int]]:
        """返回 (line_idx, path_index) 或 None。"""
        for line_idx, line in enumerate(self.subway_lines):
            path = line.get("path", [])
            stations = set(line.get("station_indices", []))
            trains = self.train_states[line_idx] if line_idx < len(self.train_states) else []
            for t in trains:
                if t["state"] != "stopped":
                    continue
                idx = t["path_index"]
                if idx not in stations or idx >= len(path):
                    continue
                if path[idx] == (gx, gy):
                    return (line_idx, idx)
        return None

    def board_subway(self) -> bool:
        if self.on_subway:
            return False
        result = self._get_stopped_train_at_station(self.player_x, self.player_y)
        if result is None:
            self.add_log("此处无停靠列车，无法上车")
            return False
        line_idx, path_idx = result
        self.on_subway = True
        self.subway_line_id = line_idx
        self.subway_path_index = path_idx
        path = self.subway_lines[line_idx]["path"]
        self.player_x, self.player_y = path[path_idx]
        self.subway_train_id = -1
        trains = self.train_states[line_idx] if line_idx < len(self.train_states) else []
        for i, t in enumerate(trains):
            if t["path_index"] == path_idx:
                self.subway_train_id = i
                break
        self.add_log("已上地铁")
        return True

    def _find_alight_position(self, station_idx: int, path: Optional[List[Tuple[int, int]]] = None) -> Optional[Tuple[int, int]]:
        if path is None:
            path = self.subway_path
        if station_idx >= len(path):
            return None
        sx, sy = path[station_idx]
        lx, ly = sx // 3, sy // 3
        if self._is_walkable(sx, sy):
            return (sx, sy)
        center_gx, center_gy = lx * 3 + 1, ly * 3 + 1
        if self._is_walkable(center_gx, center_gy):
            return (center_gx, center_gy)
        room_cells = []
        for dx in range(3):
            for dy in range(3):
                gx, gy = lx * 3 + dx, ly * 3 + dy
                if not self._is_walkable(gx, gy):
                    continue
                dist = abs(gx - sx) + abs(gy - sy)
                room_cells.append((dist, gx, gy))
        if room_cells:
            room_cells.sort()
            return (room_cells[0][1], room_cells[0][2])
        for rid, room in self.rooms.items():
            rx, ry = room.logical_pos
            dx, dy = abs(rx - lx), abs(ry - ly)
            if dx > 1 or dy > 1 or (dx == 0 and dy == 0):
                continue
            cx, cy = rx * 3 + 1, ry * 3 + 1
            if self._is_walkable(cx, cy):
                return (cx, cy)
        return None

    def alight_subway(self) -> bool:
        if not self.on_subway:
            return False
        line_idx = self.subway_line_id
        path = self.subway_lines[line_idx]["path"] if line_idx < len(self.subway_lines) else []
        stations = set(self.subway_lines[line_idx].get("station_indices", [])) if line_idx < len(self.subway_lines) else set()
        idx = self.subway_path_index
        if idx >= len(path):
            return False
        if idx not in stations:
            self.add_log("仅可在站点（方形标记）下车")
            return False
        pos = self._find_alight_position(idx, path=path)
        if pos is None:
            self.add_log("该站台附近无可下车区域")
            return False
        self.on_subway = False
        self.subway_train_id = -1
        self.player_x, self.player_y = pos
        self.add_log("已下地铁" if pos == path[idx] else f"已下地铁（位置：({pos[0]}, {pos[1]})）")
        return True

    def use_portal(self) -> bool:
        return False

    def _on_reach_target(self):
        if self.enable_experiment and self.experiment_manager and \
           self.experiment_manager.current_phase == Navigation2ExperimentManager.PHASE_NAVIGATION_TEST:
            self.experiment_manager.update_test_path_length(self.global_counter)
            self.experiment_manager.complete_test(True, self.global_counter)
            self.game_over = True
            self.win_reason = "成功到达目标！"
            self.add_log("!!! 测试成功 !!!")
        else:
            self.check_win()

    def check_win(self):
        room = self.get_room_by_grid(self.player_x, self.player_y)
        at_target_pos = self.original_target_pos and (self.player_x, self.player_y) == self.original_target_pos
        if (room and getattr(room, 'is_target', False) or at_target_pos) and not self.game_over:
            self.game_over = True
            self.win_reason = "到达目标！"
            if len(self.recorder.memory_buffer) > 0:
                self.recorder.memory_buffer[-1]["Reward"] = Navigation2Config.REWARD_REACH_TARGET
                self.recorder.memory_buffer[-1]["Game_Over"] = True
            self.add_log("!!! 胜利 !!!")

    def _switch_to_navigation_test(self):
        if not self.enable_experiment or not self.experiment_manager:
            return
        if self.experiment_manager.current_phase != Navigation2ExperimentManager.PHASE_FREE_EXPLORATION:
            return
        available_rooms = [r for r in self.rooms.values() if not getattr(r, 'is_target', False)]
        if not available_rooms or not self.original_target_pos:
            return
        start_room = random.choice(available_rooms)
        random_start_pos = (
            start_room.logical_pos[0] * 3 + 1,
            start_room.logical_pos[1] * 3 + 1
        )
        optimal_path = self.find_shortest_path(random_start_pos, self.original_target_pos)
        optimal_length = len(optimal_path) - 1 if optimal_path else 100
        self.experiment_manager.switch_to_navigation_test(
            random_start_pos, self.original_target_pos, optimal_length, self.get_map_diameter()
        )
        self.player_x, self.player_y = random_start_pos
        self.global_counter = 0
        self.on_subway = False
        self.subway_train_id = -1
        for room in self.rooms.values():
            if not getattr(room, 'is_target', False):
                room.visited = False
        current_room = self.get_room_by_grid(self.player_x, self.player_y)
        if current_room:
            current_room.visited = True
        self.add_log("进入定位导航测试阶段")

    def reset(self, new_map_type: str = None, new_entropy: float = None, new_custom_map_file: Optional[str] = None):
        m_type = new_map_type if new_map_type else self.map_type
        entropy = new_entropy if new_entropy is not None else self.target_entropy
        custom_file = new_custom_map_file if new_custom_map_file is not None else self.custom_map_file
        self.recorder.save_to_file()
        self.__init__(self.recorder, m_type, entropy, self.enable_experiment, custom_file, self.apply_target_entropy_for_custom_map)
