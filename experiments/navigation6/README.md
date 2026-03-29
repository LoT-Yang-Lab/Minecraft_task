# Navigation6：三类公共交通 + 单格地图

本实验为**公交（蓝线）/ 地铁（黄线）/ 轻轨（绿线）**三种线路的「站到站」导航，无东南西北步行、无房间与传送门；可行走格为**单格**与线路**站点**。界面仍为**无地图、仅位置编码 + 动作选项**。地图 JSON 使用 `bus_lines`、`metro_lines`、`light_rail_lines`（各含 `path` 与 `stations`），与 Navigation5 旧格式不兼容。

---

## 一、实验设计

### 1.0 整体实验流程（推荐会话顺序）

从「准备环境」到「写出报告级结果」，建议按下面顺序组织一次完整研究流程（人类被试或 Agent 基线均可接在同一分析管线上）：

1. **环境与地图**：安装依赖，确认 `assets/maps/` 中有所用地图；若自制地图，先用地图编辑器保存 JSON。  
2. **（推荐）练习阶段**：每名被试在**同一张**正式用图上完成 `run_practice.py`，产出 `data/raw/practice/`，用于估计「单步转移知识」与规范策略一致率。  
3. **生成固定试次表**：地图或编码规则变更后，务必重跑 `scripts/generate_trial_sequences.py`，为每张正式用图生成 `assets/trial_sequences/<map_id>.json`（与主程序 `EXPERIMENT_MAPS` 中的文件名 stem 一致）。  
4. **正式实验**：运行 `run_experiment.py`，被试先**选图**（数字键对应 `EXPERIMENT_MAPS` 中的序号；列表见 `app/experiment/main.py`），随后在同一地图上按试次表完成全部双目标 trial；轨迹写入 `data/raw/trajectory/<timestamp>/`。  
5. **（可选）Agent 基线**：`run_agent_experiment.py` 在相同试次表与记录格式下跑纯 A\* 或 noisy A\*，便于与人类轨迹对比。  
6. **离线分析**：数据层对齐编码 → 规范策略（QMDP / A\*）→ 宏提取 →（可选）宏–距离相关；需要时再跑认知地图出图与宏转移可视化。

人类实验在操作上通常是：**练习（每张被试图各一次）→ 正式导航（选该图）**；若研究设计为「多图被试内」，则对每张分配地图重复练习 + 正式流程，并保证 `participant_id` / 文件归档能区分地图与被试。

### 1.1 任务与界面

- **主程序（正式实验）**  
  - **入口**：  
    - 推荐：`python experiments/navigation6/scripts/run_experiment.py`  
    - 兼容：`python experiments/navigation6/main.py`（需在项目根目录 `Minecraft8.0` 下运行）  
  - **界面**：不绘制地图，只显示「当前站点」（位置编码对应的站名，如香蕉站、苹果站）与「可选动作」列表；被试通过数字键选择动作，系统执行后反馈新的位置编码。  
  - **动作空间**：仅三类「到下一站」（每类可多线路）；站在某线路站点上可选沿该线前往下一站（环线规则同配置）。  
  - **试次来源**：每张地图从 `assets/trial_sequences/<map_id>.json` 读取固定双目标序列（默认 27 trial），不再在运行时在线随机抽样。  
  - **目标**：每个 trial 展示目标 A/B（顺序不限），两个目标都到达后自动进入下一 trial。  
  - **数据**：通过 `RLDataRecorder` 记录每步的 Map、Grid、Action 等，默认写入 `experiments/navigation6/data/raw/trajectory/`，供后续轨迹分析使用。

