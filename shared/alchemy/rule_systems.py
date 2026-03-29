"""
规则系统定义
支持三种规则复杂度水平：无算子、CFG、Lexicalized PCFG
"""
from typing import Dict, List, Tuple, Optional, Set
from enum import Enum


class RuleComplexity(Enum):
    """规则复杂度水平"""
    NO_OPERATOR = "no_operator"      # 无算子（基线条件）
    CFG = "cfg"                      # 上下文无关语法
    LEXICALIZED_PCFG = "lexicalized_pcfg"  # 词汇化概率上下文无关语法


class PolishNotationParser:
    """前缀表达式（Polish Notation）解析器"""
    
    @staticmethod
    def parse(expression: str) -> List[str]:
        """
        解析前缀表达式
        
        Args:
            expression: 前缀表达式字符串，如 "(合成 (切碎 青菜) (翻炒 蘑菇))"
            
        Returns:
            解析后的token列表
        """
        # 简化解析：移除括号，按空格分割
        tokens = expression.replace('(', ' ( ').replace(')', ' ) ').split()
        return [t for t in tokens if t.strip()]
    
    @staticmethod
    def build_tree(expression: str) -> Dict:
        """
        构建语法树
        
        Args:
            expression: 前缀表达式字符串
            
        Returns:
            语法树字典
        """
        tokens = PolishNotationParser.parse(expression)
        if not tokens:
            return {}
        
        def parse_recursive(idx: int) -> Tuple[Dict, int]:
            if idx >= len(tokens):
                return {}, idx
            
            token = tokens[idx]
            
            # 如果是操作符
            if token in ['合成', '切碎', '翻炒', '焯水', '煮制', '爆香', '加味', '炒香', '煨煮', '收汁']:
                node = {
                    'type': 'operator',
                    'value': token,
                    'children': []
                }
                idx += 1
                # 解析子节点
                while idx < len(tokens) and tokens[idx] != ')':
                    if tokens[idx] == '(':
                        idx += 1
                    child, idx = parse_recursive(idx)
                    if child:
                        node['children'].append(child)
                    if idx < len(tokens) and tokens[idx] == ')':
                        idx += 1
                        break
                return node, idx
            else:
                # 叶子节点（操作数）
                return {
                    'type': 'operand',
                    'value': token
                }, idx + 1
        
        tree, _ = parse_recursive(0)
        return tree
    
    @staticmethod
    def to_string(tree: Dict) -> str:
        """将语法树转换回前缀表达式字符串"""
        if tree.get('type') == 'operator':
            children_str = ' '.join([PolishNotationParser.to_string(c) for c in tree.get('children', [])])
            return f"({tree['value']} {children_str})"
        else:
            return tree.get('value', '')


# ==================== 水平1：无算子（基线条件） ====================

RECIPES_NO_OPERATOR = {
    # 无合成操作，只需收集基础食材（方案 B 命名）
    'collect_food': {
        '番茄': ['e1'],
        '洋葱': ['e2'],
        '胡萝卜': ['e3'],
        '鸡肉': ['e4'],
        '豆腐': ['e5'],
        '鸡蛋': ['e6'],
    }
}


def get_no_operator_recipes() -> Dict:
    """获取无算子条件的配方"""
    return RECIPES_NO_OPERATOR


# ==================== 水平2：CFG（上下文无关语法） ====================

# 方案 B：切 e1/e2/e3→b1/b2/b3、煮 e4/e5/e6→c1/c2/c3 为单目操作，不在此列出；
# 此处仅二元合成规则（用于 can_merge_cfg）

