"""撤销 / 重做：单条药水出边的设置或清除。"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple


class EditorCommand:
    def execute(self) -> bool:
        raise NotImplementedError

    def undo(self) -> bool:
        raise NotImplementedError


class CommandHistory:
    def __init__(self, max_history: int = 200):
        self.history: List[EditorCommand] = []
        self.redo_stack: List[EditorCommand] = []
        self.max_history = max_history

    def execute_command(self, command: EditorCommand) -> bool:
        if command.execute():
            self.history.append(command)
            self.redo_stack.clear()
            if len(self.history) > self.max_history:
                self.history.pop(0)
            return True
        return False

    def undo(self) -> bool:
        if not self.history:
            return False
        cmd = self.history.pop()
        if cmd.undo():
            self.redo_stack.append(cmd)
            return True
        self.history.append(cmd)
        return False

    def redo(self) -> bool:
        if not self.redo_stack:
            return False
        cmd = self.redo_stack.pop()
        if cmd.execute():
            self.history.append(cmd)
            return True
        self.redo_stack.append(cmd)
        return False

    def clear(self) -> None:
        self.history.clear()
        self.redo_stack.clear()


class SetPotionEdgeCommand(EditorCommand):
    """potion_idx: 0..2；new_dst 为 None 表示删除 src 的出边。"""

    def __init__(
        self,
        potions: List[Dict[str, str]],
        potion_idx: int,
        src: str,
        old_dst: Optional[str],
        new_dst: Optional[str],
    ):
        self.potions = potions
        self.potion_idx = potion_idx
        self.src = src
        self.old_dst = old_dst
        self.new_dst = new_dst

    def execute(self) -> bool:
        d = self.potions[self.potion_idx]
        if self.new_dst is None:
            d.pop(self.src, None)
        else:
            d[self.src] = self.new_dst
        return True

    def undo(self) -> bool:
        d = self.potions[self.potion_idx]
        if self.old_dst is None:
            d.pop(self.src, None)
        else:
            d[self.src] = self.old_dst
        return True


def _nearly_zero_offset(o: Tuple[float, float]) -> bool:
    return abs(o[0]) < 0.5 and abs(o[1]) < 0.5


class SetPotion3ControlOffsetCommand(EditorCommand):
    """药水3 曲线控制点相对自动位置的像素偏移；接近 (0,0) 时从字典删除。"""

    def __init__(
        self,
        offsets: Dict[str, Tuple[float, float]],
        src: str,
        old: Optional[Tuple[float, float]],
        new: Optional[Tuple[float, float]],
    ):
        self.offsets = offsets
        self.src = src
        self.old = old
        self.new = new

    def execute(self) -> bool:
        if self.new is None or _nearly_zero_offset(self.new):
            self.offsets.pop(self.src, None)
        else:
            self.offsets[self.src] = self.new
        return True

    def undo(self) -> bool:
        if self.old is None or _nearly_zero_offset(self.old):
            self.offsets.pop(self.src, None)
        else:
            self.offsets[self.src] = self.old
        return True
