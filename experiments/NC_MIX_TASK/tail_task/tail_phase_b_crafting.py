"""
tail_phase_b_crafting.py — 仅运行尾部任务 · Crafting 阶段 B（石块距离判断 36 试）。

运行：
    python tail_phase_b_crafting.py
    浏览器打开 http://127.0.0.1:5301
"""

import random
from typing import Any, Dict, List, Optional

import tail_task_crafting as tt


def _build_only_B(seed: Optional[int] = None) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    B = tt.pseudo_shuffle(
        tt.build_phase_B(),
        key_fn=lambda t: t["true_answer"],
        max_consecutive=3,
        rng=rng,
    )
    out: List[Dict[str, Any]] = [
        {"phase": "intro", "id": "intro_B", "phase_name": "B"},
    ]
    out.extend(B)
    out.append({"phase": "end", "id": "end"})
    return out


tt.build_full_trial_list = _build_only_B
app = tt.app

if __name__ == "__main__":
    print("=" * 60)
    print("  尾部任务 · Crafting 阶段 B（石块距离判断 36 试） 启动中...")
    print(f"  数据目录: {tt.DATA_DIR}")
    print("  访问:    http://127.0.0.1:5301")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5301, debug=False)
