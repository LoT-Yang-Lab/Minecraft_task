# Navigation6 分析层

本目录实现「规范策略 + 宏提取 + 宏与距离联结」的统一分析流水线，与现有 `src`（游戏/练习）、`practice_data`、`maps` 并列，不修改现有运行逻辑。

## 目标与两条分析线

1. **规范策略线**：从认知地图构建 POMDP 内部模型，用参考项目 QMDP 求解最优策略；将练习/轨迹与最优策略对比（一致率、路径效率）；可选参数拟合。
   - **A\* 对照基线**：在同一认知地图图结构上做**完全信息最短路**（边代价=1），导出「下一跳策略」作为强基线，用于对照 QMDP 与人类行为差异。
2. **宏提取线**：从行为序列中挖掘频繁子序列（宏），输出宏目录与每被试/每地图的宏使用强度。
3. **可选联结**：检验宏使用与认知地图上相关状态对距离的关联。

## 数据格式与放置位置

| 数据 | 路径 | 说明 |
|------|------|------|
| 练习 | `experiments/navigation6/data/raw/practice/*.json`（兼容旧 `practice_data/`） | 每文件含 `participant_id`, `map_id`, `records`（含 current_code, participant_choice, phase 等） |
| 轨迹 | `experiments/navigation6/data/raw/trajectory/<timestamp>/game_log_*.csv` 或 `.xlsx`（兼容项目根 `rl_data/`） | Episode_ID, Step_Index, Map_Structure, Grid_X, Grid_Y, Action_Type, Action_Detail 等 |
| 地图 | `experiments/navigation6/assets/maps/<map_id>.json`（兼容旧 `maps/`） | 与 cogmap_nav6 及 to_position_code 所用一致 |

- **data** 层输出：统一位置编码（1～N），练习表与轨迹表供 normative / macros 共用。
- 轨迹中的「动作」与规范策略的动作空间对齐方式见 normative/build_model（动作索引 = 下一状态索引）。

## 子包职责与调用顺序

- **data**：`load_practice`、`load_trajectory`、`to_position_code`；输出按地图+被试的记录与序列。
- **normative**：`build_model`（cogmap → InternalModel）→ `solve_policy`（QMDP）/ `solve_astar`（A\* 最短路基线）→ `compare_behavior`（一致率、路径效率）；可选 `fit_params`。
- **macros**：`extract`（n-gram / 频繁子序列）→ `catalog`（宏列表）→ `usage`（每被试/每地图宏使用强度）。
- **distance**：`operationalize`（图距离或选择接近度）→ `macro_distance_correlation`（宏使用 vs 距离）。

推荐顺序：**先 data，再 normative 与 macros（可并行），最后可选 distance**。

## 运行方式

 - **规范策略**：  
   - 基本用法：  
     `python -m experiments.navigation6.analysis.run_normative [--maps-dir ...] [--practice-dir ...] [--rl-data ...] [--map-id ...] [--output-dir ...] [--baseline qmdp|astar|both]`（默认读 `assets/maps` 与 `data/raw`）  
   - 推断友好的一致率摘要（路线A，cluster bootstrap）：  
     在上面命令中加 `--infer`，脚本会在每张地图的 summary JSON 中增加 `trajectory_inference` 字段，包含被试聚合后的一致率和 participant-cluster bootstrap 置信区间。  
   - 混合效应/回归分析（路线B，logit + cluster-robust）：  
     在上面命令中再加 `--mixed-effects`，脚本会基于正式实验轨迹构建一致性长表，并在每张地图的 summary JSON 中增加 `mixed_effects` 字段，给出 baseline（A* 相对于 QMDP）的回归系数、OR 以及 95% 置信区间。例如：  
     ```bash
     python -m experiments.navigation6.analysis.run_normative ^
       --maps-dir experiments/navigation6/assets/maps ^
       --rl-data experiments/navigation6/data/raw/trajectory ^
       --baseline both ^
       --infer ^
       --mixed-effects
     ```
 - **宏提取**：`python -m experiments.navigation6.analysis.run_macros [--maps-dir ...] [--trajectory-dir ...] [--practice-dir ...] [--map-id ...] [--output-dir ...]`（默认读 `data/raw/trajectory`）  
 - **宏–距离相关**：`python -m experiments.navigation6.analysis.run_distance_correlation [--maps-dir ...] --macro-usage ... --macro-catalog ... [--map-id ...] [--output-dir ...]`

从项目根目录运行；未指定 `--output-dir` 时默认使用 `analysis/output/`。

## 输出目录约定（analysis/output/）

- **normative/**（默认写到 `experiments/navigation6/outputs/analysis/normative/`；旧的 `analysis/output/` 视为历史产物）：
  - **QMDP**：每地图最优策略表（如 `<map_id>_policy.json`）、一致率汇总（`<map_id>_summary.json`）、图表（`consistency_by_map.svg`、`phase_consistency_by_map.svg`）。
  - **A\***：一致率汇总（`<map_id>_astar_summary.json`）、图表（`consistency_by_map_astar.svg`、`phase_consistency_by_map_astar.svg`）。
- **macros/**：宏目录（如 `<map_id>_macros.json`）、每被试/每地图宏使用统计（默认写到 `experiments/navigation6/outputs/analysis/macros/`）。\n+- **distance/**：宏–距离相关结果与简短说明（默认写到 `experiments/navigation6/outputs/analysis/distance/`）。

## 依赖

- 分析层需 `numpy`；轨迹读取可选 `pandas`（支持 xlsx）。
- 规范策略依赖参考项目：`参考代码/策略提取参考项目/pgm-toolkit-main`，通过项目根 `sys.path` 导入 `pgm_toolkit.dynamical_models.pomdp`，不修改参考项目源码。
