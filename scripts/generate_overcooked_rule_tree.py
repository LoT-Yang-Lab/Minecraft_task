#!/usr/bin/env python3
"""
生成 Overcooked 规则树可视化图片
生成白底、300 DPI 的规则树图片
"""
import sys
import os

# 添加项目根目录到路径
current_file = os.path.abspath(__file__)
project_root = os.path.dirname(os.path.dirname(current_file))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 尝试导入 graphviz
try:
    import graphviz
    HAS_GRAPHVIZ = True
except ImportError:
    HAS_GRAPHVIZ = False
    print("警告: graphviz 不可用，将使用 matplotlib")

# 导入项目模块
from experiments.overcooked.src.recipes import RECIPES_AND, RECIPES_OR
from shared.alchemy.kitchen_elements import (
    BASE_INGREDIENTS, INTERMEDIATE_PRODUCTS, ABSTRACT_CATEGORIES,
    ADVANCED_PRODUCTS, FINAL_TARGET, FUNCTIONAL_EQUIVALENCE, get_display_name
)

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("警告: PIL 不可用，无法设置 DPI")


def build_rule_tree_graph():
    """构建规则树图结构"""
    # 定义节点和边
    nodes = {}
    edges = []
    
    # 添加所有节点
    for item_id in BASE_INGREDIENTS:
        nodes[item_id] = {'name': get_display_name(item_id), 'layer': 0, 'type': 'base'}
    for item_id in INTERMEDIATE_PRODUCTS:
        nodes[item_id] = {'name': get_display_name(item_id), 'layer': 1, 'type': 'intermediate'}
    for item_id in ABSTRACT_CATEGORIES:
        nodes[item_id] = {'name': get_display_name(item_id), 'layer': 2, 'type': 'abstract'}
    for item_id in ADVANCED_PRODUCTS:
        nodes[item_id] = {'name': get_display_name(item_id), 'layer': 3, 'type': 'advanced'}
    for item_id in FINAL_TARGET:
        nodes[item_id] = {'name': get_display_name(item_id), 'layer': 4, 'type': 'final'}
    
    # 添加切菜规则（e1→b1, e2→b2, e3→b3）
    cut_rules = {
        'e1': 'b1', 'e2': 'b2', 'e3': 'b3'
    }
    for src, dst in cut_rules.items():
        edges.append((src, dst, '切'))
    
    # 添加煮制规则（e4→c1, e5→c2, e6→c3）
    cook_rules = {
        'e4': 'c1', 'e5': 'c2', 'e6': 'c3'
    }
    for src, dst in cook_rules.items():
        edges.append((src, dst, '煮'))
    
    # 添加合成规则（AND规则）
    for result, ingredients in RECIPES_AND.items():
        if len(ingredients) == 2:
            # 两个输入合成一个输出
            edges.append((ingredients[0], result, '合成'))
            edges.append((ingredients[1], result, '合成'))
    
    # 添加OR等价规则（功能等价）
    for item_id, category in FUNCTIONAL_EQUIVALENCE.items():
        if item_id in nodes and category in nodes:
            edges.append((item_id, category, '等价'))
    
    return nodes, edges


def generate_with_graphviz(nodes, edges, output_path):
    """使用 graphviz 生成图片"""
    dot = graphviz.Digraph(comment='Overcooked Rule Tree', format='png')
    dot.attr(bgcolor='white')
    dot.attr(rankdir='TB')  # 从上到下
    dot.attr('node', shape='box', style='rounded,filled', fontname='SimHei')
    dot.attr('edge', fontname='SimHei')
    
    # 按层级分组
    layers = {0: [], 1: [], 2: [], 3: [], 4: []}
    for node_id, info in nodes.items():
        layers[info['layer']].append(node_id)
    
    # 添加节点，按层级设置颜色
    colors = {
        'base': '#E8F4F8',        # 浅蓝
        'intermediate': '#FFF4E6', # 浅黄
        'abstract': '#F0E8FF',    # 浅紫
        'advanced': '#E8F8E8',    # 浅绿
        'final': '#FFE8E8'        # 浅红
    }
    
    for node_id, info in nodes.items():
        label = f"{node_id}\n{info['name']}"
        dot.node(node_id, label, fillcolor=colors[info['type']])
    
    # 添加边
    for src, dst, label in edges:
        dot.edge(src, dst, label=label)
    
    # 设置层级（rank）
    for layer, node_ids in layers.items():
        if node_ids:
            with dot.subgraph() as s:
                s.attr(rank='same')
                for node_id in node_ids:
                    s.node(node_id)
    
    # 渲染图片
    dot.render(output_path.replace('.png', ''), cleanup=True)
    print(f"  已生成: {output_path}")
    
    # 如果 PIL 可用，设置 DPI
    if HAS_PIL:
        try:
            img = Image.open(output_path)
            img.save(output_path, 'PNG', dpi=(300, 300))
            print(f"  已设置 300 DPI")
        except Exception as e:
            print(f"  设置 DPI 失败: {e}")


def generate_with_matplotlib(nodes, edges, output_path):
    """使用 matplotlib 生成图片（备选方案）"""
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib import font_manager
    
    # 设置中文字体
    try:
        plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
        plt.rcParams['axes.unicode_minus'] = False
    except:
        pass
    
    fig, ax = plt.subplots(figsize=(20, 14), facecolor='white')
    ax.set_facecolor('white')
    ax.axis('off')
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    
    # 按层级组织节点
    layers = {0: [], 1: [], 2: [], 3: [], 4: []}
    for node_id, info in nodes.items():
        layers[info['layer']].append((node_id, info))
    
    # 计算节点位置（改进布局）
    node_positions = {}
    layer_y = {0: 0.88, 1: 0.68, 2: 0.48, 3: 0.28, 4: 0.08}
    layer_margins = {0: 0.05, 1: 0.05, 2: 0.05, 3: 0.05, 4: 0.05}
    
    for layer, node_list in layers.items():
        y = layer_y[layer]
        n = len(node_list)
        if n > 0:
            margin = layer_margins[layer]
            available_width = 1 - 2 * margin
            spacing = available_width / max(n, 1)
            start_x = margin
            for i, (node_id, info) in enumerate(node_list):
                x = start_x + i * spacing + spacing / 2
                node_positions[node_id] = (x, y)
    
    # 绘制边（改进：使用不同颜色和样式）
    edge_styles = {
        '切': ('#4A90E2', 'solid', 1.5),
        '煮': ('#E24A4A', 'solid', 1.5),
        '合成': ('#4AE24A', 'solid', 1.5),
        '等价': ('#E2E24A', 'dashed', 1.0)
    }
    
    for src, dst, label in edges:
        if src in node_positions and dst in node_positions:
            x1, y1 = node_positions[src]
            x2, y2 = node_positions[dst]
            color, style, width = edge_styles.get(label, ('gray', 'solid', 1.0))
            ax.plot([x1, x2], [y1, y2], color=color, linestyle=style, 
                   linewidth=width, alpha=0.6, zorder=0)
    
    # 绘制节点（改进：更大的节点和更好的文本）
    colors = {
        'base': '#E8F4F8',
        'intermediate': '#FFF4E6',
        'abstract': '#F0E8FF',
        'advanced': '#E8F8E8',
        'final': '#FFE8E8'
    }
    
    for node_id, info in nodes.items():
        if node_id in node_positions:
            x, y = node_positions[node_id]
            # 绘制节点框（更大）
            width, height = 0.08, 0.06
            rect = mpatches.FancyBboxPatch(
                (x - width/2, y - height/2), width, height,
                boxstyle="round,pad=0.01",
                facecolor=colors[info['type']],
                edgecolor='#333333',
                linewidth=2,
                zorder=2
            )
            ax.add_patch(rect)
            # 绘制文本
            label = f"{node_id}\n{info['name']}"
            ax.text(x, y, label, fontsize=10, ha='center', va='center',
                   weight='bold', color='#000000', zorder=3)
    
    # 添加层级标签
    layer_labels = {0: '基础食材', 1: '预处理层', 2: '抽象类别', 3: '终端菜品', 4: '最终目标'}
    for layer, label in layer_labels.items():
        if layers[layer]:
            y = layer_y[layer]
            ax.text(0.02, y, label, fontsize=12, ha='left', va='center',
                   weight='bold', color='#666666', style='italic')
    
    plt.tight_layout()
    
    # 保存图片
    dpi = 300 if HAS_PIL else 100
    plt.savefig(output_path, dpi=dpi, facecolor='white', bbox_inches='tight', pad_inches=0.2)
    plt.close()
    print(f"  已生成: {output_path} (DPI: {dpi})")


def main():
    """主函数"""
    print("=" * 60)
    print("生成 Overcooked 规则树可视化图片")
    print("=" * 60)
    
    # 构建规则树
    nodes, edges = build_rule_tree_graph()
    print(f"节点数: {len(nodes)}, 边数: {len(edges)}")
    
    # 创建输出目录
    output_dir = os.path.join(project_root, "experiments", "overcooked", "rule_tree_images")
    os.makedirs(output_dir, exist_ok=True)
    
    output_path = os.path.join(output_dir, "rule_tree.png")
    
    # 生成图片
    if HAS_GRAPHVIZ:
        print("使用 graphviz 生成...")
        generate_with_graphviz(nodes, edges, output_path)
    else:
        print("使用 matplotlib 生成...")
        try:
            generate_with_matplotlib(nodes, edges, output_path)
        except ImportError:
            print("错误: matplotlib 也不可用，请安装 graphviz 或 matplotlib")
            return
    
    print("\n" + "=" * 60)
    print(f"规则树图片已生成: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
