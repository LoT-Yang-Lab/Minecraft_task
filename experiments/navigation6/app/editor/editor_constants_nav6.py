"""
Navigation6 地图编辑器常量：公交(蓝) / 地铁(黄) / 轻轨(绿) 路径与站点；单格与障碍。
"""
from enum import Enum
from typing import Dict, Tuple, Any
import pygame
from shared.config import BaseConfig


class ToolType(Enum):
    WALL = "wall"
    SINGLE_CELL = "single_cell"
    BUS_PATH = "bus_path"
    BUS_STATION = "bus_station"
    METRO_PATH = "metro_path"
    METRO_STATION = "metro_station"
    LIGHT_RAIL_PATH = "light_rail_path"
    LIGHT_RAIL_STATION = "light_rail_station"
    TRANSIT_CURVE = "transit_curve"
    START_POINT = "start_point"
    TARGET_POINT = "target_point"
    SELECT = "select"


# 工具 → 当前编辑的交通类别（路径/站点共用同一类别）
TRANSIT_KIND_BY_TOOL: Dict[ToolType, str] = {
    ToolType.BUS_PATH: "bus",
    ToolType.BUS_STATION: "bus",
    ToolType.METRO_PATH: "metro",
    ToolType.METRO_STATION: "metro",
    ToolType.LIGHT_RAIL_PATH: "light_rail",
    ToolType.LIGHT_RAIL_STATION: "light_rail",
}


class EditorColors:
    PANEL_LEFT_BG = (45, 50, 55)
    PANEL_RIGHT_BG = BaseConfig.COLOR_PANEL
    TITLE_BAR_BG = (60, 65, 70)
    TITLE_BAR_TEXT = (240, 245, 250)
    TOOL_NORMAL = (65, 70, 75)
    TOOL_HOVER = (85, 90, 95)
    TOOL_ACTIVE = (100, 150, 255)
    TOOL_TEXT = (240, 245, 250)
    TOOL_SHORTCUT = (180, 190, 200)
    BUTTON_SHADOW = (30, 35, 40)
    BUTTON_BORDER = (90, 100, 110)
    BUTTON_BORDER_ACTIVE = (120, 170, 255)
    SELECTION_HIGHLIGHT = (100, 150, 255, 80)
    SELECTION_BORDER = (100, 150, 255)
    GRID_LINE = (200, 210, 220)
    VALIDATION_PASS = (100, 200, 100)
    VALIDATION_WARN = (255, 180, 50)
    VALIDATION_ERROR = (255, 100, 100)
    COLOR_BUS_LINE = (60, 120, 220)
    COLOR_METRO_LINE = (240, 210, 60)
    COLOR_LIGHT_RAIL_LINE = (70, 190, 110)
    COLOR_SUBWAY_STATION = (200, 220, 255)
    COLOR_PORTAL = (180, 120, 220)
    COLOR_START = (100, 255, 100)
    COLOR_TARGET = (255, 100, 100)
    COLOR_OBSTACLE = (150, 100, 100)
    COLOR_SINGLE_CELL = (180, 230, 230)
    COLOR_WALL = BaseConfig.COLOR_ROOM_WALL
    STATUS_INFO = BaseConfig.COLOR_TEXT_MAIN
    STATUS_SUCCESS = BaseConfig.COLOR_SUCCESS
    STATUS_WARNING = BaseConfig.COLOR_HIGHLIGHT
    STATUS_ERROR = (255, 100, 100)
    DIVIDER_LINE = (200, 210, 220)
    SECTION_BORDER = (210, 220, 230)


