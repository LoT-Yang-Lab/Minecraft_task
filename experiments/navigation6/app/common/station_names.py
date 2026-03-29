"""
Navigation6 水果城市：位置编码 1～9 与站名映射，仅用于展示。
内部逻辑与数据记录仍使用数字编码。
"""
from __future__ import annotations

from typing import Optional
# 9 种水果站（与 build_position_encoding 的字典序 1～9 对应）
STATION_NAMES = [
    "香蕉站", "苹果站", "橙子站", "葡萄站", "草莓站",
    "西瓜站", "桃子站", "樱桃站", "芒果站",
]

# 加载练习素材时的备选文件名（与 STATION_NAMES 顺序一致）
STATION_ICON_ENGLISH_NAMES = (
    "banana",
    "apple",
    "orange",
    "grape",
    "strawberry",
    "watermelon",
    "peach",
    "cherry",
    "mango",
)


def code_to_station_icon_stem(code: int) -> Optional[str]:
    """1～9 返回中文水果名（无「站」字），便于匹配 PNG 文件名；其它返回 None。"""
    if 1 <= code <= len(STATION_NAMES):
        return STATION_NAMES[code - 1].replace("站", "")
    return None


def code_to_station_name(code: int) -> str:
    """编码转站名：1～9 返回对应水果站名，0 返回「无」，其它返回 站{code}。"""
    if code == 0:
        return "无"
    if 1 <= code <= len(STATION_NAMES):
        return STATION_NAMES[code - 1]
    return f"站{code}"
