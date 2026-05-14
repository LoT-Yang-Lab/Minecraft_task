"""
tail_phase_d_crafting.py — 仅运行尾部任务 · Crafting 阶段 D（炼金动作序列流畅度 20 试）。

运行：
    python tail_phase_d_crafting.py
    浏览器打开 http://127.0.0.1:5302
"""

import random
from typing import Any, Dict, List, Optional

import tail_task_crafting as tt


def _build_only_D(seed: Optional[int] = None) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    D = tt.pseudo_shuffle(
        tt.build_phase_D(),
        key_fn=lambda t: t["category"],
        max_consecutive=2,
        rng=rng,
    )
    out: List[Dict[str, Any]] = [
        {"phase": "intro", "id": "intro_D", "phase_name": "D"},
    ]
    out.extend(D)
    out.append({"phase": "end", "id": "end"})
    return out


tt.build_full_trial_list = _build_only_D
app = tt.app

if __name__ == "__main__":
    print("=" * 60)
    print("  尾部任务 · Crafting 阶段 D（炼金动作序列流畅度 20 试） 启动中...")
    print(f"  数据目录: {tt.DATA_DIR}")
    print("  访问:    http://127.0.0.1:5302")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5302, debug=False)
