#!/usr/bin/env python3
"""
测试合成流程：e1 → 切菜 → 烹饪 → 合成
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

from .items import Item, ItemType, create_item_from_element
from .overcooked_rule_bridge import apply_cut, apply_cook, apply_synthesis, can_synthesize
from .rule_systems import RuleComplexity

def test_cut_cook_synthesis():
    """测试切菜、烹饪、合成完整流程"""
    print("测试合成流程：e1 → 切菜 → 烹饪 → 合成")
    
    # 1. 创建基础食材 e1（白菜）
    item_e1 = create_item_from_element("e1", ItemType.RAW_INGREDIENT)
    print(f"1. 创建基础食材: {item_e1.name}, element_id: {item_e1.element_id}")
    
    # 2. 应用切菜操作
    item_b1 = apply_cut(item_e1, RuleComplexity.CFG)
    assert item_b1 is not None, "切菜失败：e1 应转换为 b1"
    print(f"2. 切菜结果: {item_b1.name}, element_id: {item_b1.element_id}")
    assert item_b1.element_id == "b1", f"预期 b1，实际 {item_b1.element_id}"
    
    # 3. 应用烹饪操作
    item_c1 = apply_cook(item_b1, RuleComplexity.CFG)
    assert item_c1 is not None, "烹饪失败：b1 应转换为 c1"
    print(f"3. 烹饪结果: {item_c1.name}, element_id: {item_c1.element_id}")
    assert item_c1.element_id == "c1", f"预期 c1，实际 {item_c1.element_id}"
    
    # 4. 创建另一个 B 类物品（例如 b2）
    item_b2 = create_item_from_element("b2", ItemType.CUT_INGREDIENT)
    print(f"4. 创建另一个 B 类物品: {item_b2.name}, element_id: {item_b2.element_id}")
    
    # 5. 测试合成：b1 + c1（B + C）应该可以合成 a1
    can_synth, result_id = can_synthesize(item_b1, item_c1)
    print(f"5. 合成检查 b1 + c1: 可以合成={can_synth}, 结果={result_id}")
    assert can_synth, "b1 + c1 应该可以合成"
    assert result_id == "a1", f"预期 a1，实际 {result_id}"
    
    # 6. 应用合成操作
    success, item_a1, structure = apply_synthesis(item_b1, item_c1, RuleComplexity.CFG)
    assert success and item_a1 is not None, "合成失败：b1 + c1 应生成 a1"
    print(f"6. 合成结果: {item_a1.name}, element_id: {item_a1.element_id}")
    assert item_a1.element_id == "a1", f"预期 a1，实际 {item_a1.element_id}"
    
    # 7. 测试功能等价：b2 也可以作为 B 类与 c1 合成
    can_synth2, result_id2 = can_synthesize(item_b2, item_c1)
    print(f"7. 功能等价检查 b2 + c1: 可以合成={can_synth2}, 结果={result_id2}")
    assert can_synth2, "b2 + c1 应该可以合成（功能等价）"
    assert result_id2 == "a1", f"预期 a1，实际 {result_id2}"
    
    # 8. 应用合成操作（功能等价）
    success2, item_a1_2, structure2 = apply_synthesis(item_b2, item_c1, RuleComplexity.CFG)
    assert success2 and item_a1_2 is not None, "合成失败：b2 + c1 应生成 a1"
    print(f"8. 功能等价合成结果: {item_a1_2.name}, element_id: {item_a1_2.element_id}")
    
    print("\n所有测试通过！完整流程验证成功。")

def test_order_system():
    """测试订单系统和功能等价匹配"""
    print("\n测试订单系统和功能等价匹配...")
    
    from .orders import OrderSystem
    from .items import create_item_from_element, ItemType
    
    order_system = OrderSystem()
    
    # 生成一个订单
    order_system.generate_new_order()
    order = order_system.current_order
    print(f"生成的订单: {order['name']} (所需元素: {order['required_element']})")
    print(f"备选元素: {order['alternative_elements']}")
    
    # 测试订单匹配
    # 创建符合订单的物品（例如 a1）
    item_a1 = create_item_from_element("a1", ItemType.COOKED_INGREDIENT)
    
    # 检查订单是否匹配
    result = order_system.check_completion(item_a1)
    print(f"订单匹配检查 a1: {result}")
    # 注意：订单可能要求 a1 或 a2，这里仅作演示
    
    print("订单系统测试完成。")

if __name__ == "__main__":
    try:
        test_cut_cook_synthesis()
        test_order_system()
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)