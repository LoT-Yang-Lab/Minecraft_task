from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Set


@dataclass(frozen=True)
class AgentAction:
    action_key: str
    extra: Optional[object]
    next_code: int
    label: str = ""


@dataclass(frozen=True)
class AgentObservation:
    current_code: int
    target_a: int
    target_b: int
    reached_targets: Set[int]

    @property
    def remaining_targets(self) -> List[int]:
        out: List[int] = []
        if self.target_a not in self.reached_targets:
            out.append(self.target_a)
        if self.target_b not in self.reached_targets:
            out.append(self.target_b)
        return out


class BaseNav6Agent(ABC):
    @abstractmethod
    def select_action(self, obs: AgentObservation, actions: List[AgentAction]) -> AgentAction:
        raise NotImplementedError

