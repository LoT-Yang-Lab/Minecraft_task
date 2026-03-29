"""
厨房元素映射系统
将抽象的AND-OR-Tree结构映射为具体的厨房元素
方案 B：番茄、洋葱、胡萝卜、鸡肉、豆腐、鸡蛋；切/煮/合成；B/C/D；a1-a4；A
"""
from typing import Dict, Optional

# ==================== 基础食材映射 ====================

BASE_INGREDIENTS = {
    'e1': '番茄',
    'e2': '洋葱',
    'e3': '胡萝卜',
    'e4': '鸡肉',
    'e5': '豆腐',
    'e6': '鸡蛋',
}

# ==================== 第一层中间产物映射 ====================

INTERMEDIATE_PRODUCTS = {
    'b1': '番茄块',
    'b2': '洋葱丝',
    'b3': '胡萝卜丁',
    'c1': '煎鸡肉',
    'c2': '煎豆腐',
    'c3': '煎蛋',
    'd1': '番茄洋葱酱',
    'd2': '豆腐蛋饼',
    'd3': '洋葱蛋饼',
}

# ==================== 抽象类别映射 ====================

ABSTRACT_CATEGORIES = {
    'B': '蔬菜类',
    'C': '荤豆类',
    'D': '蛋类',
}

# ==================== 高级合成产物映射 ====================

ADVANCED_PRODUCTS = {
    'a1': '番茄鸡丁',
    'a2': '鸡肉煎蛋',
    'a3': '番茄煎蛋',
    'a4': '洋葱鸡丁',
}

# ==================== 最终目标映射 ====================

FINAL_TARGET = {
    'A': '完整套餐',
}

# ==================== 功能等价映射（OR规则） ====================

# 定义哪些中间产物可以等价于哪些抽象类别
FUNCTIONAL_EQUIVALENCE = {
    # b1,b2,b3,d1 都可以作为 B（蔬菜类）使用
    'b1': 'B',
    'b2': 'B',
    'b3': 'B',
    'd1': 'B',
    # c1,c2,d2 都可以作为 C（荤豆类）使用
    'c1': 'C',
    'c2': 'C',
    'd2': 'C',
    # c3,d3 都可以作为 D（蛋类）使用
    'c3': 'D',
    'd3': 'D',
    # a1,a2,a3,a4 都可以作为 A（完整套餐）使用
    'a1': 'A',
    'a2': 'A',
    'a3': 'A',
    'a4': 'A',
}

# ==================== 反向映射（从中文名称到内部ID） ====================

NAME_TO_ID = {}
for id, name in BASE_INGREDIENTS.items():
    NAME_TO_ID[name] = id
for id, name in INTERMEDIATE_PRODUCTS.items():
    NAME_TO_ID[name] = id
for id, name in ABSTRACT_CATEGORIES.items():
    NAME_TO_ID[name] = id
for id, name in ADVANCED_PRODUCTS.items():
    NAME_TO_ID[name] = id
for id, name in FINAL_TARGET.items():
    NAME_TO_ID[name] = id


# ==================== 工具函数 ====================

def get_display_name(item_id: str) -> str:
    """
    获取元素的显示名称
    
    Args:
        item_id: 元素ID（如'e1', 'b1', 'B'等）
        
    Returns:
        显示名称（中文）
    """
    if item_id in BASE_INGREDIENTS:
        return BASE_INGREDIENTS[item_id]
    elif item_id in INTERMEDIATE_PRODUCTS:
        return INTERMEDIATE_PRODUCTS[item_id]
    elif item_id in ABSTRACT_CATEGORIES:
        return ABSTRACT_CATEGORIES[item_id]
    elif item_id in ADVANCED_PRODUCTS:
        return ADVANCED_PRODUCTS[item_id]
    elif item_id in FINAL_TARGET:
        return FINAL_TARGET[item_id]
    else:
        return item_id  # 如果找不到，返回原ID


def get_functional_category(item_id: str) -> Optional[str]:
    """
    获取元素的功能等价类别
    
    Args:
        item_id: 元素ID
        
    Returns:
        功能等价类别ID（如'B', 'C', 'D'），如果没有则返回None
    """
    return FUNCTIONAL_EQUIVALENCE.get(item_id)


def can_use_as_category(item_id: str, category_id: str) -> bool:
    """
    检查元素是否可以作为某个类别使用
    
    Args:
        item_id: 元素ID
        category_id: 类别ID（'B', 'C', 'D'等）
        
    Returns:
        是否可以作为该类别使用
    """
    functional_category = get_functional_category(item_id)
    if functional_category:
        return functional_category == category_id
    # 如果元素本身就是类别，直接比较
    return item_id == category_id


def get_all_items_in_category(category_id: str) -> list:
    """
    获取某个类别下的所有元素ID
    
    Args:
        category_id: 类别ID（'B', 'C', 'D'等）
        
    Returns:
        该类别下的所有元素ID列表
    """
    items = []
    for item_id, func_cat in FUNCTIONAL_EQUIVALENCE.items():
        if func_cat == category_id:
            items.append(item_id)
    return items


# ==================== 颜色映射（用于UI显示） ====================

ITEM_COLORS = {
    # 基础食材
    'e1': (255, 99, 71),   # 番茄红
    'e2': (255, 218, 185), # 洋葱浅橙
    'e3': (255, 165, 0),   # 胡萝卜橙
    'e4': (255, 182, 193), # 鸡肉浅粉
    'e5': (255, 255, 240), # 豆腐米白
    'e6': (255, 228, 181), # 鸡蛋浅黄
    
    # 切产物
    'b1': (220, 100, 80),
    'b2': (230, 200, 170),
    'b3': (240, 180, 100),
    # 煮产物
    'c1': (255, 160, 140),
    'c2': (250, 245, 230),
    'c3': (255, 235, 180),
    # 合成产物
    'd1': (240, 120, 100),
    'd2': (255, 240, 200),
    'd3': (255, 220, 170),
    
    # 抽象类别
    'B': (200, 255, 200),
    'C': (255, 220, 200),
    'D': (255, 255, 200),
    
    # 高级产物
    'a1': (255, 140, 80),
    'a2': (255, 200, 150),
    'a3': (255, 160, 100),
    'a4': (255, 150, 90),
    
    # 最终目标
    'A': (255, 215, 0),
}


def get_item_color(item_id: str) -> tuple:
    """
    获取元素的颜色
    
    Args:
        item_id: 元素ID
        
    Returns:
        RGB颜色元组
    """
    return ITEM_COLORS.get(item_id, (200, 200, 200))
