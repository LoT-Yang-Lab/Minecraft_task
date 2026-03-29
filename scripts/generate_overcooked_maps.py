#!/usr/bin/env python3
"""
生成 Overcooked 任务地图图片，用于项目书/学术汇报
生成 4 种不同地图类型的截图（Barbell, Grid, Path, Ladder）
支持 300 DPI 输出，白底背景
"""
import sys
import os
import pygame
from PIL import Image

# 添加项目根目录到路径
current_file = os.path.abspath(__file__)
project_root = os.path.dirname(os.path.dirname(current_file))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入项目模块
from experiments.overcooked.src.main_overcooked import draw_ui_overcooked
from experiments.overcooked.src.game_overcooked_simple import GameOvercooked
from shared.common.recorder import RLDataRecorder
from shared.common.renderer import Renderer
from shared.common.asset_manager import AssetManager
from shared.config import BaseConfig, OvercookedConfig


def generate_map_image(map_type: str, output_path: str):
    """
    生成指定类型的地图图片

    Args:
        map_type: 地图类型 ("Barbell", "Grid", "Path", "Ladder")
        output_path: 输出图片路径
    """
    print(f"生成地图: {map_type}")

    try:
        pygame.init()
        pygame.display.set_mode((1, 1), pygame.NOFRAME)

        # 设置纯白背景色
        BaseConfig.COLOR_BG = (255, 255, 255)
        OvercookedConfig.COLOR_BG = (255, 255, 255)

        # 创建屏幕表面（不显示窗口）
        screen = pygame.Surface((BaseConfig.SCREEN_WIDTH, BaseConfig.SCREEN_HEIGHT))
        screen.fill((255, 255, 255))

        # 创建数据记录器和资源管理器
        recorder = RLDataRecorder("Overcooked_Export", task_type="Overcooked")
        asset_manager = AssetManager()
        renderer = Renderer(screen)

        # 创建游戏实例（指定地图类型）
        game = GameOvercooked(
            recorder=recorder,
            map_type=map_type,
            enable_experiment=True,
            map_structure="multi_room",
            rule_complexity="cfg",
            asset_manager=asset_manager
        )

        # 绘制完整 UI
        draw_ui_overcooked(game, renderer, asset_manager, screen)

        # 地图区域（与 main_overcooked 中 map_area 一致）
        map_area = pygame.Rect(
            320, 20,
            BaseConfig.SCREEN_WIDTH - 660,
            BaseConfig.SCREEN_HEIGHT - 40
        )
        # 只裁剪并保存地图区域，去掉左右大块留白
        crop = screen.subsurface(map_area)
        crop_w, crop_h = crop.get_width(), crop.get_height()
        data = pygame.image.tostring(crop, 'RGB')
        img = Image.frombytes('RGB', (crop_w, crop_h), data)
        img.save(output_path, 'PNG', dpi=(300, 300))
        print(f"  已保存: {output_path} (300 DPI, {crop_w}x{crop_h})")

    except Exception as e:
        print(f"  生成失败: {e}")
        import traceback
        traceback.print_exc()


def main():
    """主函数：生成 4 种地图的图片"""
    print("=" * 60)
    print("生成 Overcooked 任务地图图片")
    print("=" * 60)

    output_dir = os.path.join(project_root, "experiments", "overcooked", "map_images")
    os.makedirs(output_dir, exist_ok=True)

    map_types = ["Barbell", "Grid", "Path", "Ladder"]

    for map_type in map_types:
        output_path = os.path.join(output_dir, f"{map_type.lower()}.png")
        generate_map_image(map_type, output_path)

    print("\n" + "=" * 60)
    print(f"所有图片已生成到 {output_dir}")
    print(f"共 {len(map_types)} 张: barbell.png, grid.png, path.png, ladder.png")
    print("=" * 60)


if __name__ == "__main__":
    main()