- **练习阶段（学习 + 测试）**  
  - **入口**：  
    - 推荐：`python experiments/navigation6/scripts/run_practice.py`  
    - 兼容：`python experiments/navigation6/practice_main.py`  
  - **可选参数**：`--participant_id` / `-p`、`--seed` / `-s`、`--map` / `-m`（默认地图见 `EXPERIMENT_MAPS[0]`）、`--pair-condition` / `-c`（内部名、`1–4` 或中性代号 `dd` / `dr` / `dc` / `dcr`）。**未传 `-c` 时**，选图后出现第二屏，被试仅见代号 **DD、DR、DC、DCR**（按 1–4），元数据同时写入 `participant_condition_code` 与 `pair_condition` 供主试对照。  
  - **练习题方式序列（有地图 JSON 时）**：在有效地图路径下，学习/测试阶段的题目顺序会**预生成**。**仅在第 1–2 题、第 3–4 题… 成对内**：上一题的「下一编码」与下一题的「当前编码」相接，且这两题的交通方式（抽象为 **R=公交、D=轻轨、C=高铁（地铁线）**）在「同方式 / 异方式不含 C / 异方式含 C」或 9 有序对上按所选条件（DD/DR/DC/DCR）联合抽样；**跨对边界**（如第 2 题与第 3 题）无状态衔接约束，直方图也只统计上述对内边。**测试阶段**与**同一条件**下学习阶段共用同一条方式序列的**前缀**（例如学习为 2N 题、测试为 N 题时，测试的前 N 个方式编码与学习前 N 题一致）；测试抽题在成对约束下**优先无放回**，尽量让每条可参与序列的 instant_transit 边各出现至少一次（元数据 `test_instant_transit_coverage`）。若地图缺失、预生成失败或池中某类动作过少，会**回退**为随机打乱，并在元数据中注明。  
  - **流程**：  
    1. **学习阶段**：从学习池中出题，被试选择「下一步会到哪个站点」；答对/答错有反馈；满足「最少题数 + 正确率阈值 + 连续正确次数」后进入测试阶段。  
    2. **测试阶段**：从测试池出题，无反馈；达到最少题数后进入完成页。  
  - **阶段切换的默认量化标准**（`PracticeManager`，可按需在代码中调整）：学习阶段至少 **8** 题、滑动正确率 ≥ **0.8**、且连续正确 ≥ **3** 题后进入测试；测试阶段至少 **6** 题（默认不要求最低测试正确率，即 `min_test_accuracy=0`）。  
  - **题目来源**：由 `QuestionGenerator` 根据地图与 `GameNavigation6` 单步模拟，枚举「当前编码 + 可执行动作 → 下一编码」得到全池；练习入口再按 `pair_condition` 生成定序学习/测试列表（或打乱）。  
  - **数据**：每条作答记录含 `current_code`、`participant_choice`、`correct`、`rt_ms`、`phase` 等，与元数据一起写入 `experiments/navigation6/data/raw/practice/`，文件名形如 `navigation6_practice_<participant_id>_<时间戳>.json`。

- **地图编辑器**  
  - **入口**：`python -m experiments.navigation6.app.editor.map_editor_nav6`（在项目根运行）。  
  - **功能**：障碍物、单格可行走区、公交/地铁/轻轨路径与站点（各可多线）、起始点与目标点。  
  - **快捷键**：`W` 障碍、`G` 单格；`4/5` 公交路径/站点（蓝），`6/7` 地铁路径/站点（黄），`8/9` 轻轨路径/站点（绿）；`1/2` 起点/终点；`Esc` 选择。  
  - **保存**：地图 JSON 存放在 `experiments/navigation6/assets/maps/`；主程序与练习通过 `--map/-m <文件名.json>` 指定。

### 1.2 位置编码与地图格式

- **位置编码**：所有可行走格按 `(gx, gy)` 字典序编号为 **1～N**，与主程序、练习、认知地图、分析层中的「当前站点」「下一站」一致；0 表示无效或未知。  
- **站名展示**：`station_names.py` 将 1～9 映射为水果站名（香蕉站、苹果站等），仅用于界面显示；内部与数据仍用数字编码。  
- **地图 JSON（Navigation6）**：`single_cells`、`obstacle_map`、`start_pos`、`target_pos`、`bus_lines` / `metro_lines` / `light_rail_lines`（每项为 `{ "path": [[gx,gy],...], "stations": [[gx,gy],...] }` 的数组）；`rooms` 恒为空。试次生成与认知图邻接仅含三类线路的站间边。

### 1.3 实验数据流小结

| 环节       | 产出位置 / 格式 | 用途 |
|------------|------------------|------|
| 主程序     | `experiments/navigation6/data/raw/trajectory/<timestamp>/game_log_*.csv` 或 `.xlsx` | 轨迹分析、规范策略对比、宏提取 |
| 练习阶段   | `experiments/navigation6/data/raw/practice/*.json`（含 `records` + 元数据） | 规范策略一致率、宏提取（可选）、距离联结 |
| 地图       | `experiments/navigation6/assets/maps/*.json` | 认知地图构建、位置编码、策略求解 |
| 双目标试次表 | `experiments/navigation6/assets/trial_sequences/<map_id>.json` | 正式实验固定 trial 顺序与目标对 |

### 1.4 双目标 Trial 设计（试次表 + 运行逻辑）

**研究意图**：每个 trial 给定两个目标站点（位置编码 **targetA**、**targetB**），被试**顺序不限**，规划并执行动作；两个编码各**至少到访一次**后该 trial 结束，再进入下一对目标。界面不展示地图，仅展示当前站名（水果标签）与可选动作列表，以突出空间表征与规划而非像素跟随。

**试次表文件**：

- 路径：`assets/trial_sequences/<map_id>.json`，其中 `<map_id>` 与地图文件主名一致（例如 `assets/maps/map_1773511099.json` 对应 `assets/trial_sequences/map_1773511099.json`）。  
- 主程序在选图时加载对应 JSON；缺失或校验失败会在选图界面报错。

**JSON 结构（摘要）**：

| 字段 | 含义 |
|------|------|
| `version` | 试次表格式版本（如 `1.0`） |
| `map_id` / `map_file` | 对应地图标识与文件名 |
| `generator` | 生成参数：`seed`、`min_distance`、 `distance_metric`（`manhattan` 或 `action_graph`）等 |
| `codebook` | 每个位置编码对应的网格 `(gx, gy)`，便于核对与复现 |
| `trials` | 有序列表；每项含 `trial_id`、`targetA`、`targetB`（均为 1～N 编码） |

