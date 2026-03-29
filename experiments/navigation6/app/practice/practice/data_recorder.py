"""
练习数据记录：保存每条作答记录并导出 JSON / CSV，含元数据（participant_id、random_seed、map_id 等）。
"""
import json
import csv
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from .practice_manager import AnswerRecord


class PracticeDataRecorder:
    """Navigation6 练习数据记录器。支持元数据导出与 participant_id 文件名。"""

    def __init__(self, output_dir: str = "practice_data", participant_id: Optional[str] = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.records: List[Dict[str, Any]] = []
        self.participant_id = participant_id or ""
        self._metadata: Dict[str, Any] = {}

    def set_metadata(
        self,
        random_seed: Optional[int] = None,
        map_id: Optional[str] = None,
        session_start_iso: Optional[str] = None,
        learning_pool_size: Optional[int] = None,
        test_pool_size: Optional[int] = None,
        phase_transition_criterion: Optional[str] = None,
    ) -> None:
        if random_seed is not None:
            self._metadata["random_seed"] = random_seed
        if map_id is not None:
            self._metadata["map_id"] = map_id
        if session_start_iso is not None:
            self._metadata["session_start_iso"] = session_start_iso
        if learning_pool_size is not None:
            self._metadata["learning_pool_size"] = learning_pool_size
        if test_pool_size is not None:
            self._metadata["test_pool_size"] = test_pool_size
        if phase_transition_criterion is not None:
            self._metadata["phase_transition_criterion"] = phase_transition_criterion

    def merge_metadata(self, extra: Dict[str, Any]) -> None:
        """合并写入任意序列化元数据（如 pair_condition、直方图）。"""
        self._metadata.update(extra)

    def add_record(self, record: AnswerRecord) -> None:
        self.records.append(record.to_dict())

    def add_records(self, records: List[AnswerRecord]) -> None:
        for r in records:
            self.records.append(r.to_dict())

    def save_to_file(
        self,
        path: Optional[str] = None,
        format: str = "json",
    ) -> str:
        if path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            pid = (self.participant_id or "anonymous").replace(" ", "_")
            name = f"navigation6_practice_{pid}_{timestamp}"
            path = str(self.output_dir / f"{name}.{format}")
        if format == "csv":
            return self._save_csv(path)
        return self._save_json(path)

    def _save_json(self, filepath: str) -> str:
        data = {
            "timestamp": datetime.now().isoformat(),
            "total_records": len(self.records),
            "participant_id": self.participant_id,
            **self._metadata,
            "records": self.records,
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return filepath

    def _save_csv(self, filepath: str) -> str:
        fieldnames = [
            "phase", "trial_index", "map_id", "question_id", "current_code", "action_label",
            "correct_next_code", "participant_choice", "correct", "rt_ms", "attempt_count",
            "timestamp", "options", "first_response_ms",
        ]
        if not self.records:
            with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
            return filepath
        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for r in self.records:
                row = dict(r)
                if "options" in row and isinstance(row["options"], list):
                    row["options"] = "|".join(str(x) for x in row["options"])
                writer.writerow(row)
        return filepath
