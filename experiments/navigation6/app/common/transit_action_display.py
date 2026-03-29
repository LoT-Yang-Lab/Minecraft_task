"""
正式实验与练习共用的「按交通方式」动作文案（含被试按键）。
地铁在界面中称为「高铁」，与 Q/W/E 按键说明一致。
"""
from typing import Dict

# 与正式实验按键对应：公交 Q、轻轨 W、高铁（地铁）E
TRANSIT_MODE_ACTION_LABEL: Dict[str, str] = {
    "bus": "公交（Q）",
    "light_rail": "轻轨（W）",
    "metro": "高铁（E）",
}

TRANSIT_MODE_KEY_LETTER: Dict[str, str] = {
    "bus": "Q",
    "light_rail": "W",
    "metro": "E",
}


def transit_mode_action_display_label(mode: str) -> str:
    """当前可执行的交通类别 + 按键，不含线路序号。"""
    return TRANSIT_MODE_ACTION_LABEL.get(mode, mode)


def transit_mode_action_with_direction_label(mode: str, direction: str) -> str:
    """
    交通类别标签 + 方向后缀。
    direction: "next" | "prev"
    """
    base = transit_mode_action_display_label(mode)
    if direction == "prev":
        return f"{base} 上一站"
    return f"{base} 下一站"


def transit_mode_key_letter(mode: str) -> str:
    """正式实验中该交通方式对应的字母键（大写）。"""
    return TRANSIT_MODE_KEY_LETTER.get(mode, "?")