**生成规则**（`scripts/generate_trial_sequences.py`）：

- 默认每张图 **27** 个 trial，种子等参数见脚本 `--help`。  
- **平衡性**：对每个可达位置编码 \(c\)，\(c\) 在 **targetA** 与 **targetB** 中出现的次数**相等**。因此要求 `trials` 能被图中节点数 **N** 整除（例如 9 个节点时常用 27 trial）。  
- **间距约束**：任意 trial 中 `targetA` ≠ `targetB`，且两者在选定度量下的距离 ≥ `min_distance`（脚本默认 **1**；节点少时需调大或扩大地图后再用 2）。  
  - `manhattan`：网格曼哈顿距离。  
  - `action_graph`：与游戏一致的可达图（仅公交/地铁/轻轨各线「下一站」边）上的最短路步数；不可达对不会进入序列。  
- 算法在随机打乱 A 侧多重集后，用 **MRV + 回溯** 为每个位置分配合法的 B，并在写出前做整表校验。

**正式程序内的 trial 运行逻辑**（`app/experiment/main.py`）：

- **连续探索（方案 B）**：完成一个 trial 后**不重置**玩家位置；下一 trial 从**当前站立格**开始。第一个 trial 的起点为地图配置的初始出生位置。  
- 地图内置的**单一终点目标**会被关闭，避免「未到双目标就整局结束」。  
- 试次表内 `targetA`/`targetB` 必须与当前地图 `build_position_encoding` 得到的编码一致，且两目标不能相同。

---

## 二、数据分析

### 2.0 后续分析步骤总览

建议将离线分析看成一条**有向流水线**，前一步的输出是后一步的输入（部分步骤可并行）：

| 步骤 | 目的 | 典型输入 | 典型输出 |
|------|------|-----------|-----------|
| 0. 整理数据 | 确认路径与文件名；人类/Agent 轨迹是否在 `data/raw/trajectory/`，练习是否在 `data/raw/practice/` | 原始 CSV/XLSX、JSON | — |
| 1. 编码对齐 | 保证练习、轨迹、认知地图使用同一套 1～N | 地图 JSON、`Map_Structure` / `map_id` | `load_*` 后的规范表 |
| 2. 认知地图（可选） | 检查图结构、谱与距离，辅助解释规范策略与宏–距离 | `assets/maps/*.json` | `outputs/cogmap/*.svg` |
| 3. 规范策略 | QMDP 最优策略 + A\* 最短路基线；练习/轨迹与「推荐下一站」对比 | 地图、练习、轨迹 | `outputs/analysis/normative/*_policy.json`、`*_summary.json`、`*_astar_summary.json`、柱状图 SVG |
| 3b. 统计扩展（可选） | 轨迹一致率的 cluster bootstrap（`--infer`）；步级一致的长表 + logit / cluster-robust（`--mixed-effects`） | 同第 3 步轨迹 | summary JSON 内 `trajectory_inference`、`mixed_effects` 字段 |
| 4. 宏提取 | 频繁子序列 → 宏目录 + 每被试使用次数 | 轨迹（或练习序列） | `outputs/analysis/macros/*_macros.json`、`*_macro_usage.json` 或合并的 `all_*.json` |
| 5. 宏–距离（可选） | 宏起止状态对与图最短路的关联 | 宏目录、宏使用、地图 | `outputs/analysis/distance/*` |
| 6. 宏转移可视化（可选） | 宏观查看「宏驱动的状态转移」网络/热力图/Top-K | `all_macros.json`、`all_macro_usage.json` | 见下文 **§3.3** |

**依赖关系简述**：第 3 步主要依赖地图 + 练习/轨迹；第 4 步可独立于第 3 步，但常与规范结果对照解读；第 5 步依赖第 4 步与地图；第 6 步依赖第 4 步。

更细的子包职责与 `run_normative` 的 `--infer` / `--mixed-effects` 示例见 `analysis/README.md`。

分析层位于 `experiments/navigation6/analysis/`，与游戏/练习/地图并列，不修改运行逻辑。整体分为**数据层**、**规范策略线**、**宏提取线**、**宏–距离联结**，推荐顺序：先数据，再规范策略与宏（可并行），最后可选距离联结。

### 2.1 数据层（`analysis/data/`）

- **`load_practice`**：读取 `data/raw/practice/*.json`，扁平化为记录表，每行含 `participant_id`、`map_id`、`phase`、`current_code`、`participant_choice`、`correct`、`rt_ms` 等，供规范策略对比与宏（若从练习序列挖）使用。  
- **`load_trajectory`**：读取 `data/raw/trajectory` 下 CSV/Excel 轨迹，按 `Map_Structure` 映射为 `map_id`，结合 `to_position_code` 将每步 `(Grid_X, Grid_Y)` 转为位置编码 1～N；输出行含 `participant_id`、`map_id`、`episode`、`step`、`s`、`s_next`（及可选 `a`），供规范策略与宏提取使用。  
- **`to_position_code`**：按 `map_id` 加载对应地图，用与主程序一致的 `build_position_encoding` 得到 `cell_to_code`，提供 `encoder(gx, gy) -> 1..N`，保证练习、轨迹、认知地图使用同一套编码。

