"""
三瓶魔法药水位图：项目内 assets/bottle，以及祖先目录中的 shared/assets/bottle。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import pygame

from .stone_images import IMAGE_FILE_EXTENSIONS, find_shared_assets_dir


def collect_bottle_asset_dirs(crafting_root: Path) -> List[Path]:
    local = Path(crafting_root) / "assets" / "bottle"
    shared = find_shared_assets_dir(crafting_root, "bottle")
    out: List[Path] = []
    seen = set()
    for d in (local, shared):
        if d is None or not d.is_dir():
            continue
        key = str(d.resolve())
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out


def _bottle_stems(index: int) -> List[str]:
    """index 为 1 / 2 / 3，对应药水 1～3。"""
    if index < 1 or index > 3:
        return []
    return list(
        dict.fromkeys(
            [
                f"bottle_{index:02d}",
                f"bottle_{index}",
                f"potion_{index:02d}",
                f"potion_{index}",
                f"magic_bottle_{index:02d}",
                f"magic_bottle_{index}",
                f"药水{index}",
                f"魔法药水{index}",
                str(index),
            ]
        )
    )


def _iter_bottle_files(dirs: List[Path], index: int):
    for asset_dir in dirs:
        for stem in _bottle_stems(index):
            for ext in IMAGE_FILE_EXTENSIONS:
                p = asset_dir / f"{stem}{ext}"
                if p.is_file():
                    yield p


class BottleImageCache:
    def __init__(self, search_dirs: List[Path]):
        self.search_dirs = [Path(d) for d in search_dirs]
        self._cache: Dict[int, Optional[pygame.Surface]] = {}

    def get(self, potion_index: int) -> Optional[pygame.Surface]:
        if potion_index in self._cache:
            return self._cache[potion_index]

        surf: Optional[pygame.Surface] = None
        if self.search_dirs and 1 <= potion_index <= 3:
            for p in _iter_bottle_files(self.search_dirs, potion_index):
                try:
                    surf = pygame.image.load(str(p))
                    try:
                        surf = surf.convert_alpha()
                    except Exception:
                        pass
                    break
                except Exception:
                    continue

        self._cache[potion_index] = surf
        return surf


def count_loaded_bottles(cache: BottleImageCache) -> int:
    return sum(1 for i in (1, 2, 3) if cache.get(i) is not None)
