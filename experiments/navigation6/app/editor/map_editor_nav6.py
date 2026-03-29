"""
Navigation6 地图编辑器：单格 + 公交/地铁/轻轨路径与站点。
"""
import math
import pygame
import sys
import os
import json
import time
from typing import Optional, Tuple, Dict, List, Any
from collections import defaultdict
from pathlib import Path

# 直接运行本脚本时，把项目根加入 sys.path，保证 experiments/shared 可导入。
# .../Minecraft8.0/experiments/navigation6/app/editor/map_editor_nav6.py -> .../Minecraft8.0
_this_file = Path(__file__).resolve()
_project_root = _this_file.parents[4]
_project_root_str = str(_project_root)
if _project_root_str not in sys.path:
    sys.path.insert(0, _project_root_str)

DEBUG_LOG_PATH = os.path.join(_project_root_str, "debug-c9e6b4.log")

def _debug_log(message: str, data: dict, hypothesis_id: str = ""):
    import json as _json
    try:
        payload = {"sessionId": "c9e6b4", "location": "map_editor_nav6", "message": message, "data": data, "timestamp": int(time.time() * 1000)}
        if hypothesis_id:
            payload["hypothesisId"] = hypothesis_id
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(_json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass

try:
    import tkinter as tk
    from tkinter import filedialog
except ImportError:
    tk = None
    filedialog = None

from shared.common.asset_manager import AssetManager
from shared.common.renderer import Renderer
from shared.config import Navigation2Config, BaseConfig
from experiments.navigation6.app.editor.map_generator_nav6 import Navigation6MapGenerator
from experiments.navigation6.app.editor.editor_data_nav6 import (
    EditorMapDataNav6,
    direction_from_room_centers,
    direction_from_points,
)
from experiments.navigation6.app.editor.editor_constants_nav6 import (
    ToolType, EditorColors, EditorLayout, TOOL_CONFIGS, KEY_SHORTCUTS, TRANSIT_KIND_BY_TOOL
)

_PATH_TOOLS = frozenset({
    ToolType.BUS_PATH, ToolType.METRO_PATH, ToolType.LIGHT_RAIL_PATH,
})
_STATION_TOOLS = frozenset({
    ToolType.BUS_STATION, ToolType.METRO_STATION, ToolType.LIGHT_RAIL_STATION,
})
_TRANSIT_EDIT_TOOLS = _PATH_TOOLS | _STATION_TOOLS | frozenset({ToolType.TRANSIT_CURVE})
from experiments.navigation6.app.editor.editor_commands_nav6 import CommandHistory, CommandFactory


def get_chinese_font(size: int):
    """获取支持中文的字体"""
    chinese_fonts = [
        "SimHei", "Microsoft YaHei", "SimSun", "KaiTi",
        "FangSong", "STHeiti", "STSong", "Microsoft JhengHei", "NSimSun"
    ]
    
    for font_name in chinese_fonts:
        try:
            font = pygame.font.SysFont(font_name, size)
            test_surface = font.render("测试", True, (255, 255, 255))
            if test_surface.get_width() > 0:
                test_text = font.render("中", True, (255, 255, 255))
                if test_text.get_width() > 0 and test_text.get_width() < size * 2:
                    return font
        except Exception:
            continue
    
    try:
        font = pygame.font.SysFont(None, size)
        test_surface = font.render("测试", True, (255, 255, 255))
        if test_surface.get_width() > 0:
            return font
    except:
        pass
    
    return pygame.font.Font(None, size)


class MapEditorNav6:
    """Navigation6 地图编辑器主类（公交/地铁/轻轨 + 单格）"""
    
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode(
            (EditorLayout.SCREEN_WIDTH, EditorLayout.SCREEN_HEIGHT)
        )
        pygame.display.set_caption("Navigation6 地图编辑器（公交/地铁/轻轨）")
        
        # 初始化组件
        self.asset_manager = AssetManager()
        self.renderer = Renderer(self.screen)
        
        # 编辑器数据
        self.editor_data = EditorMapDataNav6()
        self.command_history = CommandHistory(max_history=100)
        
        # 编辑器状态
        self.current_tool = ToolType.SELECT
        
        # 鼠标状态
        self.mouse_pos = (0, 0)
        self.mouse_down = False
        self.last_click_time = 0
        self.double_click_threshold = 0.3
        
        # 文件状态
        self.current_filepath = None
        self.unsaved_changes = False
        
        # UI状态
        self.status_messages = []
        self.show_help = False
        # 门工具：第一次点击为源（房间或单格），第二次为目标（房间或单格）
        self.door_tool_source_rid: Optional[int] = None
        self.door_tool_source_cell: Optional[Tuple[int, int]] = None
        
        # 画布偏移（用于移动视图）
        self.canvas_offset_x = 0
        self.canvas_offset_y = 0
        # 线路弧度工具：展平线路索引 + 段索引（path[i]→path[i+1]）
        self.transit_curve_pick: Optional[Tuple[int, int]] = None
        
        # 字体
        self.font_sm = get_chinese_font(EditorLayout.FONT_SMALL)
        self.font_md = get_chinese_font(EditorLayout.FONT_MEDIUM)
        self.font_lg = get_chinese_font(EditorLayout.FONT_LARGE)
        
        # 地图保存目录
        current_file = os.path.abspath(__file__)
        current_dir = os.path.dirname(current_file)
        # 地图静态资源目录：assets/maps
        maps_dir_path = os.path.join(os.path.dirname(current_dir), "assets", "maps")
        self.maps_dir = Path(maps_dir_path)
        self.maps_dir.mkdir(parents=True, exist_ok=True)
        
        # 设置键盘重复
        pygame.key.set_repeat(200, 50)
    
    def run(self):
        """运行编辑器主循环"""
        clock = pygame.time.Clock()
        running = True
        
        try:
            while running:
                # 处理事件
                self._handle_events()
                
                # 更新状态
                self._update()
                
                # 绘制界面
                # #region agent log
                try:
                    self._draw()
                except Exception as _e:
                    import traceback
                    _debug_log("draw_exception", {"error": str(_e), "type": type(_e).__name__, "tb": traceback.format_exc()}, "H2")
                    raise
                # #endregion
                
                # 更新显示
                pygame.display.flip()
                clock.tick(60)
        
        except KeyboardInterrupt:
            pass
        finally:
            pygame.quit()
            sys.exit()
    
    def _handle_events(self):
        """处理所有事件"""
        self.mouse_pos = pygame.mouse.get_pos()
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._handle_quit()
            
            elif event.type == pygame.KEYDOWN:
                self._handle_keydown(event)
            
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self._handle_mouse_down(event)
            
            elif event.type == pygame.MOUSEBUTTONUP:
                self._handle_mouse_up(event)
            
            elif event.type == pygame.MOUSEMOTION:
                self._handle_mouse_motion(event)

            elif event.type == pygame.MOUSEWHEEL:
                self._handle_mouse_wheel(event)
    
    def _handle_quit(self):
        """处理退出事件"""
        if self.unsaved_changes:
            # 简单提示，实际可以添加确认对话框
            print("有未保存的更改")
        pygame.quit()
        sys.exit()
    
    def _handle_keydown(self, event: pygame.event.Event):
        """处理键盘按下事件"""
        keys = pygame.key.get_pressed()
        ctrl_pressed = keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL]
        shift_pressed = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        
        # 快捷键处理
        if ctrl_pressed:
            if event.key == pygame.K_z:  # Ctrl+Z 撤销
                self._undo()
            elif event.key == pygame.K_y:  # Ctrl+Y 重做
                self._redo()
            elif event.key == pygame.K_s:  # Ctrl+S 保存
                self._save_file()
            elif event.key == pygame.K_o:  # Ctrl+O 打开
                self._load_file()
            elif event.key == pygame.K_n:  # Ctrl+N 新建
                self._new_file()
        else:
            # 工具快捷键
            if event.key in KEY_SHORTCUTS:
                tool = KEY_SHORTCUTS[event.key]
                if isinstance(tool, ToolType):
                    self.current_tool = tool
                    self.door_tool_source_rid = None
                    self.door_tool_source_cell = None
                    if tool in TRANSIT_KIND_BY_TOOL:
                        self.editor_data.set_transit_edit_kind(TRANSIT_KIND_BY_TOOL[tool])
                    self._add_status_message(f"切换到工具: {TOOL_CONFIGS[tool]['name']}")
            
            # 方向键移动画布
            elif event.key in [pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT]:
                move_amount = 20
                if shift_pressed:
                    move_amount = 50
                
                if event.key == pygame.K_UP:
                    self.canvas_offset_y += move_amount
                elif event.key == pygame.K_DOWN:
                    self.canvas_offset_y -= move_amount
                elif event.key == pygame.K_LEFT:
                    self.canvas_offset_x += move_amount
                elif event.key == pygame.K_RIGHT:
                    self.canvas_offset_x -= move_amount

            elif self.current_tool == ToolType.TRANSIT_CURVE:
                if event.key == pygame.K_TAB:
                    self._advance_transit_curve_pick_tab(forward=not shift_pressed)
                elif self.transit_curve_pick is not None:
                    flat_idx, seg_idx = self.transit_curve_pick
                    if event.key == pygame.K_l:
                        cmd = CommandFactory.create_set_transit_segment_straight_command(
                            self.editor_data, flat_idx, seg_idx, True
                        )
                        if self.command_history.execute_command(cmd):
                            self.unsaved_changes = True
                            self._add_status_message(f"段 {flat_idx}:{seg_idx} 已设为直线（滚轮/弧度会取消直线）")
                        else:
                            self._add_status_message("该段已是直线", "info")
                    elif event.key == pygame.K_0:
                        cmd = CommandFactory.create_set_transit_segment_curve_command(
                            self.editor_data, flat_idx, seg_idx, 0.0
                        )
                        if self.command_history.execute_command(cmd):
                            self.unsaved_changes = True
                            self._add_status_message(f"段 {flat_idx}:{seg_idx} 弧度已复位为自动")
                    elif event.key == pygame.K_LEFTBRACKET:
                        self._apply_transit_curve_delta(flat_idx, seg_idx, -0.2)
                    elif event.key == pygame.K_RIGHTBRACKET:
                        self._apply_transit_curve_delta(flat_idx, seg_idx, 0.2)

    def _handle_mouse_down(self, event: pygame.event.Event):
        """处理鼠标按下事件"""
        self.mouse_down = True
        current_time = time.time()
        
        # 检查是否在画布区域内
        if EditorLayout.CANVAS_RECT.collidepoint(event.pos):
            self._handle_canvas_click(event)
        
        # 检查是否在工具栏区域内
        elif EditorLayout.PANEL_LEFT_RECT.collidepoint(event.pos):
            self._handle_toolbar_click(event)
        
        # 记录点击时间（用于双击检测）
        if current_time - self.last_click_time < self.double_click_threshold:
            self._handle_double_click(event)
        self.last_click_time = current_time
    
    def _handle_mouse_up(self, event: pygame.event.Event):
        """处理鼠标释放事件"""
        self.mouse_down = False
    
    def _handle_mouse_motion(self, event: pygame.event.Event):
        """处理鼠标移动事件"""
        pass
    
    def _handle_double_click(self, event: pygame.event.Event):
        """处理双击事件"""
        pass
    
    def _handle_canvas_click(self, event: pygame.event.Event):
        """处理画布点击事件"""
        canvas_x = event.pos[0] - EditorLayout.CANVAS_RECT.x - self.canvas_offset_x
        canvas_y = event.pos[1] - EditorLayout.CANVAS_RECT.y - self.canvas_offset_y
        gx = int(canvas_x // EditorLayout.GRID_SIZE)
        gy = int(canvas_y // EditorLayout.GRID_SIZE)
        # #region agent log
        _debug_log("canvas_click", {"gx": gx, "gy": gy, "tool": str(self.current_tool), "in_single_cell": (gx, gy) in self.editor_data.single_cells, "has_room": self.editor_data.get_room_by_grid(gx, gy) is not None}, "H5")
        try:
        # #endregion
            if self.current_tool in TRANSIT_KIND_BY_TOOL:
                self.editor_data.set_transit_edit_kind(TRANSIT_KIND_BY_TOOL[self.current_tool])
            if self.current_tool == ToolType.WALL:
                self._handle_wall_tool(gx, gy)
            elif self.current_tool == ToolType.SINGLE_CELL:
                self._handle_single_cell_tool(gx, gy)
            elif self.current_tool in _PATH_TOOLS:
                self._handle_subway_path_tool(gx, gy, event.button == 3)
            elif self.current_tool in _STATION_TOOLS:
                self._handle_subway_station_tool(gx, gy)
            elif self.current_tool == ToolType.TRANSIT_CURVE:
                self._handle_transit_curve_canvas_click(event)
            elif self.current_tool == ToolType.START_POINT:
                self._handle_start_point_tool(gx, gy)
            elif self.current_tool == ToolType.TARGET_POINT:
                self._handle_target_point_tool(gx, gy)
            elif self.current_tool == ToolType.SELECT:
                self._handle_select_tool(gx, gy)
        # #region agent log
        except Exception as e:
            import traceback
            _debug_log("canvas_click_handler_exception", {"error": str(e), "type": type(e).__name__, "tb": traceback.format_exc()}, "H1")
            raise
        # #endregion
    
    def _handle_room_tool(self, gx: int, gy: int, is_delete: bool):
        """处理房间工具"""
        lx, ly = gx // 3, gy // 3
        
        if is_delete:
            # 删除房间
            rid = ly * 100 + lx
            if rid in self.editor_data.rooms:
                cmd = CommandFactory.create_remove_room_command(self.editor_data, rid)
                if self.command_history.execute_command(cmd):
                    self.unsaved_changes = True
                    self._add_status_message(f"删除房间 ({lx}, {ly})")
        else:
            # 添加房间
            if self.editor_data.add_room(lx, ly):
                cmd = CommandFactory.create_add_room_command(self.editor_data, lx, ly)
                self.command_history.execute_command(cmd)
                self.unsaved_changes = True
                self._add_status_message(f"添加房间 ({lx}, {ly})")
    
    def _handle_door_tool(self, gx: int, gy: int, canvas_x: float = 0, canvas_y: float = 0):
        """门工具：先点源（房间或单格），再点目标（房间或单格），按角度设置/切换门线；ESC 取消。"""
        room = self.editor_data.get_room_by_grid(gx, gy)
        in_cell = (gx, gy) in self.editor_data.single_cells
        # 已选源单格，第二次点击
        if self.door_tool_source_cell is not None:
            src_gx, src_gy = self.door_tool_source_cell
            x1, y1 = src_gx + 0.5, src_gy + 0.5
            if room:
                x2, y2 = room.logical_pos[0] * 3 + 1, room.logical_pos[1] * 3 + 1
                direction = direction_from_points(x1, y1, x2, y2)
                if direction is None:
                    self.door_tool_source_cell = None
                    return
                doors = self.editor_data.get_single_cell_doors(src_gx, src_gy)
                if room.id in (doors.get(direction) or []):
                    self.editor_data.remove_single_cell_door(src_gx, src_gy, direction, target=room.id)
                    self.unsaved_changes = True
                    self._add_status_message(f"删除单格门线 ({src_gx},{src_gy}) -> 房间 {room.id} ({direction})")
                else:
                    if self.editor_data.set_single_cell_door_to(src_gx, src_gy, direction, room.id):
                        self.unsaved_changes = True
                        self._add_status_message(f"添加单格门线 ({src_gx},{src_gy}) -> 房间 {room.id} ({direction})")
            elif in_cell and (gx, gy) != (src_gx, src_gy):
                x2, y2 = gx + 0.5, gy + 0.5
                direction = direction_from_points(x1, y1, x2, y2)
                if direction is None:
                    self.door_tool_source_cell = None
                    return
                doors = self.editor_data.get_single_cell_doors(src_gx, src_gy)
                if (gx, gy) in (doors.get(direction) or []):
                    self.editor_data.remove_single_cell_door(src_gx, src_gy, direction, target=(gx, gy))
                    self.unsaved_changes = True
                    self._add_status_message(f"删除单格门线 ({src_gx},{src_gy}) -> ({gx},{gy}) ({direction})")
                else:
                    if self.editor_data.set_single_cell_door_to(src_gx, src_gy, direction, (gx, gy)):
                        self.unsaved_changes = True
                        self._add_status_message(f"添加单格门线 ({src_gx},{src_gy}) -> ({gx},{gy}) ({direction})")
            elif in_cell and (gx, gy) == (src_gx, src_gy):
                self._add_status_message("请点击另一个单格或房间作为目标")
            else:
                self.door_tool_source_cell = None
            self.door_tool_source_cell = None
            return
        # 已选源房间，第二次点击
        if room:
            rid = room.id
            lx, ly = room.logical_pos
            if self.door_tool_source_rid is None:
                self.door_tool_source_rid = rid
                self.door_tool_source_cell = None
                self._add_status_message("已选源房间，请点击目标房间（ESC 取消）")
                return
            if self.door_tool_source_rid == rid:
                self._add_status_message("请点击另一个房间作为目标")
                return
            source_rid = self.door_tool_source_rid
            source_room = self.editor_data.rooms.get(source_rid)
            if not source_room:
                self.door_tool_source_rid = None
                return
            lx1, ly1 = source_room.logical_pos
            lx2, ly2 = room.logical_pos
            direction = direction_from_room_centers(lx1, ly1, lx2, ly2)
            if direction is None:
                self._add_status_message("源与目标重合，未设置门")
                self.door_tool_source_rid = None
                return
            if rid in (source_room.doors.get(direction) or []):
                self.editor_data.remove_door(source_rid, direction, target_rid=rid)
                self.unsaved_changes = True
                self._add_status_message(f"删除门线 {source_rid} -> {rid} ({direction})")
            else:
                if self.editor_data.set_door_to_room(source_rid, direction, rid):
                    self.unsaved_changes = True
                    self._add_status_message(f"添加门线 {source_rid} -> {rid} ({direction})")
            self.door_tool_source_rid = None
            return
        # 第一次点击在单格上
        if in_cell:
            self.door_tool_source_rid = None
            self.door_tool_source_cell = (gx, gy)
            self._add_status_message("已选源单格，请点击目标房间或单格（ESC 取消）")
            return
        self.door_tool_source_rid = None
        self.door_tool_source_cell = None
    
    def _handle_wall_tool(self, gx: int, gy: int):
        """处理墙/障碍物工具"""
        cmd = CommandFactory.create_toggle_obstacle_command(self.editor_data, gx, gy)
        if self.command_history.execute_command(cmd):
            self.unsaved_changes = True
            action = "添加" if (gx, gy) not in self.editor_data.obstacle_map else "删除"
            self._add_status_message(f"{action}障碍物 ({gx}, {gy})")
    
    def _handle_single_cell_tool(self, gx: int, gy: int):
        """处理单个可行走格工具"""
        cmd = CommandFactory.create_toggle_single_cell_command(self.editor_data, gx, gy)
        if self.command_history.execute_command(cmd):
            self.unsaved_changes = True
            action = "添加" if (gx, gy) in self.editor_data.single_cells else "删除"
            self._add_status_message(f"{action}单格可行走 ({gx}, {gy})")
        else:
            if self.editor_data.get_room_by_grid(gx, gy) is not None:
                self._add_status_message("该格在房间内，无法添加单格可行走")
            elif (gx, gy) in self.editor_data.obstacle_map:
                self._add_status_message("该格为障碍物，无法添加单格可行走")
    
    def _handle_subway_path_tool(self, gx: int, gy: int, is_delete: bool):
        """处理地铁路径工具"""
        if is_delete:
            cmd = CommandFactory.create_remove_subway_path_point_command(self.editor_data, gx, gy)
            if self.command_history.execute_command(cmd):
                self.unsaved_changes = True
                self._add_status_message(f"删除地铁路径点 ({gx}, {gy})")
        else:
            cmd = CommandFactory.create_add_subway_path_point_command(self.editor_data, gx, gy)
            if self.command_history.execute_command(cmd):
                self.unsaved_changes = True
                self._add_status_message(f"添加地铁路径点 ({gx}, {gy})")
    
    def _handle_subway_station_tool(self, gx: int, gy: int):
        """处理公交/地铁/轻轨站点工具（同一格可叠多条线路的站点）。"""
        cmd = CommandFactory.create_toggle_subway_station_command(self.editor_data, gx, gy)
        if self.command_history.execute_command(cmd):
            self.unsaved_changes = True
            action = "添加" if cmd.was_added else "删除"
            self._add_status_message(f"{action}站点 ({gx}, {gy}) [{self.editor_data.transit_edit_kind}]")
        else:
            self._add_status_message(
                f"无法切换站点 ({gx}, {gy})：须在当前线路路径上，或先标为单格可行走"
            )

    @staticmethod
    def _point_seg_dist_sq(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
        abx, aby = bx - ax, by - ay
        apx, apy = px - ax, py - ay
        ab2 = abx * abx + aby * aby
        if ab2 < 1e-12:
            dx, dy = px - ax, py - ay
            return dx * dx + dy * dy
        t = max(0.0, min(1.0, (apx * abx + apy * aby) / ab2))
        qx = ax + t * abx
        qy = ay + t * aby
        dx, dy = px - qx, py - qy
        return dx * dx + dy * dy

    @staticmethod
    def _min_dist_sq_point_to_polyline(px: float, py: float, poly: List[Tuple[float, float]]) -> float:
        """点击到折线各子段的最近距离平方。"""
        if len(poly) < 2:
            return float("inf")
        best = float("inf")
        for j in range(len(poly) - 1):
            ax, ay = poly[j]
            bx, by = poly[j + 1]
            d = MapEditorNav6._point_seg_dist_sq(px, py, ax, ay, bx, by)
            if d < best:
                best = d
        return best

    def _hit_test_transit_segment(self, screen_pos: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        """返回 (展平线路索引, 段索引)。沿「实际绘制的曲线折线」测距，避免点到鼓起的弧线却判未命中。"""
        if not EditorLayout.CANVAS_RECT.collidepoint(screen_pos):
            return None
        canvas_rect = EditorLayout.CANVAS_RECT
        mx, my = float(screen_pos[0]), float(screen_pos[1])
        gs = EditorLayout.GRID_SIZE
        thresh_sq = 40.0 * 40.0
        best: Optional[Tuple[int, int]] = None
        best_d = thresh_sq
        for line_idx, line in enumerate(self.editor_data.subway_lines):
            path = line.get("path", [])
            if len(path) < 2:
                continue
            sc = line.get("segment_curve") or []
            st = line.get("segment_straight") or []
            for i in range(len(path) - 1):
                gx0, gy0 = path[i]
                gx1, gy1 = path[i + 1]
                ax = canvas_rect.x + self.canvas_offset_x + gx0 * gs + gs // 2
                ay = canvas_rect.y + self.canvas_offset_y + gy0 * gs + gs // 2
                bx = canvas_rect.x + self.canvas_offset_x + gx1 * gs + gs // 2
                by = canvas_rect.y + self.canvas_offset_y + gy1 * gs + gs // 2
                bias = float(sc[i]) if i < len(sc) else 0.0
                straight = bool(st[i]) if i < len(st) else False
                poly = self._transit_segment_polyline(
                    float(ax), float(ay), float(bx), float(by), line_idx, i, bias, force_straight=straight
                )
                d_sq = self._min_dist_sq_point_to_polyline(mx, my, poly)
                if d_sq < best_d:
                    best_d = d_sq
                    best = (line_idx, i)
        return best

    def _list_all_transit_segments_ordered(self) -> List[Tuple[int, int]]:
        """展平线路索引 + 段索引，顺序固定便于 TAB 遍历全图。"""
        out: List[Tuple[int, int]] = []
        for line_idx, line in enumerate(self.editor_data.subway_lines):
            path = line.get("path", [])
            for seg_i in range(len(path) - 1):
                out.append((line_idx, seg_i))
        return out

    def _transit_segments_near_screen_point(
        self, screen_pos: Tuple[int, int], max_dist_sq: float
    ) -> List[Tuple[int, int]]:
        """距屏幕坐标 max_dist 内的路径段，按距离近→远排序（密集重叠时 TAB 只在其中轮换）。"""
        if not EditorLayout.CANVAS_RECT.collidepoint(screen_pos):
            return []
        canvas_rect = EditorLayout.CANVAS_RECT
        mx, my = float(screen_pos[0]), float(screen_pos[1])
        gs = EditorLayout.GRID_SIZE
        scored: List[Tuple[float, int, int]] = []
        for line_idx, line in enumerate(self.editor_data.subway_lines):
            path = line.get("path", [])
            if len(path) < 2:
                continue
            for i in range(len(path) - 1):
                gx0, gy0 = path[i]
                gx1, gy1 = path[i + 1]
                ax = canvas_rect.x + self.canvas_offset_x + gx0 * gs + gs // 2
                ay = canvas_rect.y + self.canvas_offset_y + gy0 * gs + gs // 2
                bx = canvas_rect.x + self.canvas_offset_x + gx1 * gs + gs // 2
                by = canvas_rect.y + self.canvas_offset_y + gy1 * gs + gs // 2
                d_sq = self._point_seg_dist_sq(mx, my, ax, ay, bx, by)
                if d_sq <= max_dist_sq:
                    scored.append((d_sq, line_idx, i))
        scored.sort(key=lambda t: t[0])
        return [(t[1], t[2]) for t in scored]

    def _add_transit_curve_selection_status(self, flat_idx: int, seg_idx: int, prefix: str = "已选") -> None:
        val = self.editor_data.get_segment_curve_value(flat_idx, seg_idx)
        if val is None:
            self._add_status_message("无效路径段", "warning")
            return
        kl = self.editor_data._flat_index_to_kind_line(flat_idx)
        kind_label = f"{kl[0]}#{kl[1]}" if kl else "?"
        st = self.editor_data.get_segment_straight(flat_idx, seg_idx)
        st_txt = "直线" if st else "曲线"
        self._add_status_message(
            f"{prefix} [{kind_label}] 段{seg_idx} 弧度={val:.2f}（{st_txt}）— 滚轮调弯，L 直线，"
            f"TAB 切换邻近段（Shift+TAB 反向），右击/0 复位，[ / ] 微调"
        )

    def _advance_transit_curve_pick_tab(self, forward: bool) -> None:
        """在鼠标附近的候选段中循环；若无邻近段则遍历全图所有段。"""
        NEAR_SQ = 48.0 * 48.0
        canvas_rect = EditorLayout.CANVAS_RECT
        cands: List[Tuple[int, int]] = []
        if canvas_rect.collidepoint(self.mouse_pos):
            cands = self._transit_segments_near_screen_point(self.mouse_pos, NEAR_SQ)
        if not cands:
            cands = self._list_all_transit_segments_ordered()
        if not cands:
            self._add_status_message("没有可选的路径段（线路需至少 2 个路径点）", "warning")
            return
        cur = self.transit_curve_pick
        if cur is None or cur not in cands:
            nxt = cands[0]
        else:
            k = cands.index(cur)
            k = (k + 1) % len(cands) if forward else (k - 1) % len(cands)
            nxt = cands[k]
        self.transit_curve_pick = nxt
        fi, sj = nxt
        idx_show = cands.index(nxt) + 1
        prefix = f"TAB {idx_show}/{len(cands)}"
        self._add_transit_curve_selection_status(fi, sj, prefix=prefix)

    def _apply_transit_curve_delta(self, flat_idx: int, seg_idx: int, delta: float) -> None:
        old = self.editor_data.get_segment_curve_value(flat_idx, seg_idx)
        if old is None:
            return
        nv = max(-4.0, min(4.0, old + delta))
        cmd = CommandFactory.create_set_transit_segment_curve_command(self.editor_data, flat_idx, seg_idx, nv)
        if self.command_history.execute_command(cmd):
            self.unsaved_changes = True
            self._add_status_message(f"段 {flat_idx}:{seg_idx} 弧度={nv:.2f}（0=自动）")

    def _handle_mouse_wheel(self, event: pygame.event.Event) -> None:
        if self.current_tool != ToolType.TRANSIT_CURVE:
            return
        if not EditorLayout.CANVAS_RECT.collidepoint(self.mouse_pos):
            return
        dy = int(getattr(event, "y", 0))
        if dy == 0:
            return
        delta = float(dy) * 0.25
        hit = self._hit_test_transit_segment(self.mouse_pos)
        if hit is None:
            return
        self.transit_curve_pick = hit
        flat_idx, seg_idx = hit
        self._apply_transit_curve_delta(flat_idx, seg_idx, delta)

    def _handle_transit_curve_canvas_click(self, event: pygame.event.Event) -> None:
        if not EditorLayout.CANVAS_RECT.collidepoint(event.pos):
            self._add_status_message("请在左侧白色地图画布内点击（不要点在工具栏或右侧属性区）", "warning")
            return
        hit = self._hit_test_transit_segment(event.pos)
        if hit is None:
            if not self._list_all_transit_segments_ordered():
                self._add_status_message("没有可编辑的路径段：每条线路至少需要 2 个路径点", "warning")
            else:
                self._add_status_message(
                    "未命中路径段：请更贴近彩色线路点击，或按 TAB 在鼠标附近的段之间切换",
                    "warning",
                )
            return
        self.transit_curve_pick = hit
        flat_idx, seg_idx = hit
        if event.button == 3:
            kl = self.editor_data._flat_index_to_kind_line(flat_idx)
            kind_label = f"{kl[0]}#{kl[1]}" if kl else "?"
            cmd = CommandFactory.create_set_transit_segment_curve_command(
                self.editor_data, flat_idx, seg_idx, 0.0
            )
            if self.command_history.execute_command(cmd):
                self.unsaved_changes = True
                self._add_status_message(f"已复位 [{kind_label}] 段{seg_idx} 为自动弧度")
            return
        self._add_transit_curve_selection_status(flat_idx, seg_idx)

    def _handle_portal_tool(self, gx: int, gy: int):
        """处理传送门工具"""
        if self.editor_data.portal_entrance is None:
            # 选择入口
            self.editor_data.set_portal_entrance(gx, gy)
            self._add_status_message(f"选择传送门入口 ({gx}, {gy})，请再点击选择出口")
        else:
            # 选择出口，完成传送门对
            # 先保存入口位置，因为 set_portal_exit 会清除 portal_entrance
            entrance_pos = self.editor_data.portal_entrance
            
            # 检查入口和出口是否相同
            if entrance_pos == (gx, gy):
                self.editor_data.cancel_portal_creation()
                self._add_status_message("入口和出口不能相同，取消传送门创建")
                return
            
            # 直接创建命令，不调用 set_portal_exit（因为命令会处理数据修改）
            cmd = CommandFactory.create_add_portal_pair_command(
                self.editor_data,
                entrance_pos,
                (gx, gy)
            )
            if self.command_history.execute_command(cmd):
                # 命令执行成功后，清除临时状态
                self.editor_data.portal_entrance = None
                self.unsaved_changes = True
                self._add_status_message(f"添加传送门 ({entrance_pos[0]},{entrance_pos[1]}) <-> ({gx},{gy})")
            else:
                self.editor_data.cancel_portal_creation()
                self._add_status_message("添加传送门失败")
    
    def _handle_start_point_tool(self, gx: int, gy: int):
        """处理起始点工具"""
        cmd = CommandFactory.create_set_start_pos_command(self.editor_data, gx, gy)
        if self.command_history.execute_command(cmd):
            self.unsaved_changes = True
            self._add_status_message(f"设置起始点 ({gx}, {gy})")
    
    def _handle_target_point_tool(self, gx: int, gy: int):
        """处理目标点工具"""
        cmd = CommandFactory.create_set_target_pos_command(self.editor_data, gx, gy)
        if self.command_history.execute_command(cmd):
            self.unsaved_changes = True
            self._add_status_message(f"设置目标点 ({gx}, {gy})")
    
    def _handle_select_tool(self, gx: int, gy: int):
        """处理选择工具"""
        room = self.editor_data.get_room_by_grid(gx, gy)
        if room:
            self.editor_data.select_room(room.id)
            self._add_status_message(f"选择房间 ({room.logical_pos[0]}, {room.logical_pos[1]})")
    
    def _handle_toolbar_click(self, event: pygame.event.Event):
        """处理工具栏点击"""
        rect = EditorLayout.PANEL_LEFT_RECT
        y = rect.y + 60
        button_height = EditorLayout.TOOL_BUTTON_SIZE + EditorLayout.TOOL_BUTTON_MARGIN
        
        # 工具按钮
        for tool in ToolType:
            btn_rect = pygame.Rect(rect.x + 10, y, rect.width - 20, EditorLayout.TOOL_BUTTON_SIZE)
            if btn_rect.collidepoint(event.pos):
                self.current_tool = tool
                if tool in TRANSIT_KIND_BY_TOOL:
                    self.editor_data.set_transit_edit_kind(TRANSIT_KIND_BY_TOOL[tool])
                self._add_status_message(f"切换到工具: {TOOL_CONFIGS[tool]['name']}")
                return
            y += button_height
        
        # 当前交通类别下的线路选择（路径/站点工具）
        if self.current_tool in _TRANSIT_EDIT_TOOLS:
            y += 8 + 22
            line_btn_h = 26
            kind = self.editor_data.transit_edit_kind
            kind_lines = self.editor_data.nav6_transit[kind]
            for i in range(len(kind_lines)):
                btn_rect = pygame.Rect(rect.x + 10, y, rect.width - 20, line_btn_h)
                if btn_rect.collidepoint(event.pos):
                    self.editor_data.set_current_subway_line(i)
                    self.unsaved_changes = True
                    self._add_status_message(f"当前编辑 [{kind}] 线路 {i + 1}")
                    return
                y += line_btn_h + 2
            add_rect = pygame.Rect(rect.x + 10, y, rect.width - 20, line_btn_h)
            if add_rect.collidepoint(event.pos):
                idx = self.editor_data.add_subway_line()
                self.editor_data.set_current_subway_line(idx)
                self.unsaved_changes = True
                self._add_status_message(f"已新建 [{kind}] 线路 {idx + 1}")
                return
            y += line_btn_h + 2
            if len(kind_lines) > 1:
                del_rect = pygame.Rect(rect.x + 10, y, rect.width - 20, line_btn_h)
                if del_rect.collidepoint(event.pos):
                    cur = self.editor_data.current_subway_line_index
                    if self.editor_data.remove_subway_line(cur):
                        self.unsaved_changes = True
                        self._add_status_message(f"已删除线路 {cur + 1}")
                    return
                y += line_btn_h + 2
            y += 8
        else:
            y += 2
        
        # 操作按钮
        y += 10
        op_buttons = [
            ("保存 (Ctrl+S)", self._save_file),
            ("加载 (Ctrl+O)", self._load_file),
            ("新建 (Ctrl+N)", self._new_file),
            ("撤销 (Ctrl+Z)", self._undo),
            ("重做 (Ctrl+Y)", self._redo),
        ]
        
        for text, handler in op_buttons:
            btn_rect = pygame.Rect(rect.x + 10, y, rect.width - 20, 30)
            if btn_rect.collidepoint(event.pos):
                handler()
                return
            y += 35
    
    def _undo(self):
        """撤销操作"""
        cmd = self.command_history.undo()
        if cmd:
            self.unsaved_changes = True
            self._add_status_message(f"撤销: {cmd.get_description()}")
    
    def _redo(self):
        """重做操作"""
        cmd = self.command_history.redo()
        if cmd:
            self.unsaved_changes = True
            self._add_status_message(f"重做: {cmd.get_description()}")
    
    def _save_file(self):
        """保存文件"""
        if self.current_filepath:
            self._save_to_file(self.current_filepath)
        else:
            # 使用默认文件名
            filename = f"map_{int(time.time())}.json"
            filepath = self.maps_dir / filename
            self._save_to_file(filepath)
    
    def _save_to_file(self, filepath: Path):
        """保存到指定文件"""
        try:
            data = self.editor_data.to_dict()
            data["metadata"]["modified_date"] = time.strftime("%Y-%m-%d")
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            self.current_filepath = filepath
            self.unsaved_changes = False
            self._add_status_message(f"保存成功: {filepath.name}", "success")
        except Exception as e:
            self._add_status_message(f"保存失败: {e}", "error")
    
    def _load_file(self):
        """加载文件：弹出对话框选择 maps 文件夹下的地图文件"""
        if filedialog is None or tk is None:
            # 无 tkinter 时回退为加载最新文件
            map_files = list(self.maps_dir.glob("*.json"))
            if map_files:
                map_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                self._load_from_file(map_files[0])
            else:
                self._add_status_message("没有找到地图文件", "warning")
            return
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        initial_dir = str(self.maps_dir.resolve())
        filepath = filedialog.askopenfilename(
            title="选择要打开的地图",
            initialdir=initial_dir,
            filetypes=[("JSON 地图", "*.json"), ("所有文件", "*.*")]
        )
        root.destroy()
        if filepath:
            self._load_from_file(Path(filepath))
        else:
            self._add_status_message("已取消打开", "info")
    
    def _load_from_file(self, filepath: Path):
        """从指定文件加载"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if self.editor_data.from_dict(data):
                self.current_filepath = filepath
                self.unsaved_changes = False
                self.command_history.clear()
                self.transit_curve_pick = None
                self._add_status_message(f"加载成功: {filepath.name}", "success")
            else:
                self._add_status_message("加载失败: 数据格式错误", "error")
        except Exception as e:
            self._add_status_message(f"加载失败: {e}", "error")
    
    def _new_file(self):
        """新建文件"""
        if self.unsaved_changes:
            # 简单提示，实际可以添加确认对话框
            print("有未保存的更改")
        
        self.editor_data = EditorMapDataNav6()
        self.current_filepath = None
        self.unsaved_changes = False
        self.command_history.clear()
        self.transit_curve_pick = None
        self._add_status_message("新建地图")
    
    def _load_preset_map(self, map_type: str):
        """Navigation6 不再从随机房间生成器加载；请使用 JSON 或新建。"""
        self._add_status_message("Navigation6 请用「加载」打开 JSON 地图或使用新建", "warning")
    
    def _update(self):
        """更新状态"""
        # 清理过期的状态消息
        if len(self.status_messages) > 5:
            self.status_messages.pop(0)
    
    def _draw(self):
        """绘制界面"""
        self.screen.fill(BaseConfig.COLOR_BG)
        
        # 绘制左侧工具栏
        self._draw_toolbar()
        
        # 绘制画布
        self._draw_canvas()
        
        # 绘制右侧属性面板
        self._draw_properties_panel()
        
        # 绘制状态栏
        self._draw_status_bar()
    
    def _draw_toolbar(self):
        """绘制左侧工具栏"""
        rect = EditorLayout.PANEL_LEFT_RECT
        self.renderer.draw_panel(rect, "工具")
        
        y = rect.y + 60
        button_height = EditorLayout.TOOL_BUTTON_SIZE + EditorLayout.TOOL_BUTTON_MARGIN
        
        # 绘制工具按钮
        for tool in ToolType:
            btn_rect = pygame.Rect(rect.x + 10, y, rect.width - 20, EditorLayout.TOOL_BUTTON_SIZE)
            
            # 按钮颜色
            if tool == self.current_tool:
                color = EditorColors.TOOL_ACTIVE
                border_color = EditorColors.BUTTON_BORDER_ACTIVE
            else:
                color = EditorColors.TOOL_NORMAL
                border_color = EditorColors.BUTTON_BORDER
            
            pygame.draw.rect(self.screen, color, btn_rect, border_radius=5)
            pygame.draw.rect(self.screen, border_color, btn_rect, 2, border_radius=5)
            
            # 按钮文本
            text = TOOL_CONFIGS[tool]['name']
            text_surf = self.font_sm.render(text, True, EditorColors.TOOL_TEXT)
            text_x = btn_rect.x + (btn_rect.width - text_surf.get_width()) // 2
            text_y = btn_rect.y + (btn_rect.height - text_surf.get_height()) // 2
            self.screen.blit(text_surf, (text_x, text_y))
            
            # 快捷键提示
            shortcut = TOOL_CONFIGS[tool]['shortcut']
            shortcut_surf = self.font_sm.render(shortcut, True, EditorColors.TOOL_SHORTCUT)
            self.screen.blit(shortcut_surf, (btn_rect.right - shortcut_surf.get_width() - 5, btn_rect.y + 2))
            
            y += button_height
        
        if self.current_tool in _TRANSIT_EDIT_TOOLS:
            y += 8
            k = self.editor_data.transit_edit_kind
            label_surf = self.font_sm.render(f"线路 [{k}]", True, EditorColors.TOOL_TEXT)
            self.screen.blit(label_surf, (rect.x + 10, y))
            y += 22
            line_btn_h = 26
            kl = self.editor_data.nav6_transit[k]
            for i in range(len(kl)):
                btn_rect = pygame.Rect(rect.x + 10, y, rect.width - 20, line_btn_h)
                if i == self.editor_data.current_subway_line_index:
                    pygame.draw.rect(self.screen, EditorColors.TOOL_ACTIVE, btn_rect, border_radius=4)
                else:
                    pygame.draw.rect(self.screen, EditorColors.TOOL_NORMAL, btn_rect, border_radius=4)
                pygame.draw.rect(self.screen, EditorColors.BUTTON_BORDER, btn_rect, 1, border_radius=4)
                txt = self.font_sm.render(f"线路 {i + 1}", True, EditorColors.TOOL_TEXT)
                self.screen.blit(txt, (btn_rect.x + 6, btn_rect.y + (line_btn_h - txt.get_height()) // 2))
                y += line_btn_h + 2
            add_rect = pygame.Rect(rect.x + 10, y, rect.width - 20, line_btn_h)
            pygame.draw.rect(self.screen, EditorColors.TOOL_NORMAL, add_rect, border_radius=4)
            pygame.draw.rect(self.screen, EditorColors.BUTTON_BORDER, add_rect, 1, border_radius=4)
            add_txt = self.font_sm.render("+ 新建线路", True, EditorColors.TOOL_SHORTCUT)
            self.screen.blit(add_txt, (add_rect.x + 6, add_rect.y + (line_btn_h - add_txt.get_height()) // 2))
            y += line_btn_h + 2
            if len(kl) > 1:
                del_rect = pygame.Rect(rect.x + 10, y, rect.width - 20, line_btn_h)
                pygame.draw.rect(self.screen, EditorColors.TOOL_NORMAL, del_rect, border_radius=4)
                pygame.draw.rect(self.screen, EditorColors.VALIDATION_ERROR, del_rect, 1, border_radius=4)
                del_txt = self.font_sm.render("删除当前线路", True, EditorColors.VALIDATION_ERROR)
                self.screen.blit(del_txt, (del_rect.x + 6, del_rect.y + (line_btn_h - del_txt.get_height()) // 2))
                y += line_btn_h + 2
            y += 8
        else:
            y += 2
        
        # 绘制操作按钮
        y += 10
        op_buttons = [
            ("保存", "Ctrl+S"),
            ("加载", "Ctrl+O"),
            ("新建", "Ctrl+N"),
            ("撤销", "Ctrl+Z"),
            ("重做", "Ctrl+Y"),
        ]
        
        for text, shortcut in op_buttons:
            btn_rect = pygame.Rect(rect.x + 10, y, rect.width - 20, 30)
            pygame.draw.rect(self.screen, EditorColors.TOOL_NORMAL, btn_rect, border_radius=5)
            pygame.draw.rect(self.screen, EditorColors.BUTTON_BORDER, btn_rect, 1, border_radius=5)
            
            text_surf = self.font_sm.render(text, True, EditorColors.TOOL_TEXT)
            self.screen.blit(text_surf, (btn_rect.x + 5, btn_rect.y + 5))
            
            shortcut_surf = self.font_sm.render(shortcut, True, EditorColors.TOOL_SHORTCUT)
            self.screen.blit(shortcut_surf, (btn_rect.right - shortcut_surf.get_width() - 5, btn_rect.y + 5))
            
            y += 35
    
    def _draw_canvas(self):
        """绘制画布"""
        canvas_rect = EditorLayout.CANVAS_RECT
        pygame.draw.rect(self.screen, (250, 250, 250), canvas_rect)
        pygame.draw.rect(self.screen, EditorColors.DIVIDER_LINE, canvas_rect, 2)
        
        # 计算地图边界
        if self.editor_data.rooms or self.editor_data.single_cells or self.editor_data.subway_lines:
            min_x, max_x, min_y, max_y = self.editor_data.calculate_map_bounds()
            
            for rid, room in self.editor_data.rooms.items():
                self._draw_room(room, canvas_rect)
            
            for (gx, gy) in self.editor_data.single_cells:
                self._draw_single_cell(gx, gy, canvas_rect)
            
            for (gx, gy) in self.editor_data.obstacle_map.keys():
                self._draw_obstacle(gx, gy, canvas_rect)
            
            if self.editor_data.rooms:
                self._draw_door_lines(canvas_rect)
            
            self._draw_subway_path(canvas_rect)
            self._draw_subway_path_arrows(canvas_rect)
            self._draw_transit_curve_highlight(canvas_rect)

            for entrance, exit_pos in self.editor_data.portal_pairs:
                self._draw_portal(entrance[0], entrance[1], canvas_rect, "S")
                self._draw_portal(exit_pos[0], exit_pos[1], canvas_rect, "E")
            
            # 绘制传送门入口（临时状态）
            if self.editor_data.portal_entrance:
                self._draw_portal_entrance(
                    self.editor_data.portal_entrance[0],
                    self.editor_data.portal_entrance[1],
                    canvas_rect
                )
            
            # 绘制门和墙（仅墙，门用门线表示）
            for rid, room in self.editor_data.rooms.items():
                self._draw_doors_and_walls(room, canvas_rect)
            # 绘制单格四边墙与门（单格性质同大房间的一格，四边默认墙，门可打开）
            self._draw_single_cell_edges(canvas_rect)
            
            # 绘制起始点和目标点
            if self.editor_data.start_pos:
                self._draw_start_point(self.editor_data.start_pos[0], self.editor_data.start_pos[1], canvas_rect)
            if self.editor_data.target_pos:
                self._draw_target_point(self.editor_data.target_pos[0], self.editor_data.target_pos[1], canvas_rect)
            
            # 绘制选中房间
            for rid in self.editor_data.selected_room_ids:
                room = self.editor_data.rooms.get(rid)
                if room:
                    self._draw_selection(room, canvas_rect)
    
    def _draw_room(self, room: 'Room', canvas_rect: pygame.Rect):
        """绘制房间"""
        lx, ly = room.logical_pos
        gs = EditorLayout.GRID_SIZE
        
        # 房间背景
        room_rect = pygame.Rect(
            canvas_rect.x + self.canvas_offset_x + lx * 3 * gs,
            canvas_rect.y + self.canvas_offset_y + ly * 3 * gs,
            3 * gs,
            3 * gs
        )
        
        bg_color = BaseConfig.COLOR_ROOM_BG
        if room.is_target:
            bg_color = (255, 200, 200)  # 目标房间浅红色
        
        pygame.draw.rect(self.screen, bg_color, room_rect)
        pygame.draw.rect(self.screen, EditorColors.DIVIDER_LINE, room_rect, 1)
        
        # 绘制房间内的格子
        for dx in range(3):
            for dy in range(3):
                gx, gy = lx * 3 + dx, ly * 3 + dy
                cell_rect = pygame.Rect(
                    canvas_rect.x + self.canvas_offset_x + gx * gs,
                    canvas_rect.y + self.canvas_offset_y + gy * gs,
                    gs,
                    gs
                )
                pygame.draw.rect(self.screen, (240, 245, 250), cell_rect)
                pygame.draw.rect(self.screen, EditorColors.GRID_LINE, cell_rect, 1)
    
    def _draw_obstacle(self, gx: int, gy: int, canvas_rect: pygame.Rect):
        """绘制障碍物"""
        gs = EditorLayout.GRID_SIZE
        cell_rect = pygame.Rect(
            canvas_rect.x + self.canvas_offset_x + gx * gs,
            canvas_rect.y + self.canvas_offset_y + gy * gs,
            gs,
            gs
        )
        pygame.draw.rect(self.screen, EditorColors.COLOR_OBSTACLE, cell_rect)

    def _draw_single_cell(self, gx: int, gy: int, canvas_rect: pygame.Rect):
        """绘制单个可行走格"""
        gs = EditorLayout.GRID_SIZE
        cell_rect = pygame.Rect(
            canvas_rect.x + self.canvas_offset_x + gx * gs,
            canvas_rect.y + self.canvas_offset_y + gy * gs,
            gs,
            gs
        )
        pygame.draw.rect(self.screen, EditorColors.COLOR_SINGLE_CELL, cell_rect)
        pygame.draw.rect(self.screen, EditorColors.GRID_LINE, cell_rect, 1)

    def _draw_single_cell_edges(self, canvas_rect: pygame.Rect):
        """绘制单格四边：统一画墙；门线已用黄色连线表示。"""
        gs = EditorLayout.GRID_SIZE
        wall_thickness = 3
        for (gx, gy) in self.editor_data.single_cells:
            cx = canvas_rect.x + self.canvas_offset_x + gx * gs
            cy = canvas_rect.y + self.canvas_offset_y + gy * gs
            pygame.draw.line(self.screen, EditorColors.COLOR_WALL, (cx, cy), (cx + gs, cy), wall_thickness)
            pygame.draw.line(self.screen, EditorColors.COLOR_WALL, (cx, cy + gs), (cx + gs, cy + gs), wall_thickness)
            pygame.draw.line(self.screen, EditorColors.COLOR_WALL, (cx, cy), (cx, cy + gs), wall_thickness)
            pygame.draw.line(self.screen, EditorColors.COLOR_WALL, (cx + gs, cy), (cx + gs, cy + gs), wall_thickness)

    @staticmethod
    def _draw_arrow_head(screen: pygame.Surface, sx1: float, sy1: float, sx2: float, sy2: float,
                         color: tuple, arrow_len: int = 10, arrow_hw: int = 5, at_midpoint: bool = False) -> None:
        """沿 (sx1,sy1)->(sx2,sy2) 方向绘制箭头。at_midpoint=True 时箭头画在线段中点，否则在终点。"""
        dx = sx2 - sx1
        dy = sy2 - sy1
        length = (dx * dx + dy * dy) ** 0.5
        if length < 1e-6:
            return
        ux = dx / length
        uy = dy / length
        if at_midpoint:
            tip = ((sx1 + sx2) / 2, (sy1 + sy2) / 2)
        else:
            tip = (sx2, sy2)
        base_center_x = tip[0] - ux * arrow_len
        base_center_y = tip[1] - uy * arrow_len
        base_left = (base_center_x - uy * arrow_hw, base_center_y + ux * arrow_hw)
        base_right = (base_center_x + uy * arrow_hw, base_center_y - ux * arrow_hw)
        pygame.draw.polygon(screen, color, [tip, base_left, base_right])

    # 线路可视化：用二次贝塞尔近似曲线，减轻多线重叠；不改变底层网格 path 数据。
    _TRANSIT_CURVE_MIN_LEN = 8.0
    _TRANSIT_CURVE_STEPS_MAX = 28
    _TRANSIT_CURVE_STEPS_MIN = 10

    @classmethod
    def _transit_bezier_control(
        cls,
        ax: float,
        ay: float,
        bx: float,
        by: float,
        line_idx: int,
        seg_idx: int,
        manual_bias: float = 0.0,
    ) -> Tuple[float, float]:
        """线段中点的法向偏移作为二次贝塞尔控制点。manual_bias=0 为自动；非 0 时符号=弯向，绝对值≈强度倍数。"""
        mx, my = (ax + bx) * 0.5, (ay + by) * 0.5
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy)
        if L < 1e-6:
            return mx, my
        nx, ny = -dy / L, dx / L
        base_strength = min(max(L * 0.36, 5.0), 24.0)
        auto_sign = 1.0 if (seg_idx + line_idx) % 2 == 0 else -1.0
        if abs(manual_bias) < 1e-9:
            sign = auto_sign
            strength = base_strength
        else:
            sign = 1.0 if manual_bias > 0 else -1.0
            mag = min(3.5, max(0.2, abs(manual_bias)))
            strength = base_strength * mag
        return mx + sign * strength * nx, my + sign * strength * ny

    @classmethod
    def _sample_quadratic_bezier(
        cls,
        p0: Tuple[float, float],
        pc: Tuple[float, float],
        p1: Tuple[float, float],
        steps: int,
    ) -> List[Tuple[float, float]]:
        out: List[Tuple[float, float]] = []
        for i in range(steps + 1):
            t = i / steps
            om = 1.0 - t
            x = om * om * p0[0] + 2.0 * om * t * pc[0] + t * t * p1[0]
            y = om * om * p0[1] + 2.0 * om * t * pc[1] + t * t * p1[1]
            out.append((x, y))
        return out

    @classmethod
    def _transit_segment_polyline(
        cls,
        ax: float,
        ay: float,
        bx: float,
        by: float,
        line_idx: int,
        seg_idx: int,
        manual_bias: float = 0.0,
        force_straight: bool = False,
    ) -> List[Tuple[float, float]]:
        if force_straight:
            return [(ax, ay), (bx, by)]
        L = math.hypot(bx - ax, by - ay)
        if L < cls._TRANSIT_CURVE_MIN_LEN:
            return [(ax, ay), (bx, by)]
        cx, cy = cls._transit_bezier_control(ax, ay, bx, by, line_idx, seg_idx, manual_bias)
        n = int(L / 5.0)
        steps = max(cls._TRANSIT_CURVE_STEPS_MIN, min(cls._TRANSIT_CURVE_STEPS_MAX, n))
        return cls._sample_quadratic_bezier((ax, ay), (cx, cy), (bx, by), steps)

    @classmethod
    def _transit_bezier_tangent_at_mid(
        cls,
        ax: float,
        ay: float,
        bx: float,
        by: float,
        cx: float,
        cy: float,
    ) -> Tuple[float, float, float, float]:
        """t=0.5 处 (px,py) 与单位切向 (ux,uy)。"""
        t = 0.5
        om = 1.0 - t
        px = om * om * ax + 2.0 * om * t * cx + t * t * bx
        py = om * om * ay + 2.0 * om * t * cy + t * t * by
        tx = 2.0 * om * (cx - ax) + 2.0 * t * (bx - cx)
        ty = 2.0 * om * (cy - ay) + 2.0 * t * (by - cy)
        tlen = math.hypot(tx, ty)
        if tlen < 1e-6:
            return px, py, 1.0, 0.0
        return px, py, tx / tlen, ty / tlen
    
    def _transit_line_color(self, line: dict) -> Tuple[int, int, int]:
        kind = line.get("kind", "metro")
        if kind == "bus":
            return EditorColors.COLOR_BUS_LINE
        if kind == "light_rail":
            return EditorColors.COLOR_LIGHT_RAIL_LINE
        return EditorColors.COLOR_METRO_LINE

    def _draw_subway_path(self, canvas_rect: pygame.Rect):
        """绘制公交(蓝)/地铁(黄)/轻轨(绿)路径与站点；当前编辑类别下的当前线略粗。"""
        gs = EditorLayout.GRID_SIZE
        cur_flat = self.editor_data._kind_line_to_flat_index(
            self.editor_data.transit_edit_kind,
            self.editor_data.current_subway_line_index,
        )
        for line_idx, line in enumerate(self.editor_data.subway_lines):
            path = line.get("path", [])
            if len(path) < 2:
                continue
            points = []
            for gx, gy in path:
                x = canvas_rect.x + self.canvas_offset_x + gx * gs + gs // 2
                y = canvas_rect.y + self.canvas_offset_y + gy * gs + gs // 2
                points.append((x, y))
            color = self._transit_line_color(line)
            width = 5 if line_idx == cur_flat else 4
            sc = line.get("segment_curve") or []
            st = line.get("segment_straight") or []
            for i in range(len(points) - 1):
                ax, ay = points[i]
                bx, by = points[i + 1]
                bias = float(sc[i]) if i < len(sc) else 0.0
                straight = bool(st[i]) if i < len(st) else False
                poly = self._transit_segment_polyline(
                    ax, ay, bx, by, line_idx, i, bias, force_straight=straight
                )
                if len(poly) >= 2:
                    pygame.draw.lines(self.screen, color, False, poly, width)
        hubs: Dict[Tuple[int, int], List[Tuple[int, int, int]]] = defaultdict(list)
        for line in self.editor_data.subway_lines:
            color = self._transit_line_color(line)
            for (gx, gy) in line.get("stations", set()):
                hubs[(gx, gy)].append(color)
        for (gx, gy), colors in hubs.items():
            self._draw_subway_station_hub(gx, gy, canvas_rect, colors)

    def _draw_subway_path_arrows(self, canvas_rect: pygame.Rect):
        """路径方向箭头。"""
        gs = EditorLayout.GRID_SIZE
        for line_idx, line in enumerate(self.editor_data.subway_lines):
            path = line.get("path", [])
            if len(path) < 2:
                continue
            points = []
            for gx, gy in path:
                x = canvas_rect.x + self.canvas_offset_x + gx * gs + gs // 2
                y = canvas_rect.y + self.canvas_offset_y + gy * gs + gs // 2
                points.append((x, y))
            color_line = self._transit_line_color(line)
            mode = str(line.get("kind", "metro"))
            draw_both = mode in ("bus", "light_rail")
            sc = line.get("segment_curve") or []
            st = line.get("segment_straight") or []
            for i in range(len(points) - 1):
                ax, ay = points[i]
                bx, by = points[i + 1]
                bias = float(sc[i]) if i < len(sc) else 0.0
                straight = bool(st[i]) if i < len(st) else False
                L = math.hypot(bx - ax, by - ay)
                if straight or L < self._TRANSIT_CURVE_MIN_LEN:
                    self._draw_arrow_head(
                        self.screen, ax, ay, bx, by,
                        color_line, arrow_len=12, arrow_hw=6, at_midpoint=True,
                    )
                    if draw_both:
                        self._draw_arrow_head(
                            self.screen, bx, by, ax, ay,
                            color_line, arrow_len=12, arrow_hw=6, at_midpoint=True,
                        )
                    continue
                cx, cy = self._transit_bezier_control(ax, ay, bx, by, line_idx, i, bias)
                px, py, ux, uy = self._transit_bezier_tangent_at_mid(ax, ay, bx, by, cx, cy)
                tip_x, tip_y = px + ux * 5.0, py + uy * 5.0
                base_x, base_y = px - ux * 12.0, py - uy * 12.0
                self._draw_arrow_head(
                    self.screen, base_x, base_y, tip_x, tip_y,
                    color_line, arrow_len=12, arrow_hw=6, at_midpoint=False,
                )
                if draw_both:
                    self._draw_arrow_head(
                        self.screen, tip_x, tip_y, base_x, base_y,
                        color_line, arrow_len=12, arrow_hw=6, at_midpoint=False,
                    )

    def _draw_transit_curve_highlight(self, canvas_rect: pygame.Rect) -> None:
        """弧度工具下高亮当前选中的路径段。"""
        if self.current_tool != ToolType.TRANSIT_CURVE or not self.transit_curve_pick:
            return
        li, si = self.transit_curve_pick
        if li < 0 or li >= len(self.editor_data.subway_lines):
            return
        line = self.editor_data.subway_lines[li]
        path = line.get("path", [])
        if si < 0 or si >= len(path) - 1:
            return
        gs = EditorLayout.GRID_SIZE
        gx0, gy0 = path[si]
        gx1, gy1 = path[si + 1]
        ax = canvas_rect.x + self.canvas_offset_x + gx0 * gs + gs // 2
        ay = canvas_rect.y + self.canvas_offset_y + gy0 * gs + gs // 2
        bx = canvas_rect.x + self.canvas_offset_x + gx1 * gs + gs // 2
        by = canvas_rect.y + self.canvas_offset_y + gy1 * gs + gs // 2
        sc = line.get("segment_curve") or []
        st = line.get("segment_straight") or []
        bias = float(sc[si]) if si < len(sc) else 0.0
        straight = bool(st[si]) if si < len(st) else False
        poly = self._transit_segment_polyline(
            float(ax), float(ay), float(bx), float(by), li, si, bias, force_straight=straight
        )
        if len(poly) >= 2:
            pygame.draw.lines(self.screen, (255, 255, 200), False, poly, 7)

    def _draw_subway_station_hub(
        self, gx: int, gy: int, canvas_rect: pygame.Rect, stripe_colors: List[Tuple[int, int, int]]
    ) -> None:
        """绘制站点；同一格多条线路时用竖向分色条表示换乘。"""
        gs = EditorLayout.GRID_SIZE
        cx = canvas_rect.x + self.canvas_offset_x + gx * gs + gs // 2
        cy = canvas_rect.y + self.canvas_offset_y + gy * gs + gs // 2
        station_size = 20
        left = cx - station_size // 2
        top = cy - station_size // 2
        full = pygame.Rect(left, top, station_size, station_size)
        if not stripe_colors:
            return
        if len(stripe_colors) == 1:
            pygame.draw.rect(self.screen, EditorColors.COLOR_SUBWAY_STATION, full)
            pygame.draw.rect(self.screen, stripe_colors[0], full, 2)
            return
        acc = left
        n = len(stripe_colors)
        for i, c in enumerate(stripe_colors):
            seg_right = left + int((i + 1) * station_size / n)
            seg = pygame.Rect(acc, top, max(1, seg_right - acc), station_size)
            pygame.draw.rect(self.screen, c, seg)
            acc = seg_right
        pygame.draw.rect(self.screen, (35, 40, 48), full, 2)
    
    def _draw_portal(self, gx: int, gy: int, canvas_rect: pygame.Rect, label: Optional[str] = None):
        """绘制传送门，label 为 'S'（入口）或 'E'（出口）"""
        gs = EditorLayout.GRID_SIZE
        cx = canvas_rect.x + self.canvas_offset_x + gx * gs + gs // 2
        cy = canvas_rect.y + self.canvas_offset_y + gy * gs + gs // 2
        
        pygame.draw.circle(self.screen, EditorColors.COLOR_PORTAL, (cx, cy), 12)
        pygame.draw.circle(self.screen, (0, 0, 0), (cx, cy), 12, 2)
        if label:
            font = BaseConfig.get_font(12)
            text_surf = font.render(label, True, (0, 0, 0))
            text_rect = text_surf.get_rect(center=(cx, cy))
            self.screen.blit(text_surf, text_rect)
    
    def _draw_portal_entrance(self, gx: int, gy: int, canvas_rect: pygame.Rect):
        """绘制传送门入口（临时状态）"""
        gs = EditorLayout.GRID_SIZE
        cx = canvas_rect.x + self.canvas_offset_x + gx * gs + gs // 2
        cy = canvas_rect.y + self.canvas_offset_y + gy * gs + gs // 2
        
        # 半透明圆圈
        surface = pygame.Surface((24, 24), pygame.SRCALPHA)
        pygame.draw.circle(surface, (*EditorColors.COLOR_PORTAL, 128), (12, 12), 12)
        self.screen.blit(surface, (cx - 12, cy - 12))
        pygame.draw.circle(self.screen, EditorColors.COLOR_PORTAL, (cx, cy), 12, 2)
    
    def _draw_door_lines(self, canvas_rect: pygame.Rect):
        """绘制门线：房间中心→目标房间/单格中心、单格中心→目标房间/单格中心的黄色连线。"""
        gs = EditorLayout.GRID_SIZE
        line_width = 4
        drawn_room = set()
        drawn_cell = set()
        for rid, room in self.editor_data.rooms.items():
            if room.is_obstacle:
                continue
            lx, ly = room.logical_pos
            px0 = canvas_rect.x + self.canvas_offset_x + (lx * 3 + 1) * gs + gs // 2
            py0 = canvas_rect.y + self.canvas_offset_y + (ly * 3 + 1) * gs + gs // 2
            for direction, target_rids in room.doors.items():
                for target_rid in (target_rids if isinstance(target_rids, list) else [target_rids]):
                    if target_rid not in self.editor_data.rooms:
                        continue
                    key = (min(rid, target_rid), max(rid, target_rid))
                    if key in drawn_room:
                        continue
                    drawn_room.add(key)
                    target_room = self.editor_data.rooms[target_rid]
                    if target_room.is_obstacle:
                        continue
                    lx2, ly2 = target_room.logical_pos
                    px1 = canvas_rect.x + self.canvas_offset_x + (lx2 * 3 + 1) * gs + gs // 2
                    py1 = canvas_rect.y + self.canvas_offset_y + (ly2 * 3 + 1) * gs + gs // 2
                    pygame.draw.line(self.screen, EditorColors.COLOR_DOOR_LINE, (px0, py0), (px1, py1), line_width)
        for (gx, gy), dirs in self.editor_data.single_cell_doors.items():
            if not isinstance(dirs, dict):
                continue
            px0 = canvas_rect.x + self.canvas_offset_x + gx * gs + gs // 2
            py0 = canvas_rect.y + self.canvas_offset_y + gy * gs + gs // 2
            for _direction, target in dirs.items():
                targets = target if isinstance(target, list) else [target]
                for t in targets:
                    if isinstance(t, int):
                        r = self.editor_data.rooms.get(t)
                        if not r or r.is_obstacle:
                            continue
                        lx2, ly2 = r.logical_pos
                        px1 = canvas_rect.x + self.canvas_offset_x + (lx2 * 3 + 1) * gs + gs // 2
                        py1 = canvas_rect.y + self.canvas_offset_y + (ly2 * 3 + 1) * gs + gs // 2
                        pygame.draw.line(self.screen, EditorColors.COLOR_DOOR_LINE, (px0, py0), (px1, py1), line_width)
                    elif isinstance(t, tuple) and len(t) == 2:
                        gx2, gy2 = t
                        key = (min((gx, gy), (gx2, gy2)), max((gx, gy), (gx2, gy2)))
                        if key in drawn_cell:
                            continue
                        drawn_cell.add(key)
                        px1 = canvas_rect.x + self.canvas_offset_x + gx2 * gs + gs // 2
                        py1 = canvas_rect.y + self.canvas_offset_y + gy2 * gs + gs // 2
                        pygame.draw.line(self.screen, EditorColors.COLOR_DOOR_LINE, (px0, py0), (px1, py1), line_width)

    def _draw_doors_and_walls(self, room: 'Room', canvas_rect: pygame.Rect):
        """仅绘制房间四边墙；门已用门线（黄色连线）表示，不再在边上画门线段。"""
        lx, ly = room.logical_pos
        gs = EditorLayout.GRID_SIZE
        room_x = canvas_rect.x + self.canvas_offset_x + lx * 3 * gs
        room_y = canvas_rect.y + self.canvas_offset_y + ly * 3 * gs
        room_size = 3 * gs
        wall_thickness = 3
        # 四边统一画墙（不再按 door 开缺口）
        pygame.draw.line(self.screen, EditorColors.COLOR_WALL,
                         (room_x, room_y), (room_x + room_size, room_y), wall_thickness)
        pygame.draw.line(self.screen, EditorColors.COLOR_WALL,
                         (room_x, room_y + room_size), (room_x + room_size, room_y + room_size), wall_thickness)
        pygame.draw.line(self.screen, EditorColors.COLOR_WALL,
                         (room_x, room_y), (room_x, room_y + room_size), wall_thickness)
        pygame.draw.line(self.screen, EditorColors.COLOR_WALL,
                         (room_x + room_size, room_y), (room_x + room_size, room_y + room_size), wall_thickness)
    
    def _draw_start_point(self, gx: int, gy: int, canvas_rect: pygame.Rect):
        """绘制起始点"""
        gs = EditorLayout.GRID_SIZE
        cx = canvas_rect.x + self.canvas_offset_x + gx * gs + gs // 2
        cy = canvas_rect.y + self.canvas_offset_y + gy * gs + gs // 2
        
        pygame.draw.circle(self.screen, EditorColors.COLOR_START, (cx, cy), 10)
        pygame.draw.circle(self.screen, (0, 0, 0), (cx, cy), 10, 2)
    
    def _draw_target_point(self, gx: int, gy: int, canvas_rect: pygame.Rect):
        """绘制目标点"""
        gs = EditorLayout.GRID_SIZE
        cx = canvas_rect.x + self.canvas_offset_x + gx * gs + gs // 2
        cy = canvas_rect.y + self.canvas_offset_y + gy * gs + gs // 2
        
        pygame.draw.circle(self.screen, EditorColors.COLOR_TARGET, (cx, cy), 10)
        pygame.draw.circle(self.screen, (0, 0, 0), (cx, cy), 10, 2)
    
    def _draw_selection(self, room: 'Room', canvas_rect: pygame.Rect):
        """绘制选中房间"""
        lx, ly = room.logical_pos
        gs = EditorLayout.GRID_SIZE
        room_rect = pygame.Rect(
            canvas_rect.x + self.canvas_offset_x + lx * 3 * gs,
            canvas_rect.y + self.canvas_offset_y + ly * 3 * gs,
            3 * gs,
            3 * gs
        )
        
        # 半透明高亮
        surface = pygame.Surface((room_rect.width, room_rect.height), pygame.SRCALPHA)
        pygame.draw.rect(surface, EditorColors.SELECTION_HIGHLIGHT, (0, 0, room_rect.width, room_rect.height))
        self.screen.blit(surface, room_rect)
        
        # 边框
        pygame.draw.rect(self.screen, EditorColors.SELECTION_BORDER, room_rect, 3)
    
    def _draw_properties_panel(self):
        """绘制右侧属性面板"""
        rect = EditorLayout.PANEL_RIGHT_RECT
        self.renderer.draw_panel(rect, "属性")
        
        y = rect.y + 60
        
        # 地图信息
        self.renderer.draw_text("地图信息", (rect.x + 20, y), size='md', color=EditorColors.TOOL_TEXT)
        y += 30
        
        k = self.editor_data.transit_edit_kind
        kl = self.editor_data.nav6_transit.get(k, [])
        cur_line = kl[self.editor_data.current_subway_line_index] if kl else {}
        info_lines = [
            f"公交线: {len(self.editor_data.nav6_transit['bus'])} 条",
            f"地铁线: {len(self.editor_data.nav6_transit['metro'])} 条",
            f"轻轨线: {len(self.editor_data.nav6_transit['light_rail'])} 条",
            f"  当前编辑 [{k}] 路径点: {len(cur_line.get('path', []))}",
            f"  当前编辑 [{k}] 站点: {len(cur_line.get('stations', []))}",
            f"障碍物: {len(self.editor_data.obstacle_map)}",
            f"单格可行走: {len(self.editor_data.single_cells)}",
        ]
        
        for line in info_lines:
            self.renderer.draw_text(line, (rect.x + 20, y), size='sm', color=EditorColors.TOOL_TEXT)
            y += 22
        
        # 当前工具信息
        y += 20
        self.renderer.draw_text("当前工具", (rect.x + 20, y), size='md', color=EditorColors.TOOL_TEXT)
        y += 30
        
        tool_config = TOOL_CONFIGS[self.current_tool]
        self.renderer.draw_text(tool_config['name'], (rect.x + 20, y), size='sm', color=EditorColors.TOOL_ACTIVE)
        y += 22
        self.renderer.draw_text(tool_config['description'], (rect.x + 20, y), size='sm', color=EditorColors.TOOL_SHORTCUT)
        if self.current_tool == ToolType.TRANSIT_CURVE:
            y += 26
            for hint in (
                "点击路径段选中；在画布上滚轮调节。",
                "L：当前段改为直线；滚轮改弯会取消直线。",
                "TAB：在鼠标附近路径段间切换；Shift+TAB 反向。",
                "鼠标在画布外时 TAB 按全图顺序切换。",
                "正值/负值：向两侧弯曲，|值|越大越弯。",
                "右击或数字 0：该段恢复自动。[ / ] 微调。",
            ):
                self.renderer.draw_text(hint, (rect.x + 20, y), size='sm', color=EditorColors.TOOL_TEXT)
                y += 20
            if self.transit_curve_pick:
                fi, sj = self.transit_curve_pick
                vv = self.editor_data.get_segment_curve_value(fi, sj)
                if vv is not None:
                    st = self.editor_data.get_segment_straight(fi, sj)
                    st_lbl = "直线" if st else "曲线"
                    self.renderer.draw_text(
                        f"当前选中: 线#{fi} 段{sj} 弧度={vv:.2f}（{st_lbl}）",
                        (rect.x + 20, y),
                        size='sm',
                        color=EditorColors.STATUS_SUCCESS,
                    )

        # 选中房间信息
        if self.editor_data.selected_room_ids:
            y += 30
            self.renderer.draw_text("选中房间", (rect.x + 20, y), size='md', color=EditorColors.TOOL_TEXT)
            y += 25
            
            for rid in list(self.editor_data.selected_room_ids)[:3]:  # 最多显示3个
                room = self.editor_data.rooms.get(rid)
                if room:
                    lx, ly = room.logical_pos
                    self.renderer.draw_text(f"({lx}, {ly})", (rect.x + 20, y), size='sm', color=EditorColors.TOOL_TEXT)
                    y += 20
    
    def _draw_status_bar(self):
        """绘制状态栏"""
        rect = EditorLayout.STATUS_BAR_RECT
        pygame.draw.rect(self.screen, EditorColors.PANEL_LEFT_BG, rect)
        pygame.draw.line(self.screen, EditorColors.DIVIDER_LINE, (rect.x, rect.y), (rect.right, rect.y), 2)
        
        # 显示状态消息
        if self.status_messages:
            msg = self.status_messages[-1]
            text = msg.get('text', '')
            msg_type = msg.get('type', 'info')
            
            color = EditorColors.STATUS_INFO
            if msg_type == 'success':
                color = EditorColors.STATUS_SUCCESS
            elif msg_type == 'warning':
                color = EditorColors.STATUS_WARNING
            elif msg_type == 'error':
                color = EditorColors.STATUS_ERROR
            
            text_surf = self.font_sm.render(text, True, color)
            self.screen.blit(text_surf, (rect.x + 10, rect.y + 5))
        
        # 显示未保存提示
        if self.unsaved_changes:
            unsaved_text = "● 未保存"
            text_surf = self.font_sm.render(unsaved_text, True, EditorColors.STATUS_WARNING)
            self.screen.blit(text_surf, (rect.right - text_surf.get_width() - 10, rect.y + 5))
    
    def _add_status_message(self, text: str, msg_type: str = "info"):
        """添加状态消息"""
        self.status_messages.append({
            "text": text,
            "type": msg_type,
            "time": time.time()
        })


def main():
    """主函数"""
    editor = MapEditorNav6()
    editor.run()


if __name__ == "__main__":
    main()
