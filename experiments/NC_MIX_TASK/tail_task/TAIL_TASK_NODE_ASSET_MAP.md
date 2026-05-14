# Tail Task 节点 ↔ 素材映射（原始地图对照）

> 数据源：
> - **导航**：`navigation/app/assets/maps/map_1774095558.json`（运行时 map_id `map_1774095558`）
>   节点的形状/颜色定义在 `navigation/app/common/station_names.py::STATION_SHAPES`（顺序即 code 1..9）。
> - **合成**：`crafting/data/maps/builtin_map_a.json`（`map_id=custom`，`linked_navigation_map_id=map_1774095558`）
>   节点的素材定义在 `crafting/src/stone_space.py`（`STONE_IDS = stone_01..stone_09`，按 3×3 行优先排布；`stone_row_col(stone_0i) == ((i-1)//3, (i-1)%3)`）。
> - **石块贴图本体**：`Minecraft8.0/shared/assets/stone/stone_0X.png`（共 9 张，已确认全部存在）。
>
> 节点编号统一使用 3×3 **行优先** 1–9：
> ```
>           col=0   col=1   col=2
>   row=0    1       2       3
>   row=1    4       5       6
>   row=2    7       8       9
> ```
> 这与 `tail_task.py` / `tail_task_crafting.py` 的内部 `NODES` 字典完全一致，
> 也与 `crafting/src/stone_space.py::stone_row_col` 一致。

---

## 1. 导航 tail task（`tail_task.py`）

节点本身无 PNG 贴图——使用 unicode 形状字符 + CSS 颜色绘制（与 `STATION_SHAPES` 一一对应）。

| 节点 # | 网格 (row, col) | shape       | unicode | 颜色 (RGB)        | label（中文站名） | STATION_SHAPES 索引 |
| :----: | :-------------: | :---------- | :-----: | :---------------- | :---------------- | :------------------: |
| **1**  | (0, 0)          | triangle    | ▲       | #E63C3C 红        | 红色三角形站      | 0 |
| **2**  | (0, 1)          | square      | ■       | #3C78E6 蓝        | 蓝色正方形站      | 1 |
| **3**  | (0, 2)          | circle      | ●       | #32B450 绿        | 绿色圆形站        | 2 |
| **4**  | (1, 0)          | diamond     | ◆       | #E69628 橙        | 橙色菱形站        | 3 |
| **5**  | (1, 1)          | star        | ★       | #A050DC 紫        | 紫色五角星站      | 4 |
| **6**  | (1, 2)          | hexagon     | ⬢       | #E66EAA 粉        | 粉色六边形站      | 5 |
| **7**  | (2, 0)          | cross       | ✚       | #DCC828 黄        | 黄色十字站        | 6 |
| **8**  | (2, 1)          | inv_triangle| ▼       | #28BEC8 青        | 青色倒三角站      | 7 |
| **9**  | (2, 2)          | pentagon    | ⬟       | #A06E3C 棕        | 棕色五边形站      | 8 |

> 罗马数字别名（保留兼容）：节点 i ↔ `Ⅰ站..Ⅸ站`（`STATION_NAMES[i-1]`）。
> 兼容图标文件名词干：`I, II, III, IV, V, VI, VII, VIII, IX`（`STATION_ICON_ENGLISH_NAMES`）。

### 导航地图原始坐标（map_1774095558.json）

地图世界坐标 → 节点编号的对应关系：

| 节点 # | 世界坐标 (x, y) | 网格 (row, col) |
| :----: | :-------------: | :-------------: |
| 1 | (12,  7) | (0, 0) |
| 2 | (16,  7) | (0, 1) |
| 3 | (20,  7) | (0, 2) |
| 4 | (12, 11) | (1, 0) |
| 5 | (16, 11) | (1, 1) |
| 6 | (20, 11) | (1, 2) |
| 7 | (12, 15) | (2, 0) |
| 8 | (16, 15) | (2, 1) |
| 9 | (20, 15) | (2, 2) |

线路 stations 列表与上表一一对应；3 类线路（公交 / 地铁 / 轻轨）经一统化重命名为 **公交 Q/E + 地铁 A/D + 快速巴士 W**（详见 `TAIL_TASK_DESIGN.md`）。

---

## 2. 合成 tail task（`tail_task_crafting.py`）

节点本身使用 PNG 贴图（无形状/颜色语义）。Flask 通过 `/stone/<filename>` 路由从 `Minecraft8.0/shared/assets/stone/` 直接服务图片。

