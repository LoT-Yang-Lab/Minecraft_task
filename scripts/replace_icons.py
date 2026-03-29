#!/usr/bin/env python3
"""
将导航地图中的彩色方块替换为图标
- 玩家(红色方块) -> 向下.png
- 目标(红色方块) -> 金币.png  
- 障碍物(棕色方块) -> block-brick.png
"""
import os
from PIL import Image
import numpy as np

def replace_color_with_icon(image_path, output_path=None):
    """
    将图片中的特定颜色区域替换为图标
    
    Args:
        image_path: 输入图片路径
        output_path: 输出图片路径，如果为None则覆盖原文件
    """
    if output_path is None:
        output_path = image_path
    
    print(f"处理: {os.path.basename(image_path)}")
    
    # 加载原始图片
    img = Image.open(image_path)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    width, height = img.size
    pixels = np.array(img)
    
    # 定义目标颜色和对应的图标文件
    # 注意: 在RGB模式下，颜色顺序为(R, G, B)
    color_replacements = [
        {
            'name': '玩家',
            'color': (255, 80, 80),  # COLOR_PLAYER
            'icon': '向下.png',
            'size': (40, 40),  # 玩家图标大小
            'tolerance': 20    # 颜色容差
        },
        {
            'name': '目标', 
            'color': (255, 0, 0),  # FRAGMENT_COLORS['target']
            'icon': '金币.png',
            'size': (30, 30),  # 目标图标大小
            'tolerance': 20
        },
        {
            'name': '障碍物',
            'color': (100, 50, 50),  # FRAGMENT_COLORS['obstacle']
            'icon': 'block-brick.png',
            'size': (40, 40),  # 障碍物图标大小
            'tolerance': 20
        }
    ]
    
    # 资产路径
    asset_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'shared', 'assets')
    
    # 创建输出图片
    result = img.copy()
    
    for replacement in color_replacements:
        color = replacement['color']
        icon_file = replacement['icon']
        icon_size = replacement['size']
        tolerance = replacement['tolerance']
        name = replacement['name']
        
        icon_path = os.path.join(asset_dir, icon_file)
        if not os.path.exists(icon_path):
            print(f"  警告: 图标文件不存在 {icon_file}")
            continue
        
        # 加载图标
        try:
            icon = Image.open(icon_path)
            if icon.mode != 'RGBA':
                icon = icon.convert('RGBA')
            # 缩放到目标大小
            icon = icon.resize(icon_size, Image.Resampling.LANCZOS)
        except Exception as e:
            print(f"  错误: 无法加载图标 {icon_file}: {e}")
            continue
        
        # 查找颜色区域
        # 计算颜色差异
        r, g, b = color
        color_diff = np.sqrt(
            (pixels[:, :, 0].astype(float) - r) ** 2 +
            (pixels[:, :, 1].astype(float) - g) ** 2 +
            (pixels[:, :, 2].astype(float) - b) ** 2
        )
        
        # 找到颜色匹配的像素
        color_mask = color_diff <= tolerance
        
        if not np.any(color_mask):
            print(f"  未找到{name}颜色区域")
            continue
        
        # 找到颜色区域的边界框
        rows = np.any(color_mask, axis=1)
        cols = np.any(color_mask, axis=0)
        
        if not np.any(rows) or not np.any(cols):
            print(f"  {name}区域无效")
            continue
        
        ymin, ymax = np.where(rows)[0][[0, -1]]
        xmin, xmax = np.where(cols)[0][[0, -1]]
        
        # 计算中心位置
        center_x = (xmin + xmax) // 2
        center_y = (ymin + ymax) // 2
        
        # 计算图标放置位置（居中）
        icon_x = center_x - icon_size[0] // 2
        icon_y = center_y - icon_size[1] // 2
        
        print(f"  {name}: 区域({xmin},{ymin})-({xmax},{ymax}), 中心({center_x},{center_y})")
        
        # 将图标粘贴到结果图片上
        # 需要将图标合成到RGB图片上
        result_rgba = result.convert('RGBA')
        icon_mask = icon.split()[3]  # 使用alpha通道作为遮罩
        
        # 创建临时RGBA图片用于合成
        temp = Image.new('RGBA', result_rgba.size, (0, 0, 0, 0))
        temp.paste(icon, (icon_x, icon_y), icon_mask)
        
        # 合成图标和原图
        result_rgba = Image.alpha_composite(result_rgba, temp)
        result = result_rgba.convert('RGB')
        
        # 更新像素数组以反映更改
        pixels = np.array(result)
    
    # 保存结果
    result.save(output_path, dpi=(300, 300))
    print(f"  已保存: {os.path.basename(output_path)}")
    return True

def process_all_maps():
    """处理所有导航地图图片"""
    input_dir = "experiments/navigation/map_images"
    output_dir = "experiments/navigation/map_images_with_icons"
    
    if not os.path.exists(input_dir):
        print(f"错误: 输入目录不存在 {input_dir}")
        return
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 获取所有图片文件
    map_types = ["grid", "barbell", "path", "ladder"]
    difficulties = ["low", "medium_low", "medium_high", "high"]
    
    processed_count = 0
    for map_type in map_types:
        for difficulty in difficulties:
            filename = f"{map_type}_entropy_{difficulty}.png"
            input_path = os.path.join(input_dir, filename)
            output_path = os.path.join(output_dir, filename)
            
            if os.path.exists(input_path):
                print(f"\n处理 {filename}...")
                try:
                    replace_color_with_icon(input_path, output_path)
                    processed_count += 1
                except Exception as e:
                    print(f"  处理失败: {e}")
    
    print(f"\n处理完成: {processed_count} 张图片")
    
    # 如果需要，也可以覆盖原始文件
    print("\n选项: [1] 保留原始文件 [2] 用图标版本替换原始文件")
    choice = input("请选择 (1/2): ").strip()
    
    if choice == "2":
        print("正在替换原始文件...")
        for map_type in map_types:
            for difficulty in difficulties:
                filename = f"{map_type}_entropy_{difficulty}.png"
                src = os.path.join(output_dir, filename)
                dst = os.path.join(input_dir, filename)
                
                if os.path.exists(src):
                    os.replace(src, dst)
                    print(f"  已替换: {filename}")
        
        print("原始文件已替换为图标版本")

if __name__ == "__main__":
    process_all_maps()