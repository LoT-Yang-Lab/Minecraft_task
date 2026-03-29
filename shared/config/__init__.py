"""
配置模块
包含基础配置和两个任务的特定配置
"""
import os
import pygame

class BaseConfig:
    """基础配置 - 两个任务共享"""
    # 屏幕设置
    SCREEN_WIDTH = 1600
    SCREEN_HEIGHT = 900
    
    # 网格设置
    GRID_SIZE = 40
    ROOM_GRID_WIDTH = 3
    ROOM_GRID_HEIGHT = 3
    
    # 资源路径
    ASSET_PATH = os.path.join(os.path.dirname(__file__), "..", "assets")
    
    # 颜色定义
    COLOR_BG = (240, 245, 250)
    COLOR_PANEL = (250, 252, 255)
    COLOR_BORDER = (220, 230, 240)
    COLOR_TEXT_MAIN = (60, 70, 80)
    COLOR_TEXT_DIM = (120, 130, 140)
    COLOR_ACCENT = (100, 150, 255)
    COLOR_SUCCESS = (100, 200, 100)
    COLOR_HIGHLIGHT = (255, 150, 50)
    COLOR_PLAYER = (255, 80, 80)
    
    # 房间配色
    COLOR_ROOM_BG = (245, 248, 250)
    COLOR_ROOM_WALL = (120, 130, 140)  # 更深的颜色，让墙更明显
    COLOR_ROOM_VISITED = (230, 240, 250)
    COLOR_DOOR = (255, 200, 50)  # 门的颜色（亮黄色，更明显）
    
    # 物品颜色（兜底颜色，当图片加载失败时使用）方案 B
    FRAGMENT_COLORS = {
        'e1': (255, 99, 71), 'e2': (255, 218, 185), 'e3': (255, 165, 0),
        'e4': (255, 182, 193), 'e5': (255, 255, 240), 'e6': (255, 228, 181),
        'b1': (220, 100, 80), 'b2': (230, 200, 170), 'b3': (240, 180, 100),
        'c1': (255, 160, 140), 'c2': (250, 245, 230), 'c3': (255, 235, 180),
        'd1': (240, 120, 100), 'd2': (255, 240, 200), 'd3': (255, 220, 170),
        'B': (200, 255, 200), 'C': (255, 220, 200), 'D': (255, 255, 200),
        'a1': (255, 140, 80), 'a2': (255, 200, 150), 'a3': (255, 160, 100), 'a4': (255, 150, 90),
        'A': (255, 215, 0),
        'target': (255, 0, 0), 'obstacle': (100, 50, 50),
        'tomato': (255, 100, 100), 'lettuce': (100, 200, 100), 'onion': (200, 100, 200), 'meat': (160, 100, 60),
        'plate': (200, 200, 200),
    }
    
    @staticmethod
    def get_font(size):
        """获取字体"""
        try:
            return pygame.font.SysFont('simhei', size)
        except:
            return pygame.font.SysFont('arial', size)


class NavigationConfig(BaseConfig):
    """导航任务配置"""
    TITLE = "Navigation Task - Spatial Navigation"
    
    # 奖励设置
    REWARD_STEP = -0.1              # 每步移动
    REWARD_INVALID_MOVE = -0.5       # 无效移动（撞墙）
    REWARD_REACH_TARGET = 10.0       # 到达目标
    
    # 熵范围设置
    ENTROPY_LOW = (0.0, 0.3)         # 低熵范围
    ENTROPY_MEDIUM = (0.4, 0.6)      # 中熵范围（规划优势最大）
    ENTROPY_HIGH = (0.7, 0.9)        # 高熵范围
    
    # 障碍物生成参数
    OBSTACLE_DENSITY_LOW = 0.1       # 低密度障碍物比例
    OBSTACLE_DENSITY_MEDIUM = 0.3    # 中密度障碍物比例
    OBSTACLE_DENSITY_HIGH = 0.6      # 高密度障碍物比例
    
    # 可见性网络参数
    VISIBILITY_RANGE = 5             # 可见性检查范围（格子数）


class Navigation2Config(BaseConfig):
    """城市交通导航任务配置（地铁+传送门）"""
    TITLE = "Navigation2 - City Traffic (Subway & Portal)"

    # 继承导航基础奖励
    REWARD_STEP = -0.1
    REWARD_INVALID_MOVE = -0.5
    REWARD_REACH_TARGET = 10.0

    # 地铁
    SUBWAY_MOVE_CELLS = 3            # 在地铁上每步移动格数
    SUBWAY_TRAIN_PERIOD = 1          # 列车每 1 步前进 1 格（在站点则停 1 步）
    SUBWAY_STOP_DURATION = 1         # 到站停靠 1 步后继续
    SUBWAY_TRAIN_LOOP = True         # 列车到达终点后是否循环回起点
    SUBWAY_MIN_STATION_SPACING = 2   # 站点最小间隔（路径格数），用于动态计算站点数量
    SUBWAY_BOARD_SAME_ROOM = True    # 为 True 时允许在同房间内任意格子上车（站点所在房间）
    COLOR_SUBWAY_LINE = (80, 120, 255)   # 地铁路径蓝色
    COLOR_TRAIN_CAN_BOARD = (100, 255, 100)   # 绿色可上车
    COLOR_TRAIN_CANNOT_BOARD = (255, 80, 80)  # 红色不可上车

    # 传送门
    COLOR_PORTAL = (255, 220, 50)    # 传送门黄色
    PORTAL_MIN_DIST_FROM_TARGET = 2  # 传送门出口与目标最少间隔（房间数）

    # 局部可见：仅显示当前格 + 一步可达格子（含地铁/传送门下一节点），不可见区域留空
    ONLY_SHOW_REACHABLE = True

    # 熵/障碍物（与 NavigationConfig 一致）
    ENTROPY_LOW = (0.0, 0.3)
    ENTROPY_MEDIUM = (0.4, 0.6)
    ENTROPY_HIGH = (0.7, 0.9)
    VISIBILITY_RANGE = 5