### 2.2 规范策略线（`analysis/normative/`）

- **目标**：从认知地图得到「最优策略」，再将被试的练习选择或轨迹与最优策略对比，得到一致率、路径效率等。  
- **流程**：  
  1. **认知地图**：`cogmap_nav6.compute_nav6_cogmap(map_path)` 得到状态图（邻接矩阵）、图拉普拉斯、谱结构、到目标步数等。  
  2. **内部模型**：`build_model.build_internal_model_from_cogmap(cogmap)` 将认知地图转为 POMDP 的 InternalModel（状态 = 位置编码 1～N，动作 = 下一状态索引，完全可观测）。  
  3. **求解**：`solve_policy.solve_qmdp_for_map(model)` 调用参考项目 QMDP 得到最优策略；`get_optimal_next_dict(policy)` 得到「状态 → 推荐下一站」的 1-indexed 字典。  
  4. **对比**：  
     - 练习：`compare_behavior.compare_practice_to_policy(practice_records, optimal_next)` → 总一致率、分阶段（learning/test）一致率。  
     - 轨迹：`compare_trajectory_to_policy(trajectory_rows, optimal_next)` → 步级一致率等。  
- **入口**：`python -m experiments.navigation6.analysis.run_normative --maps-dir ... --practice-dir ... [--rl-data ...] [--map-id ...] [--output-dir ...]`（从项目根运行）。  
- **输出**：在 `outputs/analysis/normative/` 下，每地图生成 `<map_id>_policy.json`（策略表）、`<map_id>_summary.json`（练习/轨迹一致率等）。

### 2.3 宏提取线（`analysis/macros/`）

- **目标**：从行为序列中挖掘频繁子序列（宏），得到宏目录及每被试/每地图的宏使用强度。  
- **流程**：  
  1. **序列**：轨迹或练习记录按 `(participant_id, map_id)` 分组，按 step 排序后得到若干 `(s, s_next)` 序列。  
  2. **频繁子序列**：`extract.extract_frequent_sequences(sequences, min_support, max_length, min_length)` 统计满足最小支持度的连续子序列。  
  3. **宏目录**：`catalog.build_macro_catalog(frequent_pairs)` 整理为带 `macro_id`、`sequence`、`support`、`start_state`、`end_state` 的列表。  
  4. **使用强度**：`usage.compute_macro_usage(trajectory_rows, macro_catalog)` 对每段轨迹统计每个宏出现次数，输出每 `(participant_id, map_id, macro_id)` 的 `usage_count`。  
- **入口**：`python -m experiments.navigation6.analysis.run_macros --maps-dir ... --trajectory-dir ... [--practice-dir ...] [--map-id ...] [--n-gram ...] [--min-support ...] [--output-dir ...]`。  
- **输出**：`outputs/analysis/macros/` 下 `<map_id>_macros.json`（宏目录）、`<map_id>_macro_usage.json`（使用强度）。

### 2.4 宏–距离联结（`analysis/distance/`）

- **目标**：检验宏使用与认知地图上「状态对距离」的关联（如：宏是否更常出现在距离较近/较远的状态对之间）。  
- **流程**：  
  1. **图距离**：`operationalize.graph_distance_matrix(cogmap)` 从邻接矩阵用 Floyd-Warshall 得到任意两状态间最短路径步数（N×N 矩阵）。  
  2. **相关分析**：`macro_distance_correlation.macro_distance_correlation(macro_usage, macro_catalog, dist_mat)` 结合宏的起止状态与使用强度，计算宏–距离指标并输出结果。  
- **入口**：`python -m experiments.navigation6.analysis.run_distance_correlation --maps-dir ... --macro-usage ... --macro-catalog ... [--map-id ...] [--output-dir ...]`。  
- **输出**：`outputs/analysis/distance/` 下每地图的宏–距离结果及 `summary.json`。

---

## 三、分析可视化

### 3.1 认知地图可视化（状态图与谱结构）

- **模块**：`app/viz/cogmap_nav6.py` 从地图构建状态图（邻接矩阵）、图拉普拉斯、特征分解、到目标最短距离；`app/viz/cogmap_plot_nav6.py` 用 matplotlib 生成三张 SVG。  
- **命令行**（项目根下）：  
  ```bash
  python -m experiments.navigation6.app.viz.cogmap_nav6 [地图文件名] [--save-plots] [-o 输出目录]
  ```  
  默认使用 `map_1774095558.json`；`--save-plots` / `-s` 会调用 `render_and_save_cogmap` 写 SVG。  
