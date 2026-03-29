#!/usr/bin/env python3
"""
测试新版厨房布局
"""
import sys
import os

# 添加项目根目录到路径
current_file = os.path.abspath(__file__)
project_root = os.path.dirname(current_file)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import pygame
pygame.init()

from .kitchen import Kitchen

def test_layout_for_map(map_type):
    """测试指定地图类型的布局"""
    print(f"\n{'='*60}")
    print(f"测试地图类型: {map_type}")
    print(f"{'='*60}")
    
    # 创建厨房
    kitchen = Kitchen(800, 600, map_type)
    
    # 统计物品分布
    ingredient_count = 0
    cutting_board_count = 0
    stove_count = 0
    plate_count = 0
    generator_rooms = []
    
    for rid, room in kitchen.rooms.items():
        room_x, room_y = room.logical_pos
        print(f"\n房间 ({room_x}, {room_y}) - ID: {rid}:")
        
        if room.cell_items:
            for (dx, dy), item_type in room.cell_items.items():
                print(f"  格子({dx},{dy}): {item_type}")
                
                # 统计数量
                if item_type.startswith('generator_'):
                    ingredient_count += 1
                    generator_rooms.append((room_x, room_y))
                    # 检查是否在中心
                    if (dx, dy) != (1, 1):
                        print(f"  [WARNING]  警告: 食材生成器不在中心(1,1)，在({dx},{dy})")
                elif item_type == 'cutting_board':
                    cutting_board_count += 1
                elif item_type == 'stove':
                    stove_count += 1
                elif item_type == 'plate':
                    plate_count += 1
        else:
            print("  无物品")
    
    # 输出统计信息
    print(f"\n{'='*60}")
    print(f"统计信息 ({map_type}):")
    print(f"  食材生成器: {ingredient_count} 个")
    print(f"  切割板: {cutting_board_count} 个")
    print(f"  炉子: {stove_count} 个")
    print(f"  盘子: {plate_count} 个")
    
    # 检查特殊区域
    print(f"\n特殊区域:")
    print(f"  上菜区: 房间 {kitchen.serve_room_id}, 格子 {kitchen.serve_cell}")
    print(f"  垃圾桶: 房间 {kitchen.trash_room_id}, 格子 {kitchen.trash_cell}")
    
    # 检查玩家起始位置
    print(f"\n起始房间ID: {kitchen.start_rid}")
    
    return True

def test_all_maps():
    """测试所有地图类型"""
    map_types = ["Grid", "Barbell", "Path", "Ladder"]
    
    all_passed = True
    for map_type in map_types:
        try:
            if not test_layout_for_map(map_type):
                all_passed = False
        except Exception as e:
            print(f"\n[FAILED] 测试失败 {map_type}: {e}")
            import traceback
            traceback.print_exc()
            all_passed = False
    
    return all_passed

def test_player_start_positions():
    """测试玩家起始位置智能选择"""
    print(f"\n{'='*60}")
    print(f"测试玩家起始位置智能选择")
    print(f"{'='*60}")
    
    map_types = ["Grid", "Barbell", "Path", "Ladder"]
    
    for map_type in map_types:
        print(f"\n地图类型: {map_type}")
        kitchen = Kitchen(800, 600, map_type)
        
        # 获取起始房间
        start_room = kitchen.rooms.get(kitchen.start_rid)
        if start_room:
            lx, ly = start_room.logical_pos
            start_cell = kitchen.get_smart_player_start_cell(lx, ly)
            print(f"  起始房间: ({lx}, {ly})")
            print(f"  智能起始格子: {start_cell}")
            
            # 检查是否被占用
            if kitchen._is_cell_occupied(lx, ly, start_cell[0], start_cell[1]):
                print(f"  [WARNING]  警告: 起始格子 {start_cell} 被占用!")
            else:
                print(f"  [OK] 起始格子 {start_cell} 空闲")
        else:
            print(f"  [FAILED] 起始房间不存在")
    
    return True

if __name__ == "__main__":
    print("开始测试新版厨房布局...")
    
    try:
        # 测试所有地图布局
        layout_passed = test_all_maps()
        
        # 测试玩家起始位置
        player_start_passed = test_player_start_positions()
        
        if layout_passed and player_start_passed:
            print(f"\n{'='*60}")
            print("[PASSED] 所有测试通过!")
            print(f"{'='*60}")
        else:
            print(f"\n{'='*60}")
            print("[FAILED] 测试失败!")
            print(f"{'='*60}")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n[FAILED] 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)