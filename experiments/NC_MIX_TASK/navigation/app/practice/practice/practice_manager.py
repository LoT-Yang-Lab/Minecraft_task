"""
练习管理器：学习阶段 / 测试阶段 / 完成，阶段切换条件，答题记录（含 question_id、options、first_response_ms）。
"""
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union, Callable, Tuple

from .question_generator import PracticeQuestion, QuestionGenerator, PoolItem


class PracticePhase(Enum):
    LEARNING = "learning"
    TEST = "test"
    COMPLETE = "complete"


@dataclass
class AnswerRecord:
    phase: str
    trial_index: int
    map_id: str
    question_id: str
    current_code: int
    action_label: str
    correct_next_code: int
    participant_choice: int
    correct: bool
    rt_ms: float
    attempt_count: int
    timestamp: float = field(default_factory=time.time)
    options: List[int] = field(default_factory=list)
    first_response_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "trial_index": self.trial_index,
            "map_id": self.map_id,
            "question_id": self.question_id,
            "current_code": self.current_code,
            "action_label": self.action_label,
            "correct_next_code": self.correct_next_code,
            "participant_choice": self.participant_choice,
            "correct": self.correct,
            "rt_ms": self.rt_ms,
            "attempt_count": self.attempt_count,
            "timestamp": self.timestamp,
            "options": self.options,
            "first_response_ms": self.first_response_ms,
        }


class PracticeManager:
    def __init__(
        self,
        question_generator: QuestionGenerator,
        learning_pool: List[PoolItem],
        test_pool: List[PoolItem],
        map_id: str,
        min_questions_learning: int = 8,
        min_questions_test: int = 6,
        consecutive_correct_learning: int = 3,
        accuracy_threshold_learning: float = 0.8,
        min_test_accuracy: float = 0.0,
        reset_on_failed_test: bool = False,
        shuffle_learning_between_cycles: bool = True,
        regenerate_pools: Optional[Callable[[], Tuple[List[PoolItem], List[PoolItem]]]] = None,
    ):
        self.question_generator = question_generator
        self.learning_pool = list(learning_pool)
        self.test_pool = list(test_pool)
        self.map_id = map_id
        self.shuffle_learning_between_cycles = shuffle_learning_between_cycles
        self.regenerate_pools = regenerate_pools
        self.min_questions_learning = min_questions_learning
        self.min_questions_test = min_questions_test
        self.consecutive_correct_learning = consecutive_correct_learning
        self.accuracy_threshold_learning = accuracy_threshold_learning
        self.min_test_accuracy = min_test_accuracy
        self.reset_on_failed_test = reset_on_failed_test

        self.current_phase = PracticePhase.LEARNING
        self.current_question: Optional[PracticeQuestion] = None
        self.answer_records: List[AnswerRecord] = []
        self.trial_index: int = 0
        self.question_start_time: float = 0.0
        self.practice_start_time: float = time.time()
        self.phase_start_times: Dict[PracticePhase, float] = {
            PracticePhase.LEARNING: time.time(),
        }
        self._current_attempt_count: int = 0
        self._learning_index: int = 0
        self._test_index: int = 0
        self._first_response_time: Optional[float] = None
        self._failed_test_restarts: int = 0

    def _reset_for_new_round(self) -> None:
        """在测试阶段正确率不足时，重新开始一轮学习+测试。"""
        self.current_phase = PracticePhase.LEARNING
        self.current_question = None
        self.trial_index = 0
        self.question_start_time = 0.0
        self.practice_start_time = time.time()
        self.phase_start_times = {
            PracticePhase.LEARNING: time.time(),
        }
        self._current_attempt_count = 0
        self._learning_index = 0
        self._test_index = 0
        self._first_response_time = None
        self._failed_test_restarts += 1
        if self.regenerate_pools is not None:
            lp, tp = self.regenerate_pools()
            self.learning_pool = list(lp)
            self.test_pool = list(tp)

    def start_new_question(self) -> Optional[PracticeQuestion]:
        if self.current_phase == PracticePhase.LEARNING:
            if not self.learning_pool:
                return None
            if self.shuffle_learning_between_cycles:
                if self._learning_index > 0 and self._learning_index % len(self.learning_pool) == 0:
                    self.question_generator.shuffle_learning_pool(self.learning_pool)
                item = self.learning_pool[self._learning_index % len(self.learning_pool)]
            else:
                if self._learning_index >= len(self.learning_pool):
                    return None
                item = self.learning_pool[self._learning_index]
            self._learning_index += 1
            self.current_question = self.question_generator.build_question_from_item(item)
        elif self.current_phase == PracticePhase.TEST:
            if self._test_index >= len(self.test_pool):
                return None
            item = self.test_pool[self._test_index]
            self._test_index += 1
            self.current_question = self.question_generator.build_question_from_item(item)
        else:
            return None

        if self.current_question:
            self.trial_index += 1
            self.question_start_time = time.time()
            self._current_attempt_count = 0
            self._first_response_time = None
        return self.current_question

    def submit_answer(self, choice_code: Union[int, str]) -> tuple[bool, bool]:
        if not self.current_question:
            return False, False

        choice_int = int(choice_code) if isinstance(choice_code, str) else choice_code
        if self._first_response_time is None and self.current_phase == PracticePhase.LEARNING:
            self._first_response_time = time.time()

        correct = choice_int == self.current_question.correct_next_code
        rt_ms = (time.time() - self.question_start_time) * 1000
        self._current_attempt_count += 1

        if self.current_phase == PracticePhase.LEARNING:
            if not correct:
                return False, False
            first_response_ms = None
            if self._first_response_time is not None:
                first_response_ms = (self._first_response_time - self.question_start_time) * 1000
            record = AnswerRecord(
                phase=self.current_phase.value,
                trial_index=self.trial_index,
                map_id=self.map_id,
                question_id=self.current_question.question_id,
                current_code=self.current_question.current_code,
                action_label=self.current_question.action_label,
                correct_next_code=self.current_question.correct_next_code,
                participant_choice=choice_int,
                correct=True,
                rt_ms=rt_ms,
                attempt_count=self._current_attempt_count,
                options=list(self.current_question.options),
                first_response_ms=first_response_ms,
            )
            self.answer_records.append(record)
            phase_changed = self._check_phase_transition()
            return True, phase_changed

        record = AnswerRecord(
            phase=self.current_phase.value,
            trial_index=self.trial_index,
            map_id=self.map_id,
            question_id=self.current_question.question_id,
            current_code=self.current_question.current_code,
            action_label=self.current_question.action_label,
            correct_next_code=self.current_question.correct_next_code,
            participant_choice=choice_int,
            correct=correct,
            rt_ms=rt_ms,
            attempt_count=1,
            options=list(self.current_question.options),
            first_response_ms=rt_ms,
        )
        self.answer_records.append(record)
        phase_changed = self._check_phase_transition()
        return correct, phase_changed

    def _check_phase_transition(self) -> bool:
        if self.current_phase == PracticePhase.LEARNING:
            if self._can_enter_test():
                self.current_phase = PracticePhase.TEST
                self.phase_start_times[PracticePhase.TEST] = time.time()
                return True
        elif self.current_phase == PracticePhase.TEST:
            if self._can_complete():
                self.current_phase = PracticePhase.COMPLETE
                return True
        return False

    def _learning_records(self) -> List[AnswerRecord]:
        t0 = self.phase_start_times.get(PracticePhase.LEARNING, 0)
        t1 = self.phase_start_times.get(PracticePhase.TEST, float("inf"))
        return [r for r in self.answer_records if t0 <= r.timestamp < t1]

    def _test_records(self) -> List[AnswerRecord]:
        t0 = self.phase_start_times.get(PracticePhase.TEST, 0)
        return [r for r in self.answer_records if r.timestamp >= t0]

    def _can_enter_test(self) -> bool:
        recs = self._learning_records()
        if len(recs) < self.min_questions_learning:
            return False
        accuracy = sum(1 for r in recs if r.correct) / len(recs)
        if accuracy < self.accuracy_threshold_learning:
            return False
        consecutive = 0
        for r in reversed(recs):
            if r.correct:
                consecutive += 1
            else:
                break
        return consecutive >= self.consecutive_correct_learning

    def _can_complete(self) -> bool:
        tr = self._test_records()
        if len(tr) < self.min_questions_test:
            return False
        if self.min_test_accuracy <= 0.0:
            return True
        correct = sum(1 for r in tr if r.correct)
        accuracy = correct / len(tr) if tr else 0.0
        if accuracy >= self.min_test_accuracy:
            return True
        if self.reset_on_failed_test:
            self._reset_for_new_round()
            return False
        return True

    def get_current_phase(self) -> PracticePhase:
        return self.current_phase

    def is_learning_phase(self) -> bool:
        return self.current_phase == PracticePhase.LEARNING

    def get_statistics(self) -> Dict:
        lr = self._learning_records()
        tr = self._test_records()
        lc = sum(1 for r in lr if r.correct)
        tc = sum(1 for r in tr if r.correct)
        return {
            "learning_count": len(lr),
            "learning_correct": lc,
            "learning_accuracy": lc / len(lr) if lr else 0.0,
            "test_count": len(tr),
            "test_correct": tc,
            "test_accuracy": tc / len(tr) if tr else 0.0,
            "practice_duration": time.time() - self.practice_start_time,
            "failed_test_restarts": self._failed_test_restarts,
        }

    def is_complete(self) -> bool:
        return self.current_phase == PracticePhase.COMPLETE

    def get_all_records(self) -> List[AnswerRecord]:
        return self.answer_records.copy()

    def get_learning_pool_size(self) -> int:
        return len(self.learning_pool)

    def get_test_pool_size(self) -> int:
        return len(self.test_pool)