class EditorLayout:
    SCREEN_WIDTH = BaseConfig.SCREEN_WIDTH
    SCREEN_HEIGHT = BaseConfig.SCREEN_HEIGHT
    MARGIN_OUTER = 10
    MARGIN_INNER = 8
    MARGIN_ELEMENT = 4
    FONT_SMALL = 12
    FONT_MEDIUM = 14
    FONT_LARGE = 18
    FONT_XLARGE = 22
    PANEL_LEFT_WIDTH = 280
    PANEL_RIGHT_WIDTH = 280
    STATUS_BAR_HEIGHT = 24
    TITLE_BAR_HEIGHT = 32
    CANVAS_WIDTH = SCREEN_WIDTH - PANEL_LEFT_WIDTH - PANEL_RIGHT_WIDTH - (MARGIN_OUTER * 4)
    STATUS_BAR_RECT = pygame.Rect(
        MARGIN_OUTER,
        SCREEN_HEIGHT - STATUS_BAR_HEIGHT - MARGIN_OUTER,
        SCREEN_WIDTH - (MARGIN_OUTER * 2),
        STATUS_BAR_HEIGHT
    )
    CONTENT_AREA_HEIGHT = SCREEN_HEIGHT - STATUS_BAR_HEIGHT - (MARGIN_OUTER * 3)
    CONTENT_AREA_Y = MARGIN_OUTER
    PANEL_LEFT_RECT = pygame.Rect(MARGIN_OUTER, CONTENT_AREA_Y, PANEL_LEFT_WIDTH, CONTENT_AREA_HEIGHT)
    CANVAS_RECT = pygame.Rect(PANEL_LEFT_RECT.right + MARGIN_OUTER, CONTENT_AREA_Y, CANVAS_WIDTH, CONTENT_AREA_HEIGHT)
    PANEL_RIGHT_RECT = pygame.Rect(CANVAS_RECT.right + MARGIN_OUTER, CONTENT_AREA_Y, PANEL_RIGHT_WIDTH, CONTENT_AREA_HEIGHT)
    TOOL_BUTTON_SIZE = 40
    TOOL_BUTTON_MARGIN = 4
    GRID_SIZE = 30
    ROOM_SIZE = 90


TOOL_CONFIGS: Dict[ToolType, Dict[str, Any]] = {
    ToolType.WALL: {"name": "墙/障碍物", "shortcut": "W", "description": "设置/移除障碍物"},
    ToolType.SINGLE_CELL: {"name": "单个可行走格", "shortcut": "G", "description": "添加/删除单格可行走区域"},
    ToolType.BUS_PATH: {"name": "公交路径(蓝)", "shortcut": "4", "description": "公交线路路径"},
    ToolType.BUS_STATION: {"name": "公交站点", "shortcut": "5", "description": "公交站点"},
    ToolType.METRO_PATH: {"name": "地铁路径(黄)", "shortcut": "6", "description": "地铁线路路径"},
    ToolType.METRO_STATION: {"name": "地铁站点", "shortcut": "7", "description": "地铁站点"},
    ToolType.LIGHT_RAIL_PATH: {"name": "轻轨路径(绿)", "shortcut": "8", "description": "轻轨线路路径"},
    ToolType.LIGHT_RAIL_STATION: {"name": "轻轨站点", "shortcut": "9", "description": "轻轨站点"},
    ToolType.TRANSIT_CURVE: {
        "name": "线路弧度",
        "shortcut": "C",
        "description": "滚轮调弯；L直线；TAB切邻近段",
    },
    ToolType.START_POINT: {"name": "起始点", "shortcut": "1", "description": "设置起始位置"},
    ToolType.TARGET_POINT: {"name": "目标点", "shortcut": "2", "description": "设置目标位置"},
    ToolType.SELECT: {"name": "选择", "shortcut": "Esc", "description": "选择工具（查看属性）"},
}

KEY_SHORTCUTS: Dict[int, ToolType] = {
    pygame.K_w: ToolType.WALL,
    pygame.K_g: ToolType.SINGLE_CELL,
    pygame.K_4: ToolType.BUS_PATH,
    pygame.K_5: ToolType.BUS_STATION,
    pygame.K_6: ToolType.METRO_PATH,
    pygame.K_7: ToolType.METRO_STATION,
    pygame.K_8: ToolType.LIGHT_RAIL_PATH,
    pygame.K_9: ToolType.LIGHT_RAIL_STATION,
    pygame.K_c: ToolType.TRANSIT_CURVE,
    pygame.K_1: ToolType.START_POINT,
    pygame.K_2: ToolType.TARGET_POINT,
    pygame.K_ESCAPE: ToolType.SELECT,
}
