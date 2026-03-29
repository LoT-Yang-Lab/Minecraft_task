#!/usr/bin/env python3
"""
快速测试新版布局的视觉效果
"""
import sys
import os
current_file = os.path.abspath(__file__)
project_root = os.path.dirname(current_file)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import pygame
pygame.init()

# 设置一个虚拟显示器（避免打开窗口）
import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'

from .kitchen import Kitchen
from .game_overcooked_simple import GameOvercooked
from shared.common.recorder import RLDataRecorder

print("测试新版布局视觉效果...")

# 测试所有地图类型
map_types = ["Grid", "Barbell", "Path", "Ladder"]
for map_type in map_types:
    print(f"\n{'='*60}")
    print(f"地图类型: {map_type}")
    print(f"{'='*60}")
    
    try:
        # 创建厨房实例
        kitchen = Kitchen(800, 600, map_type)
        print(f"  厨房创建成功，房间数: {len(kitchen.rooms)}")
        
        # 检查特殊区域
        print(f"  特殊区域 - 上菜区: 房间 {kitchen.serve_room_id}, 格子 {kitchen.serve_cell}")
        print(f"  特殊区域 - 垃圾桶: 房间 {kitchen.trash_room_id}, 格子 {kitchen.trash_cell}")
        
        # 检查玩家起始位置
        start_room = kitchen.rooms.get(kitchen.start_rid)
        if start_room:
            lx, ly = start_room.logical_pos
            start_cell = kitchen.get_smart_player_start_cell(lx, ly)
            print(f"  玩家起始位置: 房间 ({lx}, {ly}), 格子 {start_cell}")
        
        # 检查物品分布
        ingredient_count = 0
        workstation_count = 0
        for rid, room in kitchen.rooms.items():
            ingredient_count += sum(1 for item in room.cell_items.values() if item.startswith('generator_'))
            workstation_count += sum(1 for item in room.cell_items.values() if item in ['cutting_board', 'stove', 'plate'])
        
        print(f"  食材生成器总数: {ingredient_count}")
        print(f"  工作台总数: {workstation_count}")
        
        # 尝试创建游戏实例（不显示窗口）
        print("  尝试创建游戏实例...")
        recorder = RLDataRecorder()
        game = GameOvercooked(recorder, map_type=map_type, enable_experiment=False)
        print(f"  游戏实例创建成功")
        
        # 检查玩家位置是否有效
        if game.player:
            print(f"  玩家位置: 房间 ({game.player.room_x}, {game.player.room_y}), 格子 ({game.player.cell_dx}, {game.player.cell_dy})")
        
        print(f"  [PASSED] {map_type} 布局测试通过")
        
    except Exception as e:
        print(f"  [FAILED] {map_type} 布局测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

print(f"\n{'='*60}")
print("所有地图类型布局测试通过！")
print("建议运行主游戏进行视觉检查:")
print("  python main_overcooked.py")
print(f"{'='*60}")