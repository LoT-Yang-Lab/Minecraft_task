#!/usr/bin/env python3
"""
将16张导航任务地图图片排列成4×4网格，生成一张大图用于学术汇报
"""
import os
from PIL import Image

def create_map_grid():
    """创建4×4地图网格图片"""
    print("=" * 60)
    print("创建4×4地图网格图片")
    print("=" * 60)
    
    # 图片目录
    input_dir = "experiments/navigation/map_images"
    output_file = "experiments/navigation/map_grid.png"
    
    # 检查目录是否存在
    if not os.path.exists(input_dir):
        print(f"错误: 目录 '{input_dir}' 不存在")
        print("请先运行 generate_navigation_maps.py 生成地图图片")
        return
    
    # 定义顺序：地图类型 × 障碍物难度
    map_types = ["grid", "barbell", "path", "ladder"]
    difficulty_levels = ["low", "medium_low", "medium_high", "high"]
    
    # 检查所有需要的图片是否存在
    all_images_exist = True
    image_files = []
    
    for map_type in map_types:
        for difficulty in difficulty_levels:
            filename = f"{map_type}_entropy_{difficulty}.png"
            filepath = os.path.join(input_dir, filename)
            
            if not os.path.exists(filepath):
                print(f"警告: 缺少图片 {filename}")
                all_images_exist = False
            else:
                image_files.append((map_type, difficulty, filepath))
    
    if not all_images_exist:
        print("\n部分图片缺失，无法创建完整的4×4网格")
        print("请确保已生成所有16张图片")
        return
    
    print(f"\n找到 {len(image_files)} 张图片")
    
    # 计算网格参数
    grid_cols = 4  # 每行4张图片
    grid_rows = 4  # 共4行
    
    # 单张图片的目标尺寸（原图1600×900，适当缩小）
    target_width = 400  # 缩小到400×225保持宽高比
    target_height = 225
    
    # 计算大图的尺寸
    padding = 20  # 图片间的间距
    label_height = 30  # 标签区域高度
    
    total_width = (target_width + padding) * grid_cols + padding
    total_height = (target_height + padding + label_height) * grid_rows + padding
    
    # 创建空白大图（白色背景）
    print(f"创建空白画布: {total_width} × {total_height} 像素")
    grid_image = Image.new('RGB', (total_width, total_height), color=(255, 255, 255))
    
    # 按顺序排列图片
    from PIL import ImageDraw, ImageFont
    
    # 尝试加载字体，失败则使用默认字体
    try:
        font = ImageFont.truetype("arial.ttf", 14)
        font_small = ImageFont.truetype("arial.ttf", 12)
    except:
        font = ImageFont.load_default()
        font_small = ImageFont.load_default()
    
    draw = ImageDraw.Draw(grid_image)
    
    print("\n开始排列图片...")
    
    for i, (map_type, difficulty, filepath) in enumerate(image_files):
        # 计算网格位置
        row = i // grid_cols
        col = i % grid_cols
        
        # 计算图片在网格中的位置
        x = padding + col * (target_width + padding)
        y = padding + row * (target_height + padding + label_height)
        
        print(f"  [{row+1},{col+1}] {os.path.basename(filepath)}")
        
        try:
            # 打开并调整图片大小
            img = Image.open(filepath)
            img_resized = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
            
            # 粘贴到网格中
            grid_image.paste(img_resized, (x, y))
            
            # 添加地图类型标签
            map_type_display = map_type.capitalize()
            difficulty_display = difficulty.replace('_', ' ').title()
            entropy_value = {
                "low": 0.2,
                "medium_low": 0.4,
                "medium_high": 0.6,
                "high": 0.8
            }[difficulty]
            
            # 绘制标签背景
            label_y = y + target_height + 5
            draw.rectangle([x, label_y, x + target_width, label_y + label_height], 
                          fill=(245, 245, 245))
            
            # 绘制标签文字
            type_text = f"{map_type_display}"
            entropy_text = f"Entropy: {entropy_value}"
            
            # 计算文字位置
            type_bbox = draw.textbbox((0, 0), type_text, font=font)
            type_width = type_bbox[2] - type_bbox[0]
            type_height = type_bbox[3] - type_bbox[1]
            
            entropy_bbox = draw.textbbox((0, 0), entropy_text, font=font_small)
            entropy_width = entropy_bbox[2] - entropy_bbox[0]
            
            # 绘制地图类型
            type_x = x + (target_width - type_width) // 2
            type_y = label_y + 5
            draw.text((type_x, type_y), type_text, fill=(0, 0, 0), font=font)
            
            # 绘制熵值
            entropy_x = x + (target_width - entropy_width) // 2
            entropy_y = label_y + 5 + type_height
            draw.text((entropy_x, entropy_y), entropy_text, fill=(100, 100, 100), font=font_small)
            
            # 绘制边框
            draw.rectangle([x, y, x + target_width, y + target_height], 
                          outline=(200, 200, 200), width=1)
            
        except Exception as e:
            print(f"    处理图片失败: {e}")
    
    # 添加标题
    title = "Navigation Task - Environment Configurations"
    try:
        title_font = ImageFont.truetype("arial.ttf", 24)
    except:
        title_font = ImageFont.load_default()
    
    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    title_width = title_bbox[2] - title_bbox[0]
    title_height = title_bbox[3] - title_bbox[1]
    
    title_x = (total_width - title_width) // 2
    title_y = 10
    
    draw.text((title_x, title_y), title, fill=(0, 0, 0), font=title_font)
    
    # 添加图例说明
    legend_y = total_height - 60
    draw.text((padding, legend_y), "Map Types: Grid (5×4), Barbell (two clusters + corridor),", 
              fill=(100, 100, 100), font=font_small)
    draw.text((padding, legend_y + 20), "Path (snake path), Ladder (two layers + vertical connection)", 
              fill=(100, 100, 100), font=font_small)
    
    # 保存图片
    grid_image.save(output_file, "PNG", quality=95)
    
    print("\n" + "=" * 60)
    print(f"4×4网格图片已生成: {output_file}")
    print(f"尺寸: {total_width} × {total_height} 像素")
    print(f"排列顺序:")
    print("  行: 地图类型 (Grid → Barbell → Path → Ladder)")
    print("  列: 障碍物难度 (Low → Medium Low → Medium High → High)")
    print("=" * 60)
    
    return output_file

if __name__ == "__main__":
    create_map_grid()