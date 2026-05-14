"""
Navigation6 站名：位置编码 1～9 与站名/形状映射，仅用于展示。
内部逻辑与数据记录仍使用数字编码。

站名使用彩色几何形状代替罗马数字，便于跨语言识别。
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

# 罗马数字站名（保留兼容，旧代码可能引用）
STATION_NAMES = [
    "Ⅰ站", "Ⅱ站", "Ⅲ站", "Ⅳ站", "Ⅴ站",
    "Ⅵ站", "Ⅶ站", "Ⅷ站", "Ⅸ站",
]

# 加载练习素材时的备选文件名（与 STATION_NAMES 顺序一致）
STATION_ICON_ENGLISH_NAMES = (
    "I",
    "II",
    "III",
    "IV",
    "V",
    "VI",
    "VII",
    "VIII",
    "IX",
)

# ── 彩色几何形状站名定义 ──────────────────────────────────
# shape: "triangle", "square", "circle", "diamond", "star",
#        "hexagon", "cross", "inv_triangle", "pentagon"
STATION_SHAPES: List[Dict[str, object]] = [
    # code 1: 红色三角形站 ▲
    {"shape": "triangle",     "color": (230, 60, 60),   "label": "红色三角形站"},
    # code 2: 蓝色正方形站 ■
    {"shape": "square",       "color": (60, 120, 230),  "label": "蓝色正方形站"},
    # code 3: 绿色圆形站 ●
    {"shape": "circle",       "color": (50, 180, 80),   "label": "绿色圆形站"},
    # code 4: 橙色菱形站 ◆
    {"shape": "diamond",      "color": (230, 150, 40),  "label": "橙色菱形站"},
    # code 5: 紫色五角星站 ★
    {"shape": "star",         "color": (160, 80, 220),  "label": "紫色五角星站"},
    # code 6: 粉色六边形站 ⬡
    {"shape": "hexagon",      "color": (230, 110, 170), "label": "粉色六边形站"},
    # code 7: 黄色十字站 ✚
    {"shape": "cross",        "color": (220, 200, 40),  "label": "黄色十字站"},
    # code 8: 青色倒三角站 ▼
    {"shape": "inv_triangle", "color": (40, 190, 200),  "label": "青色倒三角站"},
    # code 9: 棕色五边形站 ⬠
    {"shape": "pentagon",     "color": (160, 110, 60),  "label": "棕色五边形站"},
]


def station_shape_spec(code: int) -> Optional[Dict[str, object]]:
    """返回 code 对应的形状规格 dict，或 None。"""
    if 1 <= code <= len(STATION_SHAPES):
        return STATION_SHAPES[code - 1]
    return None


def draw_station_shape(
    surface,
    code: int,
    cx: int,
    cy: int,
    size: int = 20,
    *,
    outline_only: bool = False,
) -> None:
    """在 surface 上以 (cx, cy) 为中心绘制 station code 对应的彩色几何形状。

    需要 pygame 已初始化。大小由 size (半径/半宽) 控制。
    """
    import pygame
    spec = station_shape_spec(code)
    if spec is None:
        pygame.draw.circle(surface, (180, 180, 180), (cx, cy), size)
        return
    shape = spec["shape"]
    color: Tuple[int, int, int] = spec["color"]  # type: ignore[assignment]
    width = 2 if outline_only else 0

    if shape == "triangle":
        pts = [
            (cx, cy - size),
            (cx - size, cy + int(size * 0.75)),
            (cx + size, cy + int(size * 0.75)),
        ]
        pygame.draw.polygon(surface, color, pts, width)
    elif shape == "square":
        s = int(size * 0.85)
        pygame.draw.rect(surface, color, (cx - s, cy - s, s * 2, s * 2), width)
    elif shape == "circle":
        pygame.draw.circle(surface, color, (cx, cy), size, width)
    elif shape == "diamond":
        pts = [
            (cx, cy - size),
            (cx + size, cy),
            (cx, cy + size),
            (cx - size, cy),
        ]
        pygame.draw.polygon(surface, color, pts, width)
    elif shape == "star":
        _draw_star(surface, color, cx, cy, size, width)
    elif shape == "hexagon":
        pts = _regular_polygon_points(cx, cy, size, 6, -math.pi / 6)
        pygame.draw.polygon(surface, color, pts, width)
    elif shape == "cross":
        arm = max(2, int(size * 0.3))
        rects = [
            (cx - arm, cy - size, arm * 2, size * 2),
            (cx - size, cy - arm, size * 2, arm * 2),
        ]
        for r in rects:
            pygame.draw.rect(surface, color, r, width)
    elif shape == "inv_triangle":
        pts = [
            (cx, cy + size),
            (cx - size, cy - int(size * 0.75)),
            (cx + size, cy - int(size * 0.75)),
        ]
        pygame.draw.polygon(surface, color, pts, width)
    elif shape == "pentagon":
        pts = _regular_polygon_points(cx, cy, size, 5, -math.pi / 2)
        pygame.draw.polygon(surface, color, pts, width)
    else:
        import pygame
        pygame.draw.circle(surface, color, (cx, cy), size, width)


def _draw_star(surface, color, cx, cy, outer_r, width):
    """五角星。"""
    import pygame
    inner_r = outer_r * 0.4
    pts = []
    for i in range(10):
        angle = -math.pi / 2 + i * math.pi / 5
        r = outer_r if i % 2 == 0 else inner_r
        pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    pygame.draw.polygon(surface, color, pts, width)


def _regular_polygon_points(
    cx: float, cy: float, r: float, n: int, start_angle: float = 0,
) -> List[Tuple[float, float]]:
    return [
        (cx + r * math.cos(start_angle + 2 * math.pi * i / n),
         cy + r * math.sin(start_angle + 2 * math.pi * i / n))
        for i in range(n)
    ]


def code_to_station_icon_stem(code: int) -> Optional[str]:
    """1～9 返回罗马数字名（无「站」字），便于匹配 PNG 文件名；其它返回 None。"""
    if 1 <= code <= len(STATION_NAMES):
        return STATION_NAMES[code - 1].replace("站", "")
    return None


def code_to_station_name(code: int) -> str:
    """编码转站名：优先返回形状标签，兼容旧代码。"""
    if code == 0:
        return "无"
    spec = station_shape_spec(code)
    if spec is not None:
        return str(spec["label"])
    return f"站{code}"