- **输出**：默认目录 `experiments/navigation6/outputs/cogmap/`（旧 `cogmap_output/` 视为历史产物）：  
  - `{地图名}_original.svg`：状态图圆形布局；  
  - `{地图名}_spectral.svg`：谱嵌入 2D 布局（特征向量前两维）；  
  - `{地图名}_eigenvalues.svg`：拉普拉斯特征值条形图。  
- **代码调用**：  
  ```python
  from experiments.navigation6.app.viz.cogmap_nav6 import compute_nav6_cogmap, render_and_save_cogmap

  out = compute_nav6_cogmap(map_path="map_1774095558.json", include_distances=True)
  paths = render_and_save_cogmap(out, "./outputs/cogmap", basename="my_map")
  ```  
- **返回值**：`N`、`adj`、`labels`、`target_code`、`laplacian`、`eigenvalues`、`eigenvectors`、`components`、`distance_vector`、`distances_by_code` 等，供规范策略与距离分析使用。

### 3.2 规范策略与宏分析结果的可视化

- **规范策略（QMDP 与 A\*）**：运行 `run_normative` 后会自动在 `outputs/analysis/normative/` 下生成：  
  - **QMDP**：`consistency_by_map.svg`、`phase_consistency_by_map.svg`  
  - **A\***：`consistency_by_map_astar.svg`、`phase_consistency_by_map_astar.svg`  
  可通过 `--baseline qmdp|astar|both` 控制输出；需安装 `matplotlib`。  
- **宏–距离**：运行 `run_distance_correlation` 后会在 `outputs/analysis/distance/` 下为每张地图生成 `<map_id>_macro_distance_scatter.svg`（横轴为宏起止状态在图上的距离，纵轴为平均使用次数）。  
- 所有分析结果同时保留 JSON，可用其他工具进一步制图。

### 3.3 宏转移可视化（可选）

在 `run_macros` 得到宏目录与使用统计后，可用 `analysis/visualize_macro_transitions.py` 将宏的起止状态聚合为**有向边强度**，并导出：

- **网络图**（需安装 `networkx`）：`macro_transition_network.png`  
- **状态转移热力图**：`macro_transition_heatmap.png`  
- **Top-K 转移条形图**：`macro_transition_topk.png`  
- **边表**：`edge_table.csv`，便于在 R / Python 中复算

示例（项目根目录，PowerShell 可将 `^` 换为反引号续行或写成一行）：

```bash
python -m experiments.navigation6.analysis.visualize_macro_transitions ^
  --macro-catalog experiments/navigation6/outputs/analysis/macros/all_macros.json ^
  --macro-usage experiments/navigation6/outputs/analysis/macros/all_macro_usage.json ^
  --participant-id P01 ^
  --map-id map_1773511099 ^
  --out-dir experiments/navigation6/outputs/analysis/macros/viz_p01_map1
```

可按需省略 `--participant-id` 以聚合多名被试；`--map-id` 用于限定单张地图。输出目录下通常还有 `summary.json` 记录参数与规模。

---

## 四、运行方式速查

| 用途           | 命令 / 说明 |
|----------------|-------------|
| 主程序         | 推荐 `python experiments/navigation6/scripts/run_experiment.py`（兼容 `python experiments/navigation6/main.py`） |
| 练习阶段       | 推荐 `python experiments/navigation6/scripts/run_practice.py`（兼容 `python experiments/navigation6/practice_main.py`） |
| 地图编辑器     | `python -m experiments.navigation6.app.editor.map_editor_nav6` |
| 认知地图 + 出图 | `python -m experiments.navigation6.app.viz.cogmap_nav6 [地图名] --save-plots` `-o experiments/navigation6/outputs/cogmap` |
| 规范策略       | `python -m experiments.navigation6.analysis.run_normative`（默认读 `assets/maps` 与 `data/raw/*`） |
| 宏提取         | `python -m experiments.navigation6.analysis.run_macros`（默认读 `data/raw/trajectory`） |
| 宏–距离        | `python -m experiments.navigation6.analysis.run_distance_correlation --macro-usage ... --macro-catalog ...` |
| 宏转移可视化   | `python -m experiments.navigation6.analysis.visualize_macro_transitions --macro-catalog ... --macro-usage ... --out-dir ...` |

未指定 `--output-dir` 时，分析脚本默认使用 `experiments/navigation6/outputs/analysis/` 下对应子目录（normative / macros / distance）。

---

## 五、依赖与目录约定

- **运行**：主程序与练习需 `pygame`；认知地图需 `numpy`，**出图**需 `matplotlib`。  
- **宏转移网络图**（§3.3）：`macro_transition_network.png` 需额外安装 `networkx`；热力图与 Top-K 条图仅需 `matplotlib`。  
- **规范策略**：依赖参考项目 `参考代码/策略提取参考项目/pgm-toolkit-main`（通过项目根 `sys.path` 导入），不修改其源码。  
- **轨迹读取**：支持 CSV；若读 Excel 需 `pandas`。  
- **地图**：与主程序、练习、分析共用的地图放在 `experiments/navigation6/assets/maps/`（当前只保留这一份目录）。

更细的分析子包说明见 `analysis/README.md`。

---

