"""
正式实验与练习共用的「按交通方式」动作文案（含被试按键）。

三种交通工具：
- 公交（bus）：Q(前) / E(后)
- 地铁（light_rail）：A(前) / D(后)
- 环线（metro）：W
"""
from typing import Dict

# 与正式实验按键对应：公交 Q/E、地铁 A/D、环线 W
TRANSIT_MODE_ACTION_LABEL: Dict[str, str] = {
    "bus": "公交",
    "light_rail": "地铁",
    "metro": "环线",
}

TRANSIT_MODE_KEY_LETTER: Dict[str, str] = {
    "bus": "Q",
    "light_rail": "A",
    "metro": "W",
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
        return f"{base}(后)"
    return f"{base}(前)"


def transit_mode_key_letter(mode: str) -> str:
    """正式实验中该交通方式对应的字母键（大写）。"""
    return TRANSIT_MODE_KEY_LETTER.get(mode, "?")
