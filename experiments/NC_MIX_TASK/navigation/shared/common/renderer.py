"""
通用渲染系统
提供两个任务共用的UI组件和渲染函数
"""
import pygame
from ..config import BaseConfig


class Renderer:
    """渲染器类"""
    
    def __init__(self, screen):
        """
        初始化渲染器
        
        Args:
            screen: pygame.Surface对象
        """
        self.screen = screen
        self.fonts = {
            'sm': BaseConfig.get_font(16),
            'md': BaseConfig.get_font(20),
            'lg': BaseConfig.get_font(28),
            'xl': BaseConfig.get_font(40),
        }
    
    def draw_panel(self, rect: pygame.Rect, title: str):
        """
        绘制面板
        
        Args:
            rect: 面板矩形
            title: 面板标题
        """
        pygame.draw.rect(self.screen, BaseConfig.COLOR_PANEL, rect, border_radius=15)
        pygame.draw.rect(self.screen, BaseConfig.COLOR_BORDER, rect, 2, border_radius=15)
        title_surf = self.fonts['lg'].render(title, True, BaseConfig.COLOR_TEXT_MAIN)
        self.screen.blit(title_surf, (rect.x + 20, rect.y + 15))
    
    def draw_text(self, text: str, pos: tuple, size: str = 'md', 
                  color: tuple = None, center: bool = False):
        """
        绘制文本
        
        Args:
            text: 文本内容
            pos: 位置 (x, y)
            size: 字体大小 ('sm', 'md', 'lg', 'xl')
            color: 颜色，默认使用COLOR_TEXT_MAIN
            center: 是否居中显示
        """
        if color is None:
            color = BaseConfig.COLOR_TEXT_MAIN
        
        font = self.fonts.get(size, self.fonts['md'])
        text_surf = font.render(text, True, color)
        
        if center:
            pos = (pos[0] - text_surf.get_width() // 2, 
                   pos[1] - text_surf.get_height() // 2)
        
        self.screen.blit(text_surf, pos)
        return text_surf
    
    def wrap_text(self, text: str, font: pygame.font.Font, max_width: int) -> list:
        """
        将文本按最大宽度换行
        
        Args:
            text: 原始文本
            font: pygame字体对象
            max_width: 最大宽度（像素）
            
        Returns:
            换行后的文本行列表
        """
        words = text.split(' ')
        lines = []
        current_line = []
        
        for word in words:
            # 测试添加单词后当前行的宽度
            test_line = ' '.join(current_line + [word])
            width, _ = font.size(test_line)
            
            if width <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                # 如果单个单词就超过最大宽度，强制分割单词
                if font.size(word)[0] > max_width:
                    # 字符级分割
                    chars = list(word)
                    current_chars = []
                    for char in chars:
                        test_chars = ''.join(current_chars + [char])
                        if font.size(test_chars)[0] <= max_width:
                            current_chars.append(char)
                        else:
                            if current_chars:
                                lines.append(''.join(current_chars))
                            current_chars = [char]
                    if current_chars:
                        current_line = [''.join(current_chars)]
                else:
                    current_line = [word]
        
        if current_line:
            lines.append(' '.join(current_line))
        
        return lines
    
    def draw_room_cell(self, x: int, y: int, center_offset_x: int, center_offset_y: int,
                       bg_color: tuple = None, border_color: tuple = None):
        """
        绘制房间格子
        
        Args:
            x, y: 网格坐标
            center_offset_x, center_offset_y: 中心偏移量
            bg_color: 背景颜色
            border_color: 边框颜色
        """
        if bg_color is None:
            bg_color = BaseConfig.COLOR_ROOM_BG
        if border_color is None:
            border_color = (60, 60, 70)
        
        screen_x = center_offset_x + x * BaseConfig.GRID_SIZE
        screen_y = center_offset_y + y * BaseConfig.GRID_SIZE
        cell_rect = pygame.Rect(
            screen_x, screen_y,
            BaseConfig.GRID_SIZE, BaseConfig.GRID_SIZE
        )
        
        pygame.draw.rect(self.screen, bg_color, cell_rect)
        pygame.draw.rect(self.screen, border_color, cell_rect, 1)
        
        return cell_rect
    
    def draw_wall(self, start_pos: tuple, end_pos: tuple, thickness: int = 4):
        """
        绘制墙壁
        
        Args:
            start_pos: 起始位置 (x, y)
            end_pos: 结束位置 (x, y)
            thickness: 墙壁厚度
        """
        pygame.draw.line(
            self.screen, BaseConfig.COLOR_ROOM_WALL,
            start_pos, end_pos, thickness
        )

    def draw_dashed_line(self, color: tuple, start_pos: tuple, end_pos: tuple,
                         thickness: int = 2, dash_length: int = 6, gap_length: int = 4):
        """
        绘制虚线（供 Navigation3 等复用）。
        Args:
            color: 颜色 (r, g, b)
            start_pos: 起点 (x, y)
            end_pos: 终点 (x, y)
            thickness: 线宽
            dash_length: 每段实线长度（像素）
            gap_length: 每段间隔长度（像素）
        """
        x1, y1 = start_pos
        x2, y2 = end_pos
        dx = x2 - x1
        dy = y2 - y1
        length = (dx * dx + dy * dy) ** 0.5
        if length < 1e-6:
            return
        ux = dx / length
        uy = dy / length
        step = dash_length + gap_length
        pos = 0.0
        while pos < length:
            seg_end = min(pos + dash_length, length)
            sx1 = x1 + ux * pos
            sy1 = y1 + uy * pos
            sx2 = x1 + ux * seg_end
            sy2 = y1 + uy * seg_end
            pygame.draw.line(self.screen, color, (sx1, sy1), (sx2, sy2), thickness)
            pos += step

    def draw_player(self, grid_x: int, grid_y: int, center_offset_x: int, center_offset_y: int,
                    direction: str = 'south', asset_manager=None):
        """
        绘制玩家
        
        Args:
            grid_x, grid_y: 玩家网格坐标
            center_offset_x, center_offset_y: 中心偏移量
            direction: 玩家方向 ('north', 'south', 'west', 'east')，默认'south'
            asset_manager: 资源管理器（可选，用于贴图绘制）
        """
        screen_x = center_offset_x + grid_x * BaseConfig.GRID_SIZE
        screen_y = center_offset_y + grid_y * BaseConfig.GRID_SIZE
        
        # 玩家尺寸（统一使用40像素，与Overcooked任务一致）
        PLAYER_SIZE = 40
        # 计算玩家居中位置
        player_x = screen_x + (BaseConfig.GRID_SIZE - PLAYER_SIZE) // 2
        player_y = screen_y + (BaseConfig.GRID_SIZE - PLAYER_SIZE) // 2
        
        # 方向到图片键名的映射
        DIRECTION_TO_IMAGE = {
            'north': 'player_up',
            'south': 'player_down',
            'west': 'player_left',
            'east': 'player_right'
        }
        
        # 尝试使用贴图绘制玩家
        if asset_manager:
            image_key = DIRECTION_TO_IMAGE.get(direction, 'player_down')
            player_img = asset_manager.get_image(image_key, PLAYER_SIZE, PLAYER_SIZE)
            if player_img:
                # 绘制阴影
                shadow_offset = 3
                shadow_surf = pygame.Surface((PLAYER_SIZE, PLAYER_SIZE), pygame.SRCALPHA)
                shadow_surf.fill((0, 0, 0, 100))
                self.screen.blit(shadow_surf, (player_x + shadow_offset, player_y + shadow_offset))
                # 绘制玩家贴图
                self.screen.blit(player_img, (player_x, player_y))
                return
        
        # 兜底：使用颜色矩形绘制
        player_rect = pygame.Rect(
            player_x, player_y,
            PLAYER_SIZE, PLAYER_SIZE
        )
        pygame.draw.rect(
            self.screen, BaseConfig.COLOR_PLAYER,
            player_rect, border_radius=5
        )
    
    def draw_fragment(self, room_x: int, room_y: int, center_offset_x: int, center_offset_y: int,
                      fragment: str, asset_manager=None):
        """
        绘制物品碎片
        
        Args:
            room_x, room_y: 房间逻辑坐标
            center_offset_x, center_offset_y: 中心偏移量
            fragment: 物品名称
            asset_manager: 资源管理器（可选）
        """
        # 计算房间中心位置（房间内第2个格子，索引1）
        # 房间左上角位置
        room_screen_x = center_offset_x + (room_x * 3) * BaseConfig.GRID_SIZE
        room_screen_y = center_offset_y + (room_y * 3) * BaseConfig.GRID_SIZE
        
        # 中间格子的中心位置（索引1，即第2个格子）
        # 1个格子到中间格子的左上角，再加0.5个格子到中心
        cx = int(room_screen_x + BaseConfig.GRID_SIZE * 1.5)
        cy = int(room_screen_y + BaseConfig.GRID_SIZE * 1.5)
        
        # 定义图片尺寸（格子尺寸的75%，留出更多边距）
        img_size = int(BaseConfig.GRID_SIZE * 0.75)  # 30像素
        radius = img_size // 2
        
        # 尝试使用图片
        if asset_manager:
            img = asset_manager.get_image(fragment, img_size, img_size)
            if img:
                self.screen.blit(img, (cx - img_size // 2, cy - img_size // 2))
                return
        
        # 兜底：使用颜色圆圈
        color = BaseConfig.FRAGMENT_COLORS.get(fragment, (200, 200, 200))
        pygame.draw.circle(self.screen, color, (cx, cy), radius)
        
        # 绘制文字标签
        text_surf = self.fonts['sm'].render(fragment, True, (0, 0, 0))
        self.screen.blit(
            text_surf,
            (cx - text_surf.get_width() // 2, cy - text_surf.get_height() // 2)
        )
    
    def draw_room_id(self, room_x: int, room_y: int, center_offset_x: int, center_offset_y: int,
                     room_id: int):
        """
        绘制房间ID编号
        
        Args:
            room_x, room_y: 房间逻辑坐标
            center_offset_x, center_offset_y: 中心偏移量
            room_id: 房间顺序ID
        """
        room_screen_x = center_offset_x + room_x * 3 * BaseConfig.GRID_SIZE
        room_screen_y = center_offset_y + room_y * 3 * BaseConfig.GRID_SIZE
        
        id_surf = self.fonts['sm'].render(str(room_id), True, (100, 110, 130))
        self.screen.blit(id_surf, (room_screen_x + 5, room_screen_y + 5))
    
    def calculate_map_offsets(self, rooms: dict, map_area: pygame.Rect,
                              pixels_per_cell: int = None):
        """
        计算地图在屏幕上的偏移量，使地图居中显示。

        Args:
            rooms: 房间字典
            map_area: 地图显示区域
            pixels_per_cell: 每格像素数，默认 BaseConfig.GRID_SIZE（Navigation3 可传入 GRID_STEP）

        Returns:
            (center_offset_x, center_offset_y)
        """
        if pixels_per_cell is None:
            pixels_per_cell = BaseConfig.GRID_SIZE
        if not rooms:
            return 0, 0

        all_lx = [r.logical_pos[0] for r in rooms.values()]
        all_ly = [r.logical_pos[1] for r in rooms.values()]

        if not all_lx or not all_ly:
            return 0, 0

        min_lx, max_lx = min(all_lx), max(all_lx)
        min_ly, max_ly = min(all_ly), max(all_ly)

        grid_w_cells = (max_lx - min_lx + 1) * 3
        grid_h_cells = (max_ly - min_ly + 1) * 3
        grid_px_w = grid_w_cells * pixels_per_cell
        grid_px_h = grid_h_cells * pixels_per_cell

        center_off_x = (map_area.centerx - grid_px_w // 2 -
                        (min_lx * 3) * pixels_per_cell)
        center_off_y = (map_area.centery - grid_px_h // 2 -
                        (min_ly * 3) * pixels_per_cell)

        return center_off_x, center_off_y
    
    def draw_game_over_overlay(self, message: str):
        """
        绘制游戏结束遮罩
        
        Args:
            message: 结束消息
        """
        overlay = pygame.Surface(
            (BaseConfig.SCREEN_WIDTH, BaseConfig.SCREEN_HEIGHT),
            pygame.SRCALPHA
        )
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        
        text_surf = self.fonts['xl'].render(message, True, BaseConfig.COLOR_SUCCESS)
        text_rect = text_surf.get_rect(
            center=(BaseConfig.SCREEN_WIDTH // 2, BaseConfig.SCREEN_HEIGHT // 2)
        )
        self.screen.blit(text_surf, text_rect)
    
    def draw_obstacle_cell(self, grid_x: int, grid_y: int, center_offset_x: int, center_offset_y: int,
                          asset_manager=None):
        """
        绘制障碍物格子
        
        Args:
            grid_x, grid_y: 网格坐标
            center_offset_x, center_offset_y: 中心偏移量
            asset_manager: 资源管理器（可选，用于贴图绘制）
        """
        screen_x = center_offset_x + grid_x * BaseConfig.GRID_SIZE
        screen_y = center_offset_y + grid_y * BaseConfig.GRID_SIZE
        
        # 尝试使用贴图绘制障碍物
        if asset_manager:
            wall_img = asset_manager.get_image('wall_brick', BaseConfig.GRID_SIZE, BaseConfig.GRID_SIZE)
            if wall_img:
                self.screen.blit(wall_img, (screen_x, screen_y))
                return
        
        # 兜底：使用颜色矩形绘制
        obstacle_rect = pygame.Rect(
            screen_x, screen_y,
            BaseConfig.GRID_SIZE, BaseConfig.GRID_SIZE
        )
        pygame.draw.rect(
            self.screen, BaseConfig.FRAGMENT_COLORS.get('obstacle', (100, 50, 50)),
            obstacle_rect
        )

