from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pygame


@dataclass
class RuntimeContext:
    screen: pygame.Surface
    clock: pygame.time.Clock
    participant_id: str
    project_root: Path
    nav_output_root: Path
    crafting_output_root: Path
    mix_output_root: Path


@dataclass
class SessionResult:
    domain: str
    session: int
    output_path: Optional[str] = None
    interrupted: bool = False
