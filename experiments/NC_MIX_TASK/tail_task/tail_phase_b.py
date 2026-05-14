"""
tail_phase_b.py — 仅运行尾部任务 · 阶段 B（一站关系判断 36 试）。

复用 tail_task 模块（节点定义、Flask 路由、HTML、保存逻辑），
仅在启动时把 trial_list 替换为只包含 Phase B 的版本。

运行：
    python tail_phase_b.py
    浏览器打开 http://127.0.0.1:5101
"""

import random
from typing import Any, Dict, List, Optional

import tail_task as tt


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


# 替换 tail_task 中的 trial 构建器
tt.build_full_trial_list = _build_only_B
app = tt.app

if __name__ == "__main__":
    print("=" * 60)
    print("  尾部任务 · 阶段 B（一站关系判断 36 试） 启动中...")
    print(f"  数据目录: {tt.DATA_DIR}")
    print("  访问:    http://127.0.0.1:5101")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5101, debug=False)
