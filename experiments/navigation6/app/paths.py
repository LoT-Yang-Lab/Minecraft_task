"""
Navigation6 路径约定（运行侧/分析侧共用）。

说明：
- assets/：静态输入（地图等，可提交）
- data/：原始数据与中间数据（默认不提交）
- outputs/：生成物（默认不提交）
"""
from __future__ import annotations

import os
from typing import Optional


def get_nav6_root() -> str:
    # experiments/navigation6/app/paths.py -> experiments/navigation6
    return os.path.normpath(os.path.join(os.path.abspath(__file__), "..", ".."))


def assets_dir() -> str:
    return os.path.join(get_nav6_root(), "assets")


def maps_dir() -> str:
    new_dir = os.path.join(get_nav6_root(), "assets", "maps")
    if os.path.isdir(new_dir):
        return new_dir
    return os.path.join(get_nav6_root(), "maps")


def trial_sequences_dir() -> str:
    return os.path.join(assets_dir(), "trial_sequences")


def data_dir() -> str:
    return os.path.join(get_nav6_root(), "data")


def outputs_dir() -> str:
    return os.path.join(get_nav6_root(), "outputs")


def practice_raw_dir() -> str:
    return os.path.join(data_dir(), "raw", "practice")


def trajectory_raw_dir() -> str:
    return os.path.join(data_dir(), "raw", "trajectory")


def cogmap_viz_dir() -> str:
    # 认知地图三张 SVG
    return os.path.join(outputs_dir(), "viz", "cogmap")


def resolve_map_path(filename_or_path: str) -> str:
    if os.path.isabs(filename_or_path) and os.path.exists(filename_or_path):
        return filename_or_path
    return os.path.abspath(os.path.join(maps_dir(), filename_or_path))

