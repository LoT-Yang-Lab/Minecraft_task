"""
与地图编辑器 MapEditorNav6 一致的公交/地铁/轻轨路径曲线几何（二次贝塞尔 + 段参数）。
用于练习界面迷你地图等与编辑器相同的弧线路径显示。
"""
import math
from typing import Any, Dict, List, Tuple

# 与 map_editor_nav6.MapEditorNav6 保持一致
TRANSIT_CURVE_MIN_LEN = 8.0
TRANSIT_CURVE_STEPS_MAX = 28
TRANSIT_CURVE_STEPS_MIN = 10


def ensure_transit_segment_metadata(line: Dict[str, Any]) -> None:
    """segment_curve / segment_straight 与 path 段数对齐。"""
    path = line.get("path", [])
    n = max(0, len(path) - 1)
    sc = line.get("segment_curve")
    if not isinstance(sc, list):
        sc = []
    if len(sc) < n:
        sc = list(sc) + [0.0] * (n - len(sc))
    elif len(sc) > n:
        sc = sc[:n]
    line["segment_curve"] = [float(x) for x in sc]
    st = line.get("segment_straight")
    if not isinstance(st, list):
        st = []
    st_bool = [bool(x) for x in st[:n]]
    if len(st_bool) < n:
        st_bool.extend([False] * (n - len(st_bool)))
    else:
        st_bool = st_bool[:n]
    line["segment_straight"] = st_bool


def transit_bezier_control(
    ax: float,
    ay: float,
    bx: float,
    by: float,
    line_idx: int,
    seg_idx: int,
    manual_bias: float = 0.0,
) -> Tuple[float, float]:
    mx, my = (ax + bx) * 0.5, (ay + by) * 0.5
    dx, dy = bx - ax, by - ay
    L = math.hypot(dx, dy)
    if L < 1e-6:
        return mx, my
    nx, ny = -dy / L, dx / L
    base_strength = min(max(L * 0.36, 5.0), 24.0)
    auto_sign = 1.0 if (seg_idx + line_idx) % 2 == 0 else -1.0
    if abs(manual_bias) < 1e-9:
        sign = auto_sign
        strength = base_strength
    else:
        sign = 1.0 if manual_bias > 0 else -1.0
        mag = min(3.5, max(0.2, abs(manual_bias)))
        strength = base_strength * mag
    return mx + sign * strength * nx, my + sign * strength * ny


def sample_quadratic_bezier(
    p0: Tuple[float, float],
    pc: Tuple[float, float],
    p1: Tuple[float, float],
    steps: int,
) -> List[Tuple[float, float]]:
    out: List[Tuple[float, float]] = []
    for i in range(steps + 1):
        t = i / steps
        om = 1.0 - t
        x = om * om * p0[0] + 2.0 * om * t * pc[0] + t * t * p1[0]
        y = om * om * p0[1] + 2.0 * om * t * pc[1] + t * t * p1[1]
        out.append((x, y))
    return out


def transit_bezier_tangent_at_mid(
    ax: float,
    ay: float,
    bx: float,
    by: float,
    cx: float,
    cy: float,
) -> Tuple[float, float, float, float]:
    t = 0.5
    om = 1.0 - t
    px = om * om * ax + 2.0 * om * t * cx + t * t * bx
    py = om * om * ay + 2.0 * om * t * cy + t * t * by
    tx = 2.0 * om * (cx - ax) + 2.0 * t * (bx - cx)
    ty = 2.0 * om * (cy - ay) + 2.0 * t * (by - cy)
    tlen = math.hypot(tx, ty)
    if tlen < 1e-6:
        return px, py, 1.0, 0.0
    return px, py, tx / tlen, ty / tlen


def transit_segment_polyline(
    ax: float,
    ay: float,
    bx: float,
    by: float,
    line_idx: int,
    seg_idx: int,
    manual_bias: float = 0.0,
    force_straight: bool = False,
) -> List[Tuple[float, float]]:
    if force_straight:
        return [(ax, ay), (bx, by)]
    L = math.hypot(bx - ax, by - ay)
    if L < TRANSIT_CURVE_MIN_LEN:
        return [(ax, ay), (bx, by)]
    cx, cy = transit_bezier_control(ax, ay, bx, by, line_idx, seg_idx, manual_bias)
    n = int(L / 5.0)
    steps = max(TRANSIT_CURVE_STEPS_MIN, min(TRANSIT_CURVE_STEPS_MAX, n))
    return sample_quadratic_bezier((ax, ay), (cx, cy), (bx, by), steps)
