"""
Crafting 转化地图编辑器：3×3 九石；药水1/2 存 Q/A 正向边（直线），E/D 逆向由程序推导；药水3 为可拖拽控制点的二次贝塞尔曲线。
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pygame

from ..graph_moves import potion_backward_from_forward
from ..maps_crafting import built_in_potion_tables
from ..stone_images import StoneImageCache, blit_image_fit, collect_stone_asset_dirs
from ..stone_space import STONE_IDS
from ..transition_map_io_crafting import (
    TransitionMapData,
    load_transition_map,
    save_transition_map,
)

from .editor_commands import (
    CommandHistory,
    SetPotion3ControlOffsetCommand,
    SetPotionEdgeCommand,
)
from .editor_curve_geometry import potion3_sample_polyline, quadratic_bezier_control

try:
    import tkinter as tk
    from tkinter import filedialog
except ImportError:
    tk = None
    filedialog = None

SCREEN_W = 1100
SCREEN_H = 760
GRID_X = 40
GRID_Y = 88
# 格子略缩小；内边距与 blit padding 加大，宝石图在格内占比更小
CELL = 128
GAP = 8
PANEL_X = 460
CELL_IMAGE_INSET = 26
IMAGE_FIT_PADDING = 8
COLOR_BG = (32, 34, 42)
COLOR_GRID = (52, 56, 68)
COLOR_EDGE = (88, 94, 112)
COLOR_TEXT = (230, 234, 245)
COLOR_MUTED = (140, 150, 170)
POTION_COLORS = (
    (96, 200, 120),
    (240, 180, 80),
    (100, 170, 240),
)
P3_HANDLE_RADIUS = 11
P3_HANDLE_HIT = 16


def _crafting_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _font(size: int) -> pygame.font.Font:
    try:
        return pygame.font.SysFont("SimHei", size)
    except Exception:
        return pygame.font.SysFont("arial", size)


def _stone_cell_index(stone_id: str) -> int:
    for i, s in enumerate(STONE_IDS):
        if s == stone_id:
            return i
    return -1


def _cell_rect(i: int) -> pygame.Rect:
    r, c = i // 3, i % 3
    x = GRID_X + c * (CELL + GAP)
    y = GRID_Y + r * (CELL + GAP)
    return pygame.Rect(x, y, CELL, CELL)


def _cell_center(i: int) -> Tuple[int, int]:
    rect = _cell_rect(i)
    return rect.centerx, rect.centery


def _draw_potion12_directed_edge(
    surf: pygame.Surface,
    p0: Tuple[int, int],
    p1: Tuple[int, int],
    color: Tuple[int, int, int],
    width: int = 2,
    lateral: float = 0.0,
) -> None:
    """药水1/2：单向箭头 p0→p1；lateral 为垂直于连线方向的像素偏移，用于与逆向边错开。"""
    x0, y0 = p0
    x1, y1 = p1
    dx, dy = x1 - x0, y1 - y0
    dist = max(1.0, math.hypot(dx, dy))
    ux, uy = dx / dist, dy / dist
    px, py = -uy, ux
    ox, oy = px * lateral, py * lateral
    xa, ya = x0 + ox, y0 + oy
    xb, yb = x1 + ox, y1 + oy
    shorten = min(24.0, dist * 0.32)
    sx0 = int(xa + ux * shorten)
    sy0 = int(ya + uy * shorten)
    sx1 = int(xb - ux * shorten)
    sy1 = int(yb - uy * shorten)
    pygame.draw.line(surf, color, (sx0, sy0), (sx1, sy1), width)
    _draw_arrow_head(surf, (sx1, sy1), (ux, uy), color)


def _draw_arrow_head(
    surf: pygame.Surface,
    base: Tuple[int, int],
    direction: Tuple[float, float],
    color: Tuple[int, int, int],
) -> None:
    ux, uy = direction
    bx, by = base
    ah = 10
    px, py = -uy, ux
    ptip = (int(bx + ux * 8), int(by + uy * 8))
    left = (
        int(bx + px * ah * 0.5 + ux * 2),
        int(by + py * ah * 0.5 + uy * 2),
    )
    right = (
        int(bx - px * ah * 0.5 + ux * 2),
        int(by - py * ah * 0.5 + uy * 2),
    )
    pygame.draw.polygon(surf, color, [ptip, left, right])


def _draw_arrow_curved(
    surf: pygame.Surface,
    pts: List[Tuple[float, float]],
    color: Tuple[int, int, int],
    width: int = 2,
) -> None:
    if len(pts) < 2:
        return
    x0, y0 = pts[-2]
    x1, y1 = pts[-1]
    dx, dy = x1 - x0, y1 - y0
    dist = max(1.0, math.hypot(dx, dy))
    ux, uy = dx / dist, dy / dist
    shorten = min(28.0, dist * 0.35)
    sx = x1 - ux * shorten
    sy = y1 - uy * shorten
    trimmed: List[Tuple[int, int]] = [(int(p[0]), int(p[1])) for p in pts[:-1]]
    trimmed.append((int(sx), int(sy)))
    if len(trimmed) > 1:
        pygame.draw.lines(surf, color, False, trimmed, width)
    _draw_arrow_head(surf, (int(sx), int(sy)), (ux, uy), color)


class TransitionMapEditor:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("Crafting 转化地图编辑器")
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        self.clock = pygame.time.Clock()
        root = _crafting_root()
        self.crafting_root = root
        dirs = collect_stone_asset_dirs(root)
        self.img_cache = StoneImageCache(dirs)

        self.potions: List[Dict[str, str]] = [{}, {}, {}]
        self.potion3_control_offset: Dict[str, Tuple[float, float]] = {}
        self.map_id = "custom"
        self.description = ""
        self.current_file: Optional[str] = None
        self.current_potion = 0
        self.pending_src: Optional[str] = None
        self.show_all_arrows = True
        self.history = CommandHistory()
        self.running = True

        self._p3_drag: Optional[Dict[str, float]] = None
        """{src, hmx, hmy, orig_dx, orig_dy} 手柄相对鼠标的偏移与拖拽起点偏移。"""

        self._btn_rects: Dict[str, pygame.Rect] = {}
        self._init_button_layout()

    def _init_button_layout(self) -> None:
        x, y = PANEL_X, 80
        w, h, gap = 220, 36, 8
        keys = [
            "p1",
            "p2",
            "p3",
            "toggle",
            "tpl_a",
            "tpl_b",
            "new",
            "open",
            "save",
            "saveas",
        ]
        for key in keys:
            self._btn_rects[key] = pygame.Rect(x, y, w, h)
            y += h + gap

    def _draw_buttons(self) -> None:
        f = _font(16)
        labels = [
            ("p1", "当前：药水1 (数字键1)"),
            ("p2", "当前：药水2 (2)"),
            ("p3", "当前：药水3 (3) — 拖拽蓝色控制柄调曲线"),
            ("toggle", f"显示全部箭头 (A)：{'开' if self.show_all_arrows else '仅当前'}"),
            ("tpl_a", "模板：内置 map_a"),
            ("tpl_b", "模板：内置 map_b"),
            ("new", "新建 Ctrl+N"),
            ("open", "打开 Ctrl+O"),
            ("save", "保存 Ctrl+S"),
            ("saveas", "另存为…"),
        ]
        for key, text in labels:
            rect = self._btn_rects[key]
            on = (key == "p1" and self.current_potion == 0) or (
                key == "p2" and self.current_potion == 1
            ) or (key == "p3" and self.current_potion == 2)
            bg = (64, 110, 90) if on else (48, 52, 64)
            pygame.draw.rect(self.screen, bg, rect, border_radius=6)
            pygame.draw.rect(self.screen, COLOR_EDGE, rect, 1, border_radius=6)
            self.screen.blit(f.render(text, True, COLOR_TEXT), (rect.x + 10, rect.y + 8))

    def _hit_button(self, mx: int, my: int) -> Optional[str]:
        for key, rect in self._btn_rects.items():
            if rect.collidepoint(mx, my):
                return key
        return None

    def _stone_at(self, mx: int, my: int) -> Optional[str]:
        for i, sid in enumerate(STONE_IDS):
            if _cell_rect(i).collidepoint(mx, my):
                return sid
        return None

    def _p3_edge_polyline(self, src: str, dst: str) -> List[Tuple[float, float]]:
        i0 = _stone_cell_index(src)
        i1 = _stone_cell_index(dst)
        if i0 < 0 or i1 < 0:
            return []
        ax, ay = float(_cell_center(i0)[0]), float(_cell_center(i0)[1])
        bx, by = float(_cell_center(i1)[0]), float(_cell_center(i1)[1])
        seg_idx = i0 % 2
        ox, oy = self.potion3_control_offset.get(src, (0.0, 0.0))
        return potion3_sample_polyline(ax, ay, bx, by, seg_idx, ox, oy)

    def _p3_handle_position(self, src: str, dst: str) -> Tuple[float, float]:
        i0 = _stone_cell_index(src)
        i1 = _stone_cell_index(dst)
        if i0 < 0 or i1 < 0:
            return (0.0, 0.0)
        ax, ay = float(_cell_center(i0)[0]), float(_cell_center(i0)[1])
        bx, by = float(_cell_center(i1)[0]), float(_cell_center(i1)[1])
        seg_idx = i0 % 2
        acx, acy = quadratic_bezier_control(ax, ay, bx, by, seg_idx, 0.0)
        ox, oy = self.potion3_control_offset.get(src, (0.0, 0.0))
        return acx + ox, acy + oy

    def _hit_p3_handle(self, mx: float, my: float) -> Optional[str]:
        if not (self.show_all_arrows or self.current_potion == 2):
            return None
        for src, dst in self.potions[2].items():
            hx, hy = self._p3_handle_position(src, dst)
            if math.hypot(mx - hx, my - hy) <= P3_HANDLE_HIT:
                return src
        return None

    def _apply_edge(self, src: str, dst: str) -> None:
        if src == dst:
            return
        old = self.potions[self.current_potion].get(src)
        if old == dst:
            return
        if self.current_potion == 2 and old != dst:
            self.potion3_control_offset.pop(src, None)
        cmd = SetPotionEdgeCommand(
            self.potions, self.current_potion, src, old, dst
        )
        self.history.execute_command(cmd)

    def _clear_edge(self, src: str) -> None:
        old = self.potions[self.current_potion].get(src)
        if old is None:
            return
        if self.current_potion == 2:
            self.potion3_control_offset.pop(src, None)
        cmd = SetPotionEdgeCommand(
            self.potions, self.current_potion, src, old, None
        )
        self.history.execute_command(cmd)

    def _load_template(self, map_id: str) -> None:
        p1f, _p1r, p2f, _p2r, p3 = built_in_potion_tables(map_id)
        self.potions = [
            dict(p1f),
            dict(p2f),
            dict(p3),
        ]
        self.potion3_control_offset = {}
        self.map_id = map_id
        self.description = f"自内置 {map_id} 生成"
        self.current_file = None
        self.history.clear()
        self.pending_src = None
        self._p3_drag = None

    def _new(self) -> None:
        self.potions = [{}, {}, {}]
        self.potion3_control_offset = {}
        self.map_id = "custom"
        self.description = ""
        self.current_file = None
        self.history.clear()
        self.pending_src = None
        self._p3_drag = None

    def _open_dialog(self) -> None:
        if tk is None or filedialog is None:
            return
        root = tk.Tk()
        root.withdraw()
        path = filedialog.askopenfilename(
            title="打开转化地图",
            filetypes=[("JSON", "*.json"), ("All", "*.*")],
            initialdir=str(self.crafting_root / "data" / "maps"),
        )
        root.destroy()
        if not path:
            return
        tm = load_transition_map(path)
        self.potions = [dict(tm.potion1), dict(tm.potion2), dict(tm.potion3)]
        self.potion3_control_offset = dict(tm.potion3_control_offset)
        self.map_id = tm.map_id
        self.description = tm.description
        self.current_file = path
        self.history.clear()
        self.pending_src = None
        self._p3_drag = None

    def _save_dialog(self) -> None:
        if tk is None or filedialog is None:
            return
        root = tk.Tk()
        root.withdraw()
        path = filedialog.asksaveasfilename(
            title="另存为转化地图",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialdir=str(self.crafting_root / "data" / "maps"),
        )
        root.destroy()
        if not path:
            return
        self._write_file(path)

    def _write_file(self, path: str) -> None:
        data = TransitionMapData(
            map_id=self.map_id,
            description=self.description,
            potion1=dict(self.potions[0]),
            potion2=dict(self.potions[1]),
            potion3=dict(self.potions[2]),
            source_path=path,
            potion3_control_offset=dict(self.potion3_control_offset),
        )
        save_transition_map(path, data)
        self.current_file = path

    def _save(self) -> None:
        if self.current_file:
            self._write_file(self.current_file)
        else:
            self._save_dialog()

    def _draw_grid(self) -> None:
        t_f = _font(20)
        self.screen.blit(
            t_f.render(
                "九石阵｜药水1/2：先点源再点目标，存 Q/A 正向；外侧细线为 E/D 逆向（自动推算）",
                True,
                COLOR_TEXT,
            ),
            (GRID_X, 28),
        )
        self.screen.blit(
            t_f.render(
                "每条正向边仍是「源→目标」一步；可依次添加 1→2、2→3 等，同一目标石只能有一条入边（否则无法定义 E/D）",
                True,
                COLOR_MUTED,
            ),
            (GRID_X, 52),
        )
        f_small = _font(14)
        for i, sid in enumerate(STONE_IDS):
            rect = _cell_rect(i)
            pygame.draw.rect(self.screen, COLOR_GRID, rect, border_radius=10)
            pygame.draw.rect(self.screen, COLOR_EDGE, rect, 2, border_radius=10)
            inner = rect.inflate(-CELL_IMAGE_INSET, -CELL_IMAGE_INSET)
            img = self.img_cache.get(sid)
            if img is not None:
                blit_image_fit(self.screen, img, inner, padding=IMAGE_FIT_PADDING)
            else:
                pygame.draw.rect(self.screen, (40, 44, 54), inner, border_radius=6)
            self.screen.blit(f_small.render(sid, True, COLOR_MUTED), (rect.x + 8, rect.y + 6))
            if self.pending_src == sid:
                pygame.draw.rect(self.screen, (200, 200, 100), rect, 3, border_radius=10)

        potion_range = (
            range(3) if self.show_all_arrows else range(self.current_potion, self.current_potion + 1)
        )
        for pi in potion_range:
            col = POTION_COLORS[pi]
            if pi == 2:
                for src, dst in self.potions[pi].items():
                    i0 = _stone_cell_index(src)
                    i1 = _stone_cell_index(dst)
                    if i0 < 0 or i1 < 0:
                        continue
                    pts = self._p3_edge_polyline(src, dst)
                    if len(pts) >= 2:
                        _draw_arrow_curved(self.screen, pts, col, 2)
            else:
                fwd = self.potions[pi]
                try:
                    rev = potion_backward_from_forward(fwd)
                except ValueError:
                    rev = {}
                dim = tuple(max(0, int(c * 0.55)) for c in col)
                for src, dst in fwd.items():
                    i0 = _stone_cell_index(src)
                    i1 = _stone_cell_index(dst)
                    if i0 < 0 or i1 < 0:
                        continue
                    _draw_potion12_directed_edge(
                        self.screen,
                        _cell_center(i0),
                        _cell_center(i1),
                        col,
                        2,
                        lateral=5.0,
                    )
                for rdst, rsrc in rev.items():
                    j0 = _stone_cell_index(rdst)
                    j1 = _stone_cell_index(rsrc)
                    if j0 < 0 or j1 < 0:
                        continue
                    _draw_potion12_directed_edge(
                        self.screen,
                        _cell_center(j0),
                        _cell_center(j1),
                        dim,
                        1,
                        lateral=-5.0,
                    )

        show_handles = self.show_all_arrows or self.current_potion == 2
        if show_handles:
            for src, dst in self.potions[2].items():
                hx, hy = self._p3_handle_position(src, dst)
                pygame.draw.circle(
                    self.screen,
                    POTION_COLORS[2],
                    (int(hx), int(hy)),
                    P3_HANDLE_RADIUS,
                    2,
                )
                pygame.draw.circle(
                    self.screen,
                    (180, 210, 255),
                    (int(hx), int(hy)),
                    5,
                )

    def _draw_help(self) -> None:
        y = 520
        f = _font(15)
        lines = [
            f"map_id: {self.map_id}  |  文件: {self.current_file or '未保存'}",
            "右键：清除当前药水在该石的出边",
            "药水1/2：JSON 只存 Q/A 正向「源→目标」；E/D 逆向由程序推算（目标石不可被多源指向）",
            "药水3：拖动蓝色圆圈控制柄，调整曲线绕开药水1/2 直线",
            "Esc：取消已选源石  |  Ctrl+Z / Ctrl+Y：撤销 / 重做",
        ]
        for line in lines:
            self.screen.blit(f.render(line, True, COLOR_MUTED), (PANEL_X, y))
            y += 26
        st = (
            f"编辑药水 {self.current_potion + 1}  "
            + (
                f"已选源石 {self.pending_src}，请点击目标"
                if self.pending_src
                else "请点击源石"
            )
        )
        self.screen.blit(_font(17).render(st, True, COLOR_TEXT), (GRID_X, SCREEN_H - 52))

    def run(self) -> None:
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    self._on_key(event)
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self._on_mouse_down(event)
                elif event.type == pygame.MOUSEBUTTONUP:
                    self._on_mouse_up(event)
                elif event.type == pygame.MOUSEMOTION:
                    self._on_mouse_motion(event)

            self.screen.fill(COLOR_BG)
            self._draw_grid()
            self._draw_buttons()
            self._draw_help()
            pygame.display.flip()
            self.clock.tick(60)

        pygame.quit()

    def _on_key(self, event: pygame.event.Event) -> None:
        mods = pygame.key.get_mods()
        if event.key == pygame.K_ESCAPE:
            self.pending_src = None
            self._p3_drag = None
            return
        if mods & pygame.KMOD_CTRL and event.key == pygame.K_z:
            self.history.undo()
            return
        if mods & pygame.KMOD_CTRL and event.key == pygame.K_y:
            self.history.redo()
            return
        if mods & pygame.KMOD_CTRL and event.key == pygame.K_n:
            self._new()
            return
        if mods & pygame.KMOD_CTRL and event.key == pygame.K_o:
            self._open_dialog()
            return
        if mods & pygame.KMOD_CTRL and event.key == pygame.K_s:
            self._save()
            return
        if event.key == pygame.K_a:
            self.show_all_arrows = not self.show_all_arrows
            return
        if event.key == pygame.K_1:
            self.current_potion = 0
            self.pending_src = None
        elif event.key == pygame.K_2:
            self.current_potion = 1
            self.pending_src = None
        elif event.key == pygame.K_3:
            self.current_potion = 2
            self.pending_src = None

    def _p3_update_offset_from_mouse(self, src: str, mx: float, my: float) -> None:
        dst = self.potions[2].get(src)
        if not dst:
            return
        d = self._p3_drag
        if not d:
            return
        hx = mx + d["hmx"]
        hy = my + d["hmy"]
        i0 = _stone_cell_index(src)
        i1 = _stone_cell_index(dst)
        if i0 < 0 or i1 < 0:
            return
        ax, ay = float(_cell_center(i0)[0]), float(_cell_center(i0)[1])
        bx, by = float(_cell_center(i1)[0]), float(_cell_center(i1)[1])
        seg_idx = i0 % 2
        acx, acy = quadratic_bezier_control(ax, ay, bx, by, seg_idx, 0.0)
        ndx = hx - acx
        ndy = hy - acy
        if abs(ndx) < 0.5 and abs(ndy) < 0.5:
            self.potion3_control_offset.pop(src, None)
        else:
            self.potion3_control_offset[src] = (ndx, ndy)

    def _on_mouse_down(self, event: pygame.event.Event) -> None:
        mx, my = float(event.pos[0]), float(event.pos[1])
        if event.button == 1:
            hit_src = self._hit_p3_handle(mx, my)
            if hit_src is not None:
                dst = self.potions[2].get(hit_src)
                if dst:
                    hx, hy = self._p3_handle_position(hit_src, dst)
                    ox, oy = self.potion3_control_offset.get(hit_src, (0.0, 0.0))
                    self._p3_drag = {
                        "src": hit_src,
                        "hmx": hx - mx,
                        "hmy": hy - my,
                        "orig_dx": ox,
                        "orig_dy": oy,
                    }
                    self.pending_src = None
                return

            key = self._hit_button(int(mx), int(my))
            if key == "p1":
                self.current_potion = 0
                self.pending_src = None
            elif key == "p2":
                self.current_potion = 1
                self.pending_src = None
            elif key == "p3":
                self.current_potion = 2
                self.pending_src = None
            elif key == "toggle":
                self.show_all_arrows = not self.show_all_arrows
            elif key == "tpl_a":
                self._load_template("map_a")
            elif key == "tpl_b":
                self._load_template("map_b")
            elif key == "new":
                self._new()
            elif key == "open":
                self._open_dialog()
            elif key == "save":
                self._save()
            elif key == "saveas":
                self._save_dialog()
            elif key is None:
                sid = self._stone_at(int(mx), int(my))
                if sid is None:
                    return
                if self.pending_src is None:
                    self.pending_src = sid
                else:
                    self._apply_edge(self.pending_src, sid)
                    self.pending_src = None
        elif event.button == 3:
            sid = self._stone_at(int(mx), int(my))
            if sid:
                self._clear_edge(sid)
                self.pending_src = None

    def _on_mouse_motion(self, event: pygame.event.Event) -> None:
        if self._p3_drag is None:
            return
        mx, my = float(event.pos[0]), float(event.pos[1])
        src = str(self._p3_drag["src"])
        self._p3_update_offset_from_mouse(src, mx, my)

    def _on_mouse_up(self, event: pygame.event.Event) -> None:
        if event.button != 1 or self._p3_drag is None:
            return
        src = str(self._p3_drag["src"])
        odx = float(self._p3_drag["orig_dx"])
        ody = float(self._p3_drag["orig_dy"])
        cur = self.potion3_control_offset.get(src)
        self._p3_drag = None

        orig_t: Optional[Tuple[float, float]] = (
            None
            if abs(odx) < 0.5 and abs(ody) < 0.5
            else (odx, ody)
        )
        if cur is None:
            cur_t: Optional[Tuple[float, float]] = None
        else:
            cur_t = (float(cur[0]), float(cur[1]))

        def _off_close(
            a: Optional[Tuple[float, float]], b: Optional[Tuple[float, float]]
        ) -> bool:
            if a is None and b is None:
                return True
            if a is None or b is None:
                return False
            return abs(a[0] - b[0]) < 1.0 and abs(a[1] - b[1]) < 1.0

        if _off_close(cur_t, orig_t):
            return
        cmd = SetPotion3ControlOffsetCommand(
            self.potion3_control_offset,
            src,
            orig_t,
            cur_t,
        )
        self.history.execute_command(cmd)


def main() -> None:
    TransitionMapEditor().run()
