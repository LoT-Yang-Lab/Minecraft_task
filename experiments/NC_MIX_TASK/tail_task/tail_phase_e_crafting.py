"""
tail_phase_e_crafting.py — 仅运行尾部任务 · Crafting 阶段 E（中转石块报告 27 试）。

运行：
    python tail_phase_e_crafting.py
    浏览器打开 http://127.0.0.1:5303
"""

import random
from typing import Any, Dict, List, Optional

import tail_task_crafting as tt


def _build_only_E(seed: Optional[int] = None) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    E = tt.pseudo_shuffle(
        tt.build_phase_E(),
        key_fn=lambda t: t["start"],
        max_consecutive=2,
        rng=rng,
    )
    out: List[Dict[str, Any]] = [
        {"phase": "intro", "id": "intro_E", "phase_name": "E"},
    ]
    out.extend(E)
    out.append({"phase": "end", "id": "end"})
    return out


tt.build_full_trial_list = _build_only_E
app = tt.app

if __name__ == "__main__":
    print("=" * 60)
    print("  尾部任务 · Crafting 阶段 E（中转石块报告 27 试） 启动中...")
    print(f"  数据目录: {tt.DATA_DIR}")
    print("  访问:    http://127.0.0.1:5303")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5303, debug=False)