class Navigation3Config(Navigation2Config):
    """Navigation3：仅三张地图，扩展格子间距 + 虚线连接 UI。"""
    TITLE = "Navigation3 - 网格2/线性2/环状2"
    # 格子间距：逻辑步长与绘制尺寸分离，整体放大、格子之间留缝更宽
    GRID_STEP = 72          # 相邻格子中心间距（像素），格子之间更疏朗
    CELL_DRAW_SIZE = 48     # 每格绘制边长（整体放大）；margin = (GRID_STEP - CELL_DRAW_SIZE) // 2 = 12


class OvercookedConfig(BaseConfig):
    """物品合成任务配置"""
    TITLE = "Overcooked Task - Item Synthesis"
    
    # 背包设置
    BACKPACK_CAPACITY = 4
    
    # 奖励设置
    REWARD_STEP = -0.1              # 每步移动
    REWARD_INVALID_MOVE = -0.5       # 无效移动
    REWARD_COLLECT = 0.5            # 收集物品
    REWARD_DITCH = -0.2             # 丢弃物品
    REWARD_TRANSFORM = 1.0          # 自动转化
    REWARD_MERGE = 2.0              # 手动合成
    REWARD_STAGE_COMPLETE = 10.0     # 完成阶段目标（合成a1或a2）
    REWARD_WIN = 20.0               # 完成所有阶段（游戏结束）


class AlchemyConfig(BaseConfig):
    """小小炼金术任务配置"""
    TITLE = "小小炼金术 - Little Alchemy"
    
    # 奖励设置
    REWARD_ADD = 0.5                # 添加元素
    REWARD_SYNTHESIS = 2.0          # 合成成功
    REWARD_TRANSFORM = 1.0          # 自动转化
    REWARD_REMOVE = -0.2            # 移除元素


class AlchemyExperimentConfig:
    """小小炼金术实验配置"""
    # 实验阶段
    PHASE_LEARNING = "learning"     # 学习阶段
    PHASE_TESTING = "testing"       # 测试阶段
    PHASE_RULE_PRESENTATION = "rule_presentation"  # 规则呈现阶段
    PHASE_ACTION_EXECUTION = "action_execution"    # 行动执行阶段
    PHASE_STRUCTURE_TRANSFER = "structure_transfer"  # 结构迁移测试阶段
    
    # 规则复杂度（可选：no_operator, cfg, lexicalized_pcfg）
    # no_operator: 无算子（基线条件）
    # cfg: 上下文无关语法
    # lexicalized_pcfg: 词汇化概率上下文无关语法
    RULE_COMPLEXITY = "cfg"         # 默认CFG复杂度
    
    # 提示条件
    HINT_LEVEL = "none"             # none: 无提示, partial: 部分提示, full: 完整提示
    
    # 反馈类型
    FEEDBACK_TYPE = "immediate"     # immediate: 即时反馈, delayed: 延迟反馈, none: 无反馈
    
    # 时间限制（秒，None表示无限制）
    TIME_LIMIT = None               # 学习阶段时间限制
    
    # 尝试次数限制（None表示无限制）
    MAX_ATTEMPTS = None             # 学习阶段最大尝试次数
    
    # 测试阶段目标元素列表
    TEST_TARGETS = ['A']            # 要求合成的目标元素
    
    # 实验试次数量
    NUM_TRIALS = 1                  # 实验试次数量
    
    # 是否显示得分（实验室模式建议关闭）
    SHOW_SCORE = False              # 是否显示得分
    
    # 是否显示游戏化元素
    SHOW_GAMIFICATION = False       # 是否显示游戏化元素（奖励动画等）
    
    # 是否显示前缀表达式结构
    SHOW_POLISH_NOTATION = True     # 是否显示前缀表达式规则结构
    
    # 结构迁移测试配置
    ENABLE_STRUCTURE_TRANSFER = True  # 是否启用结构迁移测试
    TRANSFER_TEST_TARGETS = []      # 迁移测试目标列表


class Alchemy2Config(BaseConfig):
    """剪纸填色游戏配置（Alchemy2）"""
    TITLE = "剪纸填色 - Paper Cut & Color"

    # 奖励
    REWARD_ADD = 0.5                # 从素材栏拖入
    REWARD_SYNTHESIS = 2.0          # 合成成功
    REWARD_SUBMIT = 10.0            # 提交订单成功

    # 订单
    ORDER_DURATION = 30             # 订单超时秒数（可选）
    ORDER_INTERVAL = 2.0            # 完成订单后多少秒刷新新订单

