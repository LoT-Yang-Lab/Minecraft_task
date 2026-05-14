"""
Navigation6 实验管理器（由 Navigation2 迁移而来）。
"""
import time
from typing import Dict, List, Set, Optional, Tuple


class Navigation2ExperimentManager:
    """城市交通导航实验管理器。"""

    PHASE_FREE_EXPLORATION = "free_exploration"
    PHASE_NAVIGATION_TEST = "navigation_test"
    PHASE_COMPLETE = "complete"

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.current_trial = 0
        self.current_phase = self.PHASE_FREE_EXPLORATION
        self.phase_start_time = time.time()
        self.trial_start_time = time.time()
        self.visited_rooms: Set[int] = set()
        self.total_rooms = 0
        self.coverage_threshold = self.config.get("coverage_threshold", 0.9)
        self.exploration_start_time = None
        self.exploration_end_time = None
        self.exploration_duration = 0.0
        self.test_start_position: Optional[Tuple[int, int]] = None
        self.test_target_position: Optional[Tuple[int, int]] = None
        self.test_start_time = None
        self.test_time_limit = None
        self.test_completed = False
        self.test_success = False
        self.test_path_length = 0
        self.test_optimal_path_length = 0
        self.trajectory_data: List[Dict] = []
        self.decision_points: List[Dict] = []
        self.last_decision_time = None
        self.last_position: Optional[Tuple[int, int]] = None
        self.phase_elapsed_time = 0.0
        self.used_subway_count = 0
        self.used_portal_count = 0
        self.first_subway_use_step: Optional[int] = None
        self.first_portal_use_step: Optional[int] = None

    def start_trial(self, total_rooms: int):
        self.current_trial += 1
        self.current_phase = self.PHASE_FREE_EXPLORATION
        self.trial_start_time = time.time()
        self.phase_start_time = time.time()
        self.visited_rooms.clear()
        self.total_rooms = total_rooms
        self.exploration_start_time = time.time()
        self.exploration_end_time = None
        self.exploration_duration = 0.0
        self.test_start_position = None
        self.test_target_position = None
        self.test_start_time = None
        self.test_time_limit = None
        self.test_completed = False
        self.test_success = False
        self.test_path_length = 0
        self.test_optimal_path_length = 0
        self.trajectory_data.clear()
        self.decision_points.clear()
        self.last_decision_time = None
        self.last_position = None
        self.phase_elapsed_time = 0.0
        self.used_subway_count = 0
        self.used_portal_count = 0
        self.first_subway_use_step = None
        self.first_portal_use_step = None

    def record_room_visit(self, room_id: int):
        self.visited_rooms.add(room_id)

    def get_coverage_rate(self) -> float:
        if self.total_rooms == 0:
            return 0.0
        return len(self.visited_rooms) / self.total_rooms

    def is_exploration_complete(self) -> bool:
        return self.get_coverage_rate() >= self.coverage_threshold

    def record_subway_use(self, step: Optional[int] = None):
        self.used_subway_count += 1
        if self.first_subway_use_step is None and step is not None:
            self.first_subway_use_step = step

    def record_portal_use(self, step: Optional[int] = None):
        self.used_portal_count += 1
        if self.first_portal_use_step is None and step is not None:
            self.first_portal_use_step = step

    def switch_to_navigation_test(
        self,
        start_pos: Tuple[int, int],
        target_pos: Tuple[int, int],
        optimal_path_length: int,
        map_diameter: int,
    ):
        if self.current_phase != self.PHASE_FREE_EXPLORATION:
            return
        self.exploration_end_time = time.time()
        self.exploration_duration = self.exploration_end_time - self.exploration_start_time
        self.phase_elapsed_time = self.exploration_duration
        self.current_phase = self.PHASE_NAVIGATION_TEST
        self.phase_start_time = time.time()
        self.test_start_position = start_pos
        self.test_target_position = target_pos
        self.test_start_time = time.time()
        self.test_optimal_path_length = optimal_path_length
        time_per_cell = self.config.get("time_per_cell", 2.0)
        self.test_time_limit = map_diameter * time_per_cell
        self.test_completed = False
        self.test_success = False
        self.test_path_length = 0

    def record_trajectory_point(self, x: int, y: int, velocity: float = 0.0, heading: Optional[str] = None):
        current_time = time.time()
        self.trajectory_data.append(
            {
                "trial": self.current_trial,
                "phase": self.current_phase,
                "timestamp": current_time - self.trial_start_time,
                "x": x,
                "y": y,
                "velocity": velocity,
                "heading": heading,
                "coverage_rate": self.get_coverage_rate() if self.current_phase == self.PHASE_FREE_EXPLORATION else None,
            }
        )
        if self.last_position != (x, y):
            if self.last_decision_time is not None:
                pause_duration = current_time - self.last_decision_time
                if pause_duration > 0.5:
                    self.decision_points.append(
                        {
                            "trial": self.current_trial,
                            "phase": self.current_phase,
                            "timestamp": self.last_decision_time - self.trial_start_time,
                            "position": self.last_position,
                            "pause_duration": pause_duration,
                            "next_position": (x, y),
                        }
                    )
            self.last_decision_time = current_time
            self.last_position = (x, y)

    def update_test_path_length(self, path_length: int):
        self.test_path_length = path_length

    def check_test_timeout(self) -> bool:
        if self.current_phase != self.PHASE_NAVIGATION_TEST:
            return False
        if self.test_start_time is None or self.test_time_limit is None:
            return False
        return (time.time() - self.test_start_time) >= self.test_time_limit

    def complete_test(self, success: bool, path_length: int):
        self.test_completed = True
        self.test_success = success
        self.test_path_length = path_length
        if success:
            self.current_phase = self.PHASE_COMPLETE

    def get_phase_elapsed_time(self) -> float:
        return time.time() - self.phase_start_time

    def get_trial_elapsed_time(self) -> float:
        return time.time() - self.trial_start_time

    def get_remaining_test_time(self) -> Optional[float]:
        if self.current_phase != self.PHASE_NAVIGATION_TEST or self.test_start_time is None or self.test_time_limit is None:
            return None
        return max(0.0, self.test_time_limit - (time.time() - self.test_start_time))

    def get_experiment_summary(self) -> Dict:
        summary = {
            "current_trial": self.current_trial,
            "current_phase": self.current_phase,
            "coverage_rate": self.get_coverage_rate(),
            "visited_rooms_count": len(self.visited_rooms),
            "total_rooms": self.total_rooms,
            "phase_elapsed_time": self.get_phase_elapsed_time(),
            "trial_elapsed_time": self.get_trial_elapsed_time(),
            "used_subway": self.used_subway_count,
            "used_portal": self.used_portal_count,
            "first_subway_use_step": self.first_subway_use_step,
            "first_portal_use_step": self.first_portal_use_step,
        }
        if self.exploration_duration > 0:
            summary["exploration_duration"] = self.exploration_duration
        if self.current_phase == self.PHASE_NAVIGATION_TEST or self.test_completed:
            summary["test_remaining_time"] = self.get_remaining_test_time()
            summary["test_path_length"] = self.test_path_length
            summary["test_optimal_path_length"] = self.test_optimal_path_length
            if self.test_optimal_path_length > 0:
                summary["test_path_ratio"] = self.test_path_length / self.test_optimal_path_length
            summary["test_success"] = self.test_success
            summary["test_completed"] = self.test_completed
        summary["trajectory_points_count"] = len(self.trajectory_data)
        summary["decision_points_count"] = len(self.decision_points)
        return summary