## 六、项目使用指南

以下说明如何从零在本机运行实验、收集数据并完成分析，所有命令均在**项目根目录**（`Minecraft8.0`）下执行，除非另作说明。

### 6.1 环境准备

1. **Python**：建议 3.8+，确保已安装项目所需依赖。  
2. **依赖安装**（若项目根有 `requirements.txt` 或类似文件）：  
   ```bash
   pip install -r requirements.txt
   ```  
   若无统一依赖文件，至少需安装：  
   - 主程序与练习：`pygame`  
   - 认知地图与谱计算：`numpy`  
   - 认知地图出图与分析可视化：`matplotlib`  
   - 规范策略：需存在参考项目 `参考代码/策略提取参考项目/pgm-toolkit-main`（见第五节）  
   - 轨迹读 Excel：`pandas`（可选）  
3. **工作目录**：在终端中进入项目根目录，例如：  
   ```bash
   cd D:\桌面文件夹\华东师范\Minecraft8.0
   ```  
   后续所有 `python` / `python -m` 命令均在此目录下执行。

### 6.2 地图准备

- **使用已有地图**：`experiments/navigation6/assets/maps/` 下地图可直接被主程序、练习和分析使用。  
- **自制地图**：运行地图编辑器，编辑完成后保存到 `assets/maps/`：  
  ```bash
  python -m experiments.navigation6.app.editor.map_editor_nav6
  ```  
  保存的 JSON 文件名即后续的「地图 ID」（不含 `.json`），主程序与练习通过 `custom_map_file` 或 `--map` 指定该文件即可。

### 6.3 运行实验与收集数据

**练习阶段（推荐先做，用于规范策略一致率与可选宏/距离分析）**

```bash
# 使用默认地图与匿名被试
python experiments/navigation6/scripts/run_practice.py

# 指定被试 ID、随机种子与地图
python experiments/navigation6/scripts/run_practice.py -p participant_01 -s 42 -m map_1774095558.json -c uniform
```

- 练习结束后，数据默认写入 `experiments/navigation6/data/raw/practice/`。  

**主程序（正式实验，产生轨迹）**

```bash
# 首次或更新地图后，先生成每张地图固定 trial 序列（默认 27）
python experiments/navigation6/scripts/generate_trial_sequences.py

# 再启动正式实验
python experiments/navigation6/scripts/run_experiment.py
```

- 主程序会按所选地图读取 `assets/trial_sequences/<map_id>.json`；若缺失或格式错误，会在选图界面提示错误。  
- 被试通过数字键选择动作，完成当前 trial 的 A/B 双目标后自动进入下一试次，直至试次表结束。  
- 轨迹与事件会由 `RLDataRecorder` 默认写入 `experiments/navigation6/data/raw/trajectory/<timestamp>/`，供后续轨迹级分析与宏提取使用。

**五阶段 session / proposal 5 运行器（新）**

当研究设计需要严格按 proposal 5 的五个 session 顺序执行新版 Navigation6 交通导航任务时，可使用：

```bash
python experiments/navigation6/tests/run_experiment_new.py --order navigation-first
```

或：

```bash
python experiments/navigation6/tests/run_experiment_new.py --order crafting-first
```

说明：

- 该脚本会按照 `tests/trial_schedule.py` 中的五阶段设计生成固定 session 顺序；
- pair catalog 直接硬编码自 proposal 5 的 **Table 3 / Table 4 / Table 5**：
  - grid-dominant：24 对
  - loop-dominant：12 对
  - tie：8 对
- 每个 24-task session 都按 **7 grid : 7 loop : 10 tie** 配额抽样，并按 `m` 做加权抽样；同一 block 内禁止紧邻重复 pair；
- 两种 counterbalanced order 与种子严格对应表 7：
  - navigation-first：Session 1–5 种子依次为 `5101, 5102, 5103, 5104, 5105`
  - crafting-first：Session 1–5 种子依次为 `5201, 5202, 5203, 5204, 5205`
- 五个 session 的任务结构为：
  - navigation-first：`navigation → crafting → navigation → crafting → mixed(12 nav + 12 craft 交替)`
  - crafting-first：`crafting → navigation → crafting → navigation → mixed(12 craft + 12 nav 交替)`
- **仅执行导航 trial**，crafting trial 在 JSON 计划中完整保留为占位信息，但运行时跳过；
- 实际交互界面使用 `experiments/navigation6/main2.py` 的新版交通方式 UI，而不是旧 Graph9 按键界面；
- 每个导航 trial 会明确显示起点与终点，参与者自行导航；单个 trial 最多 **10 步动作**，到达目标或触发 10-step cap 后进入下一 trial；
- 被试按 `Q/E`（公交前/后）、`A/D`（轻轨前/后）、`W`（高铁前）进行导航；
- 每个导航 session 都会把预先规划好的 `(start, goal)` 序列注入 `main2()` 运行；
- 数据改为对齐 3/20 左右旧版格式，但针对**多 session**流程做了分层归档：一次完整运行会写入
  `experiments/navigation6/data/raw/trajectory/proposal5_<order>_<timestamp>/`；
  该目录下会自动保存：
  - `full_schedule.json`：本次完整五阶段 schedule；
  - `session_01_navigation_game_log_Navigation6_User.xlsx`、
    `session_03_navigation_game_log_Navigation6_User.xlsx`、
    `session_05_mixed_game_log_Navigation6_User.xlsx` 等逐 session 工作簿（navigation-first 示例）。