RECIPES_CFG = {
    # 第一层合成：e+e→d
    '合成_e1_e2': {
        'ingredients': ['e1', 'e2'],
        'result': 'd1',
        'structure': '(合成 e1 e2)'
    },
    '合成_e5_e6': {
        'ingredients': ['e5', 'e6'],
        'result': 'd2',
        'structure': '(合成 e5 e6)'
    },
    '合成_e2_e6': {
        'ingredients': ['e2', 'e6'],
        'result': 'd3',
        'structure': '(合成 e2 e6)'
    },
    # 高级合成：B/C/D 两两组合（功能等价匹配在 can_merge_cfg 中处理）
    '高级合成_B_C': {
        'ingredients': ['B', 'C'],
        'result': 'a1',
        'structure': '(合成 B C)'
    },
    '高级合成_C_D': {
        'ingredients': ['C', 'D'],
        'result': 'a2',
        'structure': '(合成 C D)'
    },
    '高级合成_B_D': {
        'ingredients': ['B', 'D'],
        'result': 'a3',
        'structure': '(合成 B D)'
    }
}


def get_cfg_recipes() -> Dict:
    """获取CFG条件的配方"""
    return RECIPES_CFG


def can_merge_cfg(item1: str, item2: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    CFG条件下的合成检查（支持功能等价）
    
    Returns:
        (是否可以合成, 合成结果, 结构表达式)
    """
    # 尝试导入kitchen_elements以支持功能等价
    try:
        from .kitchen_elements import can_use_as_category
        HAS_KITCHEN_ELEMENTS = True
    except ImportError:
        HAS_KITCHEN_ELEMENTS = False
    
    items = [item1, item2]
    
    for key, recipe in RECIPES_CFG.items():
        if 'ingredients' not in recipe:
            continue
            
        ingredients = recipe['ingredients']
        if len(ingredients) != 2:
            continue
        
        # 检查物品是否匹配配料（考虑功能等价）
        matched = False
        if HAS_KITCHEN_ELEMENTS:
            # 使用功能等价检查：物品可以匹配抽象类别
            # 尝试所有排列（2个物品，2个配料）
            from itertools import permutations
            for perm in permutations(range(2)):
                match_all = True
                for i in range(2):
                    item = items[perm[i]]
                    ingredient = ingredients[i]
                    # 如果配料是抽象类别（B、C、D等），检查物品是否可以作为该类别使用
                    if ingredient in ['B', 'C', 'D', 'A']:
                        if not can_use_as_category(item, ingredient):
                            match_all = False
                            break
                    else:
                        # 具体物品必须完全匹配
                        if item != ingredient:
                            match_all = False
                            break
                if match_all:
                    matched = True
                    break
        else:
            # 没有功能等价支持，直接比较排序后的列表
            if sorted(items) == sorted(ingredients):
                matched = True
        
        if matched:
            result = recipe['result']
            structure = recipe.get('structure', '')
            return True, result, structure
    
    return False, None, None


# ==================== 水平3：Lexicalized PCFG（词汇化概率上下文无关语法） ====================

# 方案 B 词汇化：与 CFG 同一套 result/ingredients，配方键为具体菜名

RECIPES_LEXICALIZED_PCFG = {
    # 第一层合成（与 CFG 一致，用 id）
    '番茄洋葱酱': {
        'ingredients': ['e1', 'e2'],
        'result': 'd1',
        'structure': '(合成 番茄 洋葱)',
        'lexical_binding': {'番茄': 'e1', '洋葱': 'e2'}
    },
    '豆腐蛋饼': {
        'ingredients': ['e5', 'e6'],
        'result': 'd2',
        'structure': '(合成 豆腐 鸡蛋)',
        'lexical_binding': {'豆腐': 'e5', '鸡蛋': 'e6'}
    },
    '洋葱蛋饼': {
        'ingredients': ['e2', 'e6'],
        'result': 'd3',
        'structure': '(合成 洋葱 鸡蛋)',
        'lexical_binding': {'洋葱': 'e2', '鸡蛋': 'e6'}
    },
    # 高级合成（B/C/D 功能等价，与 CFG 一致）
    '番茄鸡丁': {
        'ingredients': ['B', 'C'],
        'result': 'a1',
        'structure': '(合成 蔬菜类 荤豆类)'
    },
    '洋葱鸡丁': {
        'ingredients': ['B', 'C'],
        'result': 'a4',
        'structure': '(合成 蔬菜类 荤豆类)'
    },
    '鸡肉煎蛋': {
        'ingredients': ['C', 'D'],
        'result': 'a2',
        'structure': '(合成 荤豆类 蛋类)'
    },
    '番茄煎蛋': {
        'ingredients': ['B', 'D'],
        'result': 'a3',
        'structure': '(合成 蔬菜类 蛋类)'
    }
}


def get_lexicalized_pcfg_recipes() -> Dict:
    """获取Lexicalized PCFG条件的配方"""
    return RECIPES_LEXICALIZED_PCFG


def can_merge_lexicalized_pcfg(item1: str, item2: str, 
                                discovered_recipes: Optional[Set[str]] = None) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Lexicalized PCFG条件下的合成检查（支持功能等价）
    
    Args:
        item1, item2: 要合成的物品
        discovered_recipes: 已发现的配方名称集合（用于检查依赖）
    
    Returns:
        (是否可以合成, 合成结果, 结构表达式)
    """
    # 首先尝试使用overcooked的can_merge（支持功能等价）
    try:
        from ..overcooked.recipes import can_merge
        can_merge_result, result = can_merge(item1, item2)
        if can_merge_result and result:
            # 获取结构表达式
            structure_expr = get_structure_expression(
                RuleComplexity.LEXICALIZED_PCFG, item1, item2, result
            )
            return True, result, structure_expr
    except ImportError:
        pass
    
    # 如果导入失败，使用原始逻辑（仅作为后备）
    if discovered_recipes is None:
        discovered_recipes = set()
    
    items_sorted = sorted([item1, item2])
    
    for key, recipe in RECIPES_LEXICALIZED_PCFG.items():
        if 'ingredients' in recipe:
            # 检查基础配方
            if sorted(recipe['ingredients']) == items_sorted:
                # 检查是否有依赖要求
                if 'requires' in recipe:
                    if not all(req in discovered_recipes for req in recipe['requires']):
                        continue
                return True, recipe['result'], recipe.get('structure', '')
    
    return False, None, None


# ==================== 统一接口 ====================

def get_recipes_by_complexity(complexity: RuleComplexity) -> Dict:
    """根据复杂度水平获取配方"""
    if complexity == RuleComplexity.NO_OPERATOR:
        return get_no_operator_recipes()
    elif complexity == RuleComplexity.CFG:
        return get_cfg_recipes()
    elif complexity == RuleComplexity.LEXICALIZED_PCFG:
        return get_lexicalized_pcfg_recipes()
    else:
        return {}


def can_merge_by_complexity(item1: str, item2: str, 
                            complexity: RuleComplexity,
                             discovered_recipes: Optional[Set[str]] = None) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    根据复杂度水平检查是否可以合成
    
    Returns:
        (是否可以合成, 合成结果, 结构表达式)
    """
    if complexity == RuleComplexity.NO_OPERATOR:
        # 无算子条件：不能合成
        return False, None, None
    elif complexity == RuleComplexity.CFG:
        return can_merge_cfg(item1, item2)
    elif complexity == RuleComplexity.LEXICALIZED_PCFG:
        return can_merge_lexicalized_pcfg(item1, item2, discovered_recipes)
    else:
        return False, None, None


def get_structure_expression(complexity: RuleComplexity, 
                            item1: str, item2: str,
                            result: str) -> str:
    """获取结构表达式（前缀表达式）"""
    if complexity == RuleComplexity.NO_OPERATOR:
        return f"(收集 {item1} {item2})"
    elif complexity == RuleComplexity.CFG:
        recipes = get_cfg_recipes()
        for key, recipe in recipes.items():
            if 'ingredients' in recipe and recipe.get('result') == result:
                return recipe.get('structure', f'(合成 {item1} {item2})')
        return f'(合成 {item1} {item2})'
    elif complexity == RuleComplexity.LEXICALIZED_PCFG:
        recipes = get_lexicalized_pcfg_recipes()
        for key, recipe in recipes.items():
            if 'ingredients' in recipe and recipe.get('result') == result:
                return recipe.get('structure', f'(合成 {item1} {item2})')
        return f'(合成 {item1} {item2})'
    else:
        return f'(合成 {item1} {item2})'

