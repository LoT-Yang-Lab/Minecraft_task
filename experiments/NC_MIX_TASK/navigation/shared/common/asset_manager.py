"""
资源管理器
用于加载和管理游戏资源（图片等）
"""
import os
import pygame
from ..config import BaseConfig

# 尝试导入PIL作为后备方案
PIL_AVAILABLE = False
Image = None
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    pass


class AssetManager:
    """资源管理器"""
    
    def __init__(self, asset_path=None):
        """
        初始化资源管理器
        
        Args:
            asset_path: 资源路径，如果为None则使用BaseConfig中的路径
        """
        self.images = {}
        self.asset_path = asset_path or BaseConfig.ASSET_PATH
        
        # 按 {id}.png 加载的项（仅非规则树；规则树用 item_images_map 方式 B）
        self.item_list = [
            'obstacle',  # 障碍物
        ]
        
        # 额外图片映射（键名 -> 文件名）
        self.extra_images_map = {
            'wall_brick': 'block-brick.png',
            'player_up': '向上.png',
            'player_down': '向下.png',
            'player_left': '向左.png',
            'player_right': '向右.png',
            'cutting_board': '菜刀-切.jpg',
            'stove': '煎锅-煎.jpg',
            'copy_scale': 'copy_scale.png',  # 魔法天平（复制台）
            'trash': '垃圾桶.png',
            'serve_zone': '上菜台.png',
            'target': '金币.png',
            'train': 'train.png',  # 火车图片
        }
        
        # 方案 B：规则树全部用 id → 中文文件名 映射（与 shared/assets 中实际文件名一致）
        self.item_images_map = {
            'e1': '番茄.jpg', 'e2': '洋葱.png', 'e3': '胡萝卜.png',
            'e4': '鸡肉.png', 'e5': '豆腐.png', 'e6': '鸡蛋.png',
            'b1': '番茄块.png', 'b2': '洋葱丝.png', 'b3': '胡萝卜丁.png',
            'c1': '煎鸡肉.png', 'c2': '煎豆腐.png', 'c3': '煎蛋.png',
            'd1': '番茄洋葱酱.png', 'd2': '豆腐蛋饼.png', 'd3': '洋葱蛋饼.png',
            'a1': '番茄鸡丁.png', 'a2': '鸡肉煎蛋.png', 'a3': '番茄煎蛋.png', 'a4': '洋葱鸡丁.png',
            'A': '完整套餐.png',
        }
        self.load_assets()
    
    def _load_image_with_fallback(self, file_path, item_name):
        """
        尝试加载图片，使用pygame或PIL作为后备
        
        Args:
            file_path: 图片文件路径
            item_name: 物品名称（用于错误信息）
            
        Returns:
            加载成功的图片Surface，或None
        """
        # 首先尝试pygame加载
        try:
            img = pygame.image.load(file_path).convert_alpha()
            return img
        except Exception as e:
            print(f"  [警告] pygame加载 {item_name} 失败: {e}")
            
        # 如果pygame失败且PIL可用，尝试使用PIL加载
        if PIL_AVAILABLE and Image is not None:
            try:
                pil_img = Image.open(file_path)  # type: ignore
                # 转换为RGBA模式
                if pil_img.mode != 'RGBA':
                    pil_img = pil_img.convert('RGBA')
                
                # 将PIL图像转换为pygame Surface
                img_data = pil_img.tobytes()
                try:
                    img = pygame.image.fromstring(img_data, pil_img.size, 'RGBA')
                    print(f"  -> 使用PIL+fromstring成功加载: {os.path.basename(file_path)}")
                    return img
                except Exception as e2:
                    print(f"  [警告] pygame.image.fromstring失败: {e2}，尝试手动转换")
                    # 手动创建Surface并设置像素
                    surface = pygame.Surface(pil_img.size, pygame.SRCALPHA)
                    pixels = pil_img.load()
                    for x in range(pil_img.width):
                        for y in range(pil_img.height):
                            r, g, b, a = pixels[x, y]
                            surface.set_at((x, y), (r, g, b, a))
                    print(f"  -> 使用PIL+手动转换成功加载: {os.path.basename(file_path)}")
                    return surface
            except Exception as e:
                print(f"  [错误] PIL加载 {item_name} 也失败: {e}")
        else:
            print(f"  [警告] PIL不可用，无法使用后备方案加载 {item_name}")
        
        return None
    
    def load_assets(self):
        """加载所有资源"""
        if not os.path.exists(self.asset_path):
            print(f"[警告] 资源路径不存在: {self.asset_path}")
            return

        print(f"正在从 {self.asset_path} 加载资源...")
        loaded_count = 0
        # 按 item_list 加载（仅 obstacle 等非规则树）
        for item in self.item_list:
            file_path = os.path.join(self.asset_path, f"{item}.png")
            if os.path.exists(file_path):
                img = self._load_image_with_fallback(file_path, item)
                if img is not None:
                    self.images[item] = img
                    loaded_count += 1
                    print(f"  -> 已加载: {item}.png")
                else:
                    print(f"  [错误] 加载 {item}.png 失败")
        
        # 方案 B：按 id→中文文件名 加载规则树素材
        for elem_id, filename in self.item_images_map.items():
            file_path = os.path.join(self.asset_path, filename)
            if os.path.exists(file_path):
                img = self._load_image_with_fallback(file_path, f"物品:{elem_id}")
                if img is not None:
                    self.images[elem_id] = img
                    loaded_count += 1
                    print(f"  -> 已加载: {elem_id} ({filename})")
                else:
                    print(f"  [错误] 加载 {filename} 失败")
            else:
                print(f"  [警告] 文件不存在: {filename}")
        
        # 加载额外图片
        for key, filename in self.extra_images_map.items():
            file_path = os.path.join(self.asset_path, filename)
            if os.path.exists(file_path):
                img = self._load_image_with_fallback(file_path, f"额外:{key}")
                if img is not None:
                    self.images[key] = img
                    loaded_count += 1
                    print(f"  -> 已加载: {key} ({filename})")
                else:
                    print(f"  [错误] 加载 {filename} 失败")
            else:
                print(f"  [警告] 文件不存在: {filename}")
        
        total_items = len(self.item_list) + len(self.extra_images_map) + len(self.item_images_map)
        print(f"资源加载完成: {loaded_count}/{total_items} 个文件")

    def get_image(self, item_name, width, height):
        """
        获取并缩放图片
        
        Args:
            item_name: 物品名称
            width: 目标宽度
            height: 目标高度
            
        Returns:
            缩放后的图片Surface，如果不存在则返回None
        """
        if item_name in self.images:
            return pygame.transform.smoothscale(
                self.images[item_name], (width, height)
            )
        return None

    def has_image(self, item_name):
        """检查是否有该物品的图片"""
        return item_name in self.images