- 注意：因为 Session 2 / 4 可能是 crafting-only，当前实现会**直接跳过这些 session 的执行窗口**，因此 navigation-first 顺序下，关闭 Session 1 的导航窗口后，程序会先在终端中打印“跳过 Session 2 crafting”，然后继续进入下一个含导航试次的 session（通常是 Session 3）。
- 工作簿中：
  - `Sheet1` 为与旧版兼容的步级轨迹表（核心列与旧 `game_log_*.xlsx` 对齐）；
  - `trial_summary` 保存每个导航试次的结果摘要；
  - `planned_trials` / `session_metadata` 保存本次 session 的试次规划与阶段信息；
  - `crafting_placeholders` 保存该 session 中被跳过的 crafting 占位试次。
  - 试次计划 `test_trials`
  - session 元数据 `session_metadata`
  - trial 级摘要 `trial_summaries`
  - `max_actions_per_trial`

常用参数：

- `--start-session 3`：从第 3 个 session 继续；
- `--pause-between-sessions`：每个 session 之间在终端停顿，方便主试控制节奏；若想清楚看到“Session 1 结束 → Session 2（crafting）跳过 → Session 3 启动”的衔接，建议打开此参数；
- 若当前运行环境不是交互式终端（例如某些自动化 shell / IDE task），即使传入 `--pause-between-sessions`，脚本也会自动跳过暂停而不会报 `EOFError`；
- `--dry-run`：只打印并检查五阶段 session 计划，不启动 pygame；
- `--max-sessions 2`：只运行（或 dry-run 检查）从当前起始 session 开始的前 2 个 session；
- `--schedule-output <path>`：导出本次生成的 session 计划 JSON。

如果只想检查而不运行实验，可使用：

```bash
python experiments/navigation6/tests/run_testing_1.py --order navigation-first crafting-first
```

该脚本会输出两个 counterbalanced order 的五阶段 session 摘要，并把生成的 schedule 保存到 `experiments/navigation6/tests/generated_schedules/`。

如果想导出完整的五阶段 trial 计划并人工核对，可查看：

- `experiments/navigation6/tests/generated_schedules/navigation_first_schedule.json`
- `experiments/navigation6/tests/generated_schedules/crafting_first_schedule.json`

其中每个 session 都包含：

- `navigation_trials`：当前 session 真正会执行的导航 trial；
- `crafting_trials`：当前 session 的合成任务规划占位；
- `combined_order`：24 个 task 的实际顺序（mixed session 中为交替顺序）。

**A* Agent 自动实验（无 UI）**

项目新增 `experiments/navigation6/agents/`，用于存放可复用 agent：

- `pure_astar_agent`：每步按 A* 最短路径选下一动作；
- `noisy_astar_agent`：`epsilon-greedy`，以 `epsilon` 概率随机动作，否则按 pure A*。

运行示例：

```bash
# 纯 A* agent
python experiments/navigation6/scripts/run_agent_experiment.py --agent pure --map map_1773511099.json

# noisy A* agent（epsilon-greedy）
python experiments/navigation6/scripts/run_agent_experiment.py --agent noisy --epsilon 0.1 --seed 42 --map map_1773511099.json
```

常用参数：

- `--agent pure|noisy`：agent 类型；
- `--map`：地图文件名（位于 `assets/maps`）；
- `--epsilon`：仅 noisy 生效；
- `--seed`：控制 noisy 随机性可复现；
- `--max-steps-per-trial`：每 trial 步数保护阈值。

输出数据与正式实验一致，写入 `experiments/navigation6/data/raw/trajectory/<timestamp>/`，并包含双目标字段：`DualTrial_ID`、`DualTarget_A`、`DualTarget_B`、`DualTarget_Reached_A`、`DualTarget_Reached_B`。

### 6.4 认知地图可视化（可选）

在分析前或分析中，若需查看某张地图的状态图与谱结构，可在项目根下执行：

```bash
# 使用默认地图并保存三张 SVG（默认文件名见 cogmap_nav6 模块）
python -m experiments.navigation6.app.viz.cogmap_nav6 --save-plots

# 指定地图与输出目录（推荐统一放到 outputs/ 下）
python -m experiments.navigation6.app.viz.cogmap_nav6 map_1773511099.json -s -o experiments/navigation6/outputs/cogmap
```

- 输出默认在 `experiments/navigation6/outputs/cogmap/`：`*_original.svg`、`*_spectral.svg`、`*_eigenvalues.svg`，用浏览器或矢量图工具打开即可。

### 6.5 运行分析管线

