#!/usr/bin/env python3
"""
测试Shift多选功能
"""
import sys
import os

# 添加项目根目录到路径
current_file = os.path.abspath(__file__)
project_root = os.path.dirname(current_file)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 设置虚拟显示器避免打开窗口
import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'

import pygame
pygame.init()

from shared.common.recorder import RLDataRecorder
from .game_overcooked_simple import GameOvercooked
from .items import Item, ItemType

def test_toggle_select():
    """测试toggle_select函数"""
    print("测试Shift多选功能...")
    
    # 创建数据记录器（不实际记录）
    recorder = RLDataRecorder()
    
    # 创建游戏实例（使用虚拟显示器）
    game = GameOvercooked(recorder, map_type="Grid", enable_experiment=False)
    
    # 添加一些测试物品到背包
    # 创建一些基本物品
    item_e1 = Item(item_type=ItemType.RAW_INGREDIENT, name="generator_e1", element_id="e1")
    item_e2 = Item(item_type=ItemType.RAW_INGREDIENT, name="generator_e2", element_id="e2")
    item_b1 = Item(item_type=ItemType.CUT_INGREDIENT, name="b1", element_id="b1")
    
    # 清空背包并放入物品
    game.player.backpack_items = [item_e1, item_e2, item_b1, None]
    
    print(f"初始背包: {[item.name if item else '空' for item in game.player.backpack_items]}")
    print(f"初始选中物品: {game.selected_items}")
    
    # 测试1: 单选（无Shift）
    print("\n测试1: 单选槽位0")
    game.toggle_select(0, shift_pressed=False)
    print(f"选中物品: {game.selected_items}")
    assert game.selected_items == [0], f"预期[0]，实际{game.selected_items}"
    
    # 测试2: Shift添加选择
    print("\n测试2: Shift+点击槽位1")
    game.toggle_select(1, shift_pressed=True)
    print(f"选中物品: {game.selected_items}")
    assert game.selected_items == [0, 1], f"预期[0,1]，实际{game.selected_items}"
    
    # 测试3: Shift添加第三个物品（应该限制为2个）
    print("\n测试3: Shift+点击槽位2（应限制为2个）")
    game.toggle_select(2, shift_pressed=True)
    print(f"选中物品: {game.selected_items}")
    assert len(game.selected_items) == 2, f"预期长度为2，实际{len(game.selected_items)}"
    # 检查是否移除了最早的选择（槽位0）
    assert game.selected_items == [1, 2], f"预期[1,2]，实际{game.selected_items}"
    
    # 测试4: Shift取消选择
    print("\n测试4: Shift+点击已选槽位1（取消选择）")
    game.toggle_select(1, shift_pressed=True)
    print(f"选中物品: {game.selected_items}")
    assert game.selected_items == [2], f"预期[2]，实际{game.selected_items}"
    
    # 测试5: 单选清空Shift选择
    print("\n测试5: 单击槽位3（空槽位）")
    game.toggle_select(3, shift_pressed=False)
    print(f"选中物品: {game.selected_items}")
    assert game.selected_items == [], f"预期[]，实际{game.selected_items}"
    
    # 测试6: 选中空槽位
    print("\n测试6: Shift+点击空槽位3")
    game.toggle_select(3, shift_pressed=True)
    print(f"选中物品: {game.selected_items}")
    # 空槽位不应被选中
    assert game.selected_items == [], f"预期[]，实际{game.selected_items}"
    
    print("\n所有测试通过！")

if __name__ == "__main__":
    try:
        test_toggle_select()
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)