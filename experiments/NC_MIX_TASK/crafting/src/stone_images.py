"""
九石状态对应的宝石位图：在多个目录中依次查找（避免空目录挡住后续路径）。

搜索顺序：
- `<项目根>/assets/stone`
- 自项目根向上祖先目录中的 `shared/assets/stone`（便于与 monorepo 共用素材）
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import pygame

from .stone_space import STONE_IDS, stone_index


def find_shared_assets_dir(crafting_root: Path, name: str) -> Optional[Path]:
    """
    从项目根向上查找存在的 `shared/assets/{name}` 目录。
    仅拷贝本文件夹运行时若无该路径，则只使用项目内 `assets/{name}`。
    """
    cur = Path(crafting_root).resolve()
    for _ in range(12):
        d = cur / "shared" / "assets" / name
        if d.is_dir():
            return d
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    return None


# 含常见大小写后缀（Windows 上部分素材为大写扩展名）；供 bottle 等复用
IMAGE_FILE_EXTENSIONS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".PNG",
    ".JPG",
    ".JPEG",
    ".WEBP",
    ".bmp",
    ".BMP",
)


def collect_stone_asset_dirs(crafting_root: Path) -> List[Path]:
    """
    收集所有存在的素材目录（按优先级）。
    若本地 assets/stone 为空目录，仍会先搜一遍，再搜 shared，避免「空文件夹挡住宝石图」。
    """
    local = Path(crafting_root) / "assets" / "stone"
    shared = find_shared_assets_dir(crafting_root, "stone")
    out: List[Path] = []
    seen_resolved = set()
    for d in (local, shared):
        if d is None or not d.is_dir():
            continue
        key = str(d.resolve())
        if key in seen_resolved:
            continue
        seen_resolved.add(key)
        out.append(d)
    return out


def _stem_candidates(state_id: str) -> List[str]:
    idx = stone_index(state_id)
    stems: List[str] = []
    if idx is not None:
        stems.extend(
            [
                f"stone_{idx:02d}",
                f"stone_{idx}",
                f"gem_{idx:02d}",
                f"gem_{idx}",
                f"{idx:02d}",
                str(idx),
                f"宝石{idx:02d}",
                f"宝石{idx}",
            ]
        )
    stems.append(state_id)
    return list(dict.fromkeys(stems))


def _iter_existing_files(dirs: List[Path], state_id: str):
    for asset_dir in dirs:
        for stem in _stem_candidates(state_id):
            for ext in IMAGE_FILE_EXTENSIONS:
                p = asset_dir / f"{stem}{ext}"
                if p.is_file():
                    yield p


def blit_image_fit(
    target: pygame.Surface,
    image: pygame.Surface,
    rect: pygame.Rect,
    padding: int = 6,
) -> None:
    iw, ih = image.get_size()
    rw = max(1, rect.w - 2 * padding)
    rh = max(1, rect.h - 2 * padding)
    scale = min(rw / iw, rh / ih)
    nw = max(1, int(iw * scale))
    nh = max(1, int(ih * scale))
    scaled = pygame.transform.smoothscale(image, (nw, nh))
    x = rect.x + (rect.w - nw) // 2
    y = rect.y + (rect.h - nh) // 2
    target.blit(scaled, (x, y))


class StoneImageCache:
    def __init__(self, search_dirs: List[Path]):
        self.search_dirs = [Path(d) for d in search_dirs]
        self._cache: Dict[str, Optional[pygame.Surface]] = {}

    def get(self, state_id: str) -> Optional[pygame.Surface]:
        if state_id in self._cache:
            return self._cache[state_id]

        surf: Optional[pygame.Surface] = None
        if self.search_dirs:
            for p in _iter_existing_files(self.search_dirs, state_id):
                try:
                    surf = pygame.image.load(str(p))
                    try:
                        surf = surf.convert_alpha()
                    except Exception:
                        pass
                    break
                except Exception:
                    continue

        self._cache[state_id] = surf
        return surf


def count_loaded_gems(cache: StoneImageCache) -> int:
    n = 0
    for sid in STONE_IDS:
        if cache.get(sid) is not None:
            n += 1
    return n
