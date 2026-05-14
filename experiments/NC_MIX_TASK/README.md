# NC_MIX_TASK

独立的 Navigation + Crafting + Mix 项目。在**项目根目录**执行下列命令（依赖 `common/bootstrap.py` 统一处理 `sys.path`）。

## 顶层入口（保留各自练习 / 主实验 / 混合）

| 用途 | 命令 |
|------|------|
| 导航练习 | `python practice_navigation.py` |
| 制作练习 | `python practice_crafting.py` |
| 导航主实验 | `python main_navigation.py`（等同 `navigation/main.py`，含 `--graph9` 等） |
| 制作主实验 | `python main_crafting.py`（等同 `crafting/main.py`） |
| 导航地图编辑器 | `python editor_navigation.py` |
| 制作地图编辑器 | `python editor_crafting.py` |
| 混合实验（同进程单窗口） | `python run_mix.py --order navigation-first` |

## 代码布局

- `common/`：共享类型（如 `runtime_context`）、`bootstrap`（子包路径注入）。
- `navigation/`：导航实验、练习（`practice_main.py`）、编辑器、分析脚本等。
- `crafting/`：制作实验、练习、Proposal-5 批量（`run_proposal5_experiment.py`）、`src/` 核心逻辑。
- `mix/`：混合日程、预检、同进程调度。
- `tests/`：混合与跨域相关测试；子目录内另有 `navigation/tests`、`crafting/tests`。

根目录单测：`python -m pytest`（见 `pytest.ini` 的 `pythonpath`）。

## 安装

```bash
pip install -r requirements.txt
```

## 数据目录

- 混合调度：`data/full_schedule.json`
- 混合会话元数据：`data/mix/session_XX/session_metadata.json`
- 导航数据：`data/navigation/...`
- 制作数据：`data/crafting/...`
- 预检报告：`data/mix/preflight_report.json`