| 节点 # | 网格 (row, col) | stone_id  | 贴图文件                                        | 中文标签 | URL 路径               |
| :----: | :-------------: | :-------: | :---------------------------------------------: | :------: | :--------------------- |
| **1**  | (0, 0)          | stone_01  | `shared/assets/stone/stone_01.png`              | 石块一   | `/stone/stone_01.png` |
| **2**  | (0, 1)          | stone_02  | `shared/assets/stone/stone_02.png`              | 石块二   | `/stone/stone_02.png` |
| **3**  | (0, 2)          | stone_03  | `shared/assets/stone/stone_03.png`              | 石块三   | `/stone/stone_03.png` |
| **4**  | (1, 0)          | stone_04  | `shared/assets/stone/stone_04.png`              | 石块四   | `/stone/stone_04.png` |
| **5**  | (1, 1)          | stone_05  | `shared/assets/stone/stone_05.png`              | 石块五   | `/stone/stone_05.png` |
| **6**  | (1, 2)          | stone_06  | `shared/assets/stone/stone_06.png`              | 石块六   | `/stone/stone_06.png` |
| **7**  | (2, 0)          | stone_07  | `shared/assets/stone/stone_07.png`              | 石块七   | `/stone/stone_07.png` |
| **8**  | (2, 1)          | stone_08  | `shared/assets/stone/stone_08.png`              | 石块八   | `/stone/stone_08.png` |
| **9**  | (2, 2)          | stone_09  | `shared/assets/stone/stone_09.png`              | 石块九   | `/stone/stone_09.png` |

> 此映射由 `stone_space.py::STONE_IDS` 与 `stone_row_col` 唯一决定：
> ```python
> STONE_IDS = [f"stone_{i:02d}" for i in range(1, 10)]
> # stone_row_col(stone_0i) == ((i-1)//3, (i-1)%3)
> ```
> 因此 stone_0i 的 (row, col) = ((i-1)//3, (i-1)%3)，与导航的网格行优先编号 1..9 完全对齐——
> **节点 i ↔ stone_0i**（直接同号），无须再做第二层置换。

### 合成地图原始转移规则（builtin_map_a.json）

`builtin_map_a.json` 中 `linked_navigation_map_id = "map_1774095558"`，
其 `potion1 / potion2 / potion3` 对应「公交 / 地铁 / 快速巴士」：

| 字段     | tail task 含义              | 边（stone_id 形式）                                                                                  |
| :------: | :-------------------------- | :-------------------------------------------------------------------------------------------------- |
| potion1  | 公交 E（行内 →）            | s01→s02, s02→s03, s04→s05, s05→s06, s07→s08, s08→s09                                                |
| potion2  | 地铁 D（列内 ↓）            | s01→s04, s02→s05, s03→s06, s04→s07, s05→s08, s06→s09                                                |
| potion3  | 快速巴士 W（4 角顺时针）    | s01→s03, s03→s09, s09→s07, s07→s01                                                                  |

> 反向边（公交 Q / 地铁 A）由 `tail_task_crafting.py::build_phase_*` 通过逆转 potion1 / potion2 自动生成。

---

## 3. 一致性校验（导航 ↔ 合成 同构）

| 节点 # | 导航 shape | 导航 color | 合成 stone | 合成 PNG       |
| :----: | :--------- | :--------- | :--------- | :------------- |
| 1 | triangle     | 红 #E63C3C | stone_01 | stone_01.png |
| 2 | square       | 蓝 #3C78E6 | stone_02 | stone_02.png |
| 3 | circle       | 绿 #32B450 | stone_03 | stone_03.png |
| 4 | diamond      | 橙 #E69628 | stone_04 | stone_04.png |
| 5 | star         | 紫 #A050DC | stone_05 | stone_05.png |
| 6 | hexagon      | 粉 #E66EAA | stone_06 | stone_06.png |
| 7 | cross        | 黄 #DCC828 | stone_07 | stone_07.png |
| 8 | inv_triangle | 青 #28BEC8 | stone_08 | stone_08.png |
| 9 | pentagon     | 棕 #A06E3C | stone_09 | stone_09.png |

两份 tail task 的 `NODES` 字典使用同一行优先 3×3 编号 1..9，同一线路系统（公交 Q/E + 地铁 A/D + 快速巴士 W），同一 28 条有向边，仅在节点的「视觉外壳」上一边用形状/颜色、一边用 PNG 贴图，两者互为同构（节点 i 直接对应 stone_0i）。