分析脚本均以模块方式运行（`python -m experiments.navigation6.analysis.run_*`），且需从**项目根**执行。

**1）规范策略（一致率 + 自动生成柱状图）**

- 需要：地图目录、练习数据目录；可选轨迹目录（主程序产生的 `data/raw/trajectory`）。  
- 示例：  
  ```bash
  python -m experiments.navigation6.analysis.run_normative ^
    --maps-dir experiments/navigation6/assets/maps ^
    --practice-dir experiments/navigation6/data/raw/practice ^
    --rl-data experiments/navigation6/data/raw/trajectory ^
    --baseline both ^
    --output-dir experiments/navigation6/outputs/analysis/normative
  ```  
  （Windows CMD 用 `^` 续行；PowerShell 用反引号 `` ` `` 续行或写为一行；Linux/macOS 用 `\` 续行。）  
- 若省略 `--maps-dir` / `--practice-dir` / `--output-dir`，脚本会使用默认路径（见第四节表格）。  
- 输出：  
  - `outputs/analysis/normative/<map_id>_policy.json`、`<map_id>_summary.json`  
  - `outputs/analysis/normative/<map_id>_astar_summary.json`（A\* 一致率汇总）  
  - `consistency_by_map.svg`、`phase_consistency_by_map.svg`（QMDP，需 matplotlib）  
  - `consistency_by_map_astar.svg`、`phase_consistency_by_map_astar.svg`（A\*，需 matplotlib）  
- **可选**：在同一命令中加入 `--infer`（轨迹一致率 cluster bootstrap 置信区间，可配 `--bootstrap-n` / `--bootstrap-seed` / `--alpha`）或 `--mixed-effects`（步级长表 + logit 与 A\* 相对 QMDP 的对比系数）。详见 `analysis/README.md`。

**2）宏提取（频繁子序列 → 宏目录 + 使用强度）**

- 需要：地图目录、轨迹目录（或练习目录，用于从练习序列挖宏）。  
- 示例：  
  ```bash
  python -m experiments.navigation6.analysis.run_macros ^
    --maps-dir experiments/navigation6/assets/maps ^
    --trajectory-dir experiments/navigation6/data/raw/trajectory ^
    --practice-dir experiments/navigation6/data/raw/practice ^
    --min-support 2 ^
    --output-dir experiments/navigation6/outputs/analysis/macros
  ```  
- 输出：`outputs/analysis/macros/` 下 `*_macros.json`、`*_macro_usage.json`。

**3）宏–距离联结（距离–使用散点图）**

- 需要：地图目录、上一步生成的宏使用 JSON 与宏目录 JSON。  
- 示例：  
  ```bash
  python -m experiments.navigation6.analysis.run_distance_correlation ^
    --maps-dir experiments/navigation6/assets/maps ^
    --macro-usage experiments/navigation6/outputs/analysis/macros/all_macro_usage.json ^
    --macro-catalog experiments/navigation6/outputs/analysis/macros/all_macros.json ^
    --output-dir experiments/navigation6/outputs/analysis/distance
  ```  
- 输出：`outputs/analysis/distance/` 下每地图的 `*_macro_distance.json`、`<map_id>_macro_distance_scatter.svg` 及 `summary.json`。

**4）宏转移可视化（可选，依赖第 2 步 JSON）**

- 见 **§3.3**；常用于论文插图或检查宏是否在少数状态对之间过度集中。

### 6.6 查看结果

- **JSON**：用任意文本编辑器或 JSON 查看器打开 `outputs/analysis/normative/`、`outputs/analysis/macros/`、`outputs/analysis/distance/` 下对应文件。  
- **图表**：  
  - 认知地图：打开 `outputs/cogmap/` 下 `*_original.svg`、`*_spectral.svg`、`*_eigenvalues.svg`。  
  - 规范策略：打开 `outputs/analysis/normative/consistency_by_map.svg`、`phase_consistency_by_map.svg`（以及 A\* 的 `*_astar.svg`）。  
  - 宏–距离：打开 `outputs/analysis/distance/<map_id>_macro_distance_scatter.svg`。  

### 6.7 典型流程小结

与 **§1.0 整体实验流程**、**§2.0 后续分析步骤总览**一致，最短路径可记为：

1. 进入项目根 → 安装依赖 → 确认地图在 `experiments/navigation6/assets/maps/`。  
2. 运行练习：`scripts/run_practice.py`（可多次、多被试）→ 检查 `data/raw/practice/`。  
3. 先运行 `scripts/generate_trial_sequences.py` 生成固定 trial 表，再运行 `scripts/run_experiment.py` → 检查 `data/raw/trajectory/`。  
4. 可选：运行 `cogmap_nav6.py --save-plots` 查看认知地图。  
5. 运行分析：`run_normative`（可加 `--infer` / `--mixed-effects`）→ `run_macros` → 可选 `run_distance_correlation` → 可选 `visualize_macro_transitions`（**§3.3**）。  
6. 在 `outputs/` 下查看 JSON、SVG 与 PNG，按需进一步制图或写报告。
