"""
二次贝塞尔采样（与 navigation6 transit_curve_geometry 同源思路），供药水3曲线绘制与箭头朝向。
"""

from __future__ import annotations

import math
from typing import List, Tuple

TRANSIT_CURVE_MIN_LEN = 8.0
TRANSIT_CURVE_STEPS_MAX = 28
TRANSIT_CURVE_STEPS_MIN = 10


def quadratic_bezier_control(
    ax: float,
    ay: float,
    bx: float,
    by: float,
    seg_idx: int,
    manual_bias: float = 0.0,
) -> Tuple[float, float]:
    """线段中点沿法向偏移得到控制点；manual_bias 非零时调节弯曲张力。"""
    mx, my = (ax + bx) * 0.5, (ay + by) * 0.5
    dx, dy = bx - ax, by - ay
    L = math.hypot(dx, dy)
    if L < 1e-6:
        return mx, my
    nx, ny = -dy / L, dx / L
    base_strength = min(max(L * 0.36, 5.0), 24.0)
    auto_sign = 1.0 if seg_idx % 2 == 0 else -1.0
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
        t = i / max(1, steps)
        om = 1.0 - t
        x = om * om * p0[0] + 2.0 * om * t * pc[0] + t * t * p1[0]
        y = om * om * p0[1] + 2.0 * om * t * pc[1] + t * t * p1[1]
        out.append((x, y))
    return out


def potion3_sample_polyline(
    ax: float,
    ay: float,
    bx: float,
    by: float,
    seg_idx: int,
    offset_dx: float,
    offset_dy: float,
) -> List[Tuple[float, float]]:
    L = math.hypot(bx - ax, by - ay)
    if L < TRANSIT_CURVE_MIN_LEN:
        return [(ax, ay), (bx, by)]
    cx, cy = quadratic_bezier_control(ax, ay, bx, by, seg_idx, 0.0)
    cx += offset_dx
    cy += offset_dy
    n = int(L / 5.0)
    steps = max(TRANSIT_CURVE_STEPS_MIN, min(TRANSIT_CURVE_STEPS_MAX, n))
    return sample_quadratic_bezier((ax, ay), (cx, cy), (bx, by), steps)
