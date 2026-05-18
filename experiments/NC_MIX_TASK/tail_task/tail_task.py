"""
tail_task.py - 尾部任务 (Tail Task) 独立 Flask 应用
                — 与 NC_MIX_TASK / navigation6 / graph9 实际运行时地图对齐

依据 TAIL_TASK_DESIGN.md。

图：3×3 行优先编号 1-9；与「统一网格 · 导航与合成」运行时图完全一致。
  · 公交  —— 行内一步双向：Q (前 / 向左, 深蓝)  +  E (后 / 向右, 浅蓝)
  · 地铁  —— 列内一步双向：A (前 / 向上, 深绿)  +  D (后 / 向下, 浅绿)
  · 快速巴士 W —— 仅在 4 角顺时针单向：1 → 3 → 9 → 7 → 1（紫/品红）

节点用彩色几何形状（红三角、蓝方块、绿圆、橙菱形、紫五角星、粉六边形、黄十字、青倒三角、棕五边形），
与运行时 `navigation/app/common/station_names.py::STATION_SHAPES` 一一对应。
所有 emoji 图标已替换为线路颜色箭头，与 NC_MIX_TASK 保持一致。

阶段：
  B  — 节点间距离判断（36 试，4 选 1：1 / 2 / 3 / 4 步）+ 5 级置信
         距离按「无向网格图」（公交 + 地铁，不含快速巴士 W）计算，最大 4 步
  D  — 动作序列流畅度（20 试，5 级 Likert）
  E  — 中转节点报告（27 试，9 起点 × 3 终点）

数据保存：data/tail_task/{subject_id}_{timestamp}.json + .csv

运行：
    python tail_task.py
    浏览器打开 http://127.0.0.1:5001
"""

import csv
import json
import os
import random
import time
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, jsonify, render_template_string, request

# ============================================================
# 节点 / 线路定义（与 NC_MIX_TASK / graph9.py 对齐）
# ============================================================
# 3×3 行优先编号：
#   1 2 3
#   4 5 6
#   7 8 9
#
# 节点显示：彩色几何形状（来自 NC_MIX_TASK/common/station_names.py）
NODES: Dict[int, Dict[str, Any]] = {
    1: {"id": 1, "shape": "triangle",     "color": "#E63C3C", "name": "红色三角形站", "ch": "▲"},
    2: {"id": 2, "shape": "square",       "color": "#3C78E6", "name": "蓝色正方形站", "ch": "■"},
    3: {"id": 3, "shape": "circle",       "color": "#32B450", "name": "绿色圆形站",   "ch": "●"},
    4: {"id": 4, "shape": "diamond",      "color": "#E69628", "name": "橙色菱形站",   "ch": "◆"},
    5: {"id": 5, "shape": "star",         "color": "#A050DC", "name": "紫色五角星站", "ch": "★"},
    6: {"id": 6, "shape": "hexagon",      "color": "#E66EAA", "name": "粉色六边形站", "ch": "⬢"},
    7: {"id": 7, "shape": "cross",        "color": "#DCC828", "name": "黄色十字站",   "ch": "✚"},
    8: {"id": 8, "shape": "inv_triangle", "color": "#28BEC8", "name": "青色倒三角站", "ch": "▼"},
    9: {"id": 9, "shape": "pentagon",     "color": "#A06E3C", "name": "棕色五边形站", "ch": "⬟"},
}
ALL_NODE_IDS = list(range(1, 10))

# 节点在 3×3 网格中的位置 (row, col)
_NODE_POS: Dict[int, Tuple[int, int]] = {
    1: (0, 0), 2: (0, 1), 3: (0, 2),
    4: (1, 0), 5: (1, 1), 6: (1, 2),
    7: (2, 0), 8: (2, 1), 9: (2, 2),
}

# 线路：颜色与运行时统一网格图（导航 / 合成）一致。
# 每条交通线路实际由 2 个方向键驱动 (Q/E, A/D)，运行时绘成两种深浅色调；
# 但拓扑层面这是同一条无向边，因此 LINES 仍按 3 类组织。
LINES: Dict[str, Dict[str, str]] = {
    "bus": {
        "label": "公交",
        "color": "#3CA0FF",            # 主色（双向边整体）
        "color_q": "#1E5FE6",          # 公交Q (前) — 深蓝
        "color_e": "#6FA8FF",          # 公交E (后) — 浅蓝
        "label_q": "公交Q",
        "label_e": "公交E",
        "key_q": "Q",
        "key_e": "E",
    },
    "subway": {
        "label": "地铁",
        "color": "#50C878",
        "color_a": "#2E9F4A",          # 地铁A (前) — 深绿
        "color_d": "#6BD884",          # 地铁D (后) — 浅绿
        "label_a": "地铁A",
        "label_d": "地铁D",
        "key_a": "A",
        "key_d": "D",
    },
    "rapidbus": {
        "label": "快速巴士",
        "color": "#C84BD8",            # 紫/品红，单色（仅 W 一个方向键）
        "key": "W",
        "label_w": "快速巴士W",
    },
}

# 公交（行内双向，6 条无向）
BUS_EDGES: List[Tuple[int, int]] = [(1, 2), (2, 3), (4, 5), (5, 6), (7, 8), (8, 9)]
# 地铁（列内双向，6 条无向）
SUBWAY_EDGES: List[Tuple[int, int]] = [(1, 4), (4, 7), (2, 5), (5, 8), (3, 6), (6, 9)]
# 快速巴士（4 角顺时针单向，4 条有向；仅 W 键可用）
RAPID_NEXT: Dict[int, int] = {1: 3, 3: 9, 9: 7, 7: 1}
# 别名（保持向后兼容）
RING_NEXT = RAPID_NEXT


def _undirected_edge_set(pairs: List[Tuple[int, int]]) -> set:
    return {tuple(sorted(p)) for p in pairs}


_BUS_SET = _undirected_edge_set(BUS_EDGES)
_SUBWAY_SET = _undirected_edge_set(SUBWAY_EDGES)
_RAPID_UNDIR_SET = _undirected_edge_set([(a, b) for a, b in RAPID_NEXT.items()])


def _undirected_relation(a: int, b: int) -> Optional[str]:
    """无向关系（用于 Phase B）：返回 'bus' / 'subway' / 'rapidbus' 或 None。"""
    pair = tuple(sorted((a, b)))
    if pair in _BUS_SET:
        return "bus"
    if pair in _SUBWAY_SET:
        return "subway"
    if pair in _RAPID_UNDIR_SET:
        return "rapidbus"
    return None


def _directed_line(a: int, b: int) -> Optional[str]:
    """有向一站关系（用于 Phase D 序列校验）。

    返回值除「线路类型」外，还隐含了方向键：
      bus  : a→b 同行，b > a → 走 E（向右），b < a → 走 Q（向左）
      subway: a→b 同列，b > a → 走 D（向下），b < a → 走 A（向上）
      rapidbus: 仅当 RAPID_NEXT[a] == b 时合法（W 键单向）
    """
    pair = tuple(sorted((a, b)))
    if pair in _BUS_SET:
        return "bus"
    if pair in _SUBWAY_SET:
        return "subway"
    if RAPID_NEXT.get(a) == b:
        return "rapidbus"
    return None


def _directed_action(a: int, b: int) -> Optional[str]:
    """有向一步关系，返回方向键标签：'bus_q'/'bus_e'/'subway_a'/'subway_d'/'rapidbus_w'。

    供 Phase D 显示对应深浅色调。
    """
    pair = tuple(sorted((a, b)))
    if pair in _BUS_SET:
        # 行内：col 增大 = E（向右），col 减小 = Q（向左）
        return "bus_e" if b > a else "bus_q"
    if pair in _SUBWAY_SET:
        # 列内：row 增大（编号大 8）= D（向下），row 减小 = A（向上）
        return "subway_d" if b > a else "subway_a"
    if RAPID_NEXT.get(a) == b:
        return "rapidbus_w"
    return None


def _direct_targets(node: int) -> set:
    """节点 a 的所有一站直达目标（用于 Phase E 候选过滤）。"""
    out = set()
    for a, b in BUS_EDGES + SUBWAY_EDGES:
        if a == node:
            out.add(b)
        if b == node:
            out.add(a)
    if node in RAPID_NEXT:
        out.add(RAPID_NEXT[node])
    return out


# ============================================================
# 阶段 B — 36 试次（节点间距离判断，1-4 步）
# ============================================================
# 距离图：仅公交 + 地铁（无向网格），不含快速巴士 W ⇒ 直径 = 4。
# 全部 C(9,2) = 36 对，每对呈现一次。

_GRID_NEIGHBORS: Dict[int, set] = {i: set() for i in ALL_NODE_IDS}
for _a, _b in BUS_EDGES + SUBWAY_EDGES:
    _GRID_NEIGHBORS[_a].add(_b)
    _GRID_NEIGHBORS[_b].add(_a)


def _grid_distance(a: int, b: int) -> int:
    """无向 BFS 最短距离（仅公交 + 地铁），返回 1..4。"""
    if a == b:
        return 0
    visited = {a}
    frontier = [a]
    d = 0
    while frontier:
        d += 1
        nxt = []
        for u in frontier:
            for v in _GRID_NEIGHBORS[u]:
                if v == b:
                    return d
                if v not in visited:
                    visited.add(v)
                    nxt.append(v)
        frontier = nxt
    return -1  # 不应发生（连通图）


def build_phase_B() -> List[Dict[str, Any]]:
    """
    新 Phase B（节点间距离判断）：
      - 36 试 = C(9,2) 全枚举，每对一次
      - 答案为公交+地铁网格上的无向最短距离 ∈ {1,2,3,4}
      - 被试 4 选 1 + 5 级置信
    """
    trials: List[Dict[str, Any]] = []
    pairs = []
    for i in range(1, 10):
        for j in range(i + 1, 10):
            pairs.append((i, j))
    assert len(pairs) == 36

    for a, b in pairs:
        d = _grid_distance(a, b)
        assert 1 <= d <= 4, f"({a},{b}) distance={d} out of range"
        trials.append({
            "id": f"B-{len(trials)+1:02d}",
            "phase": "B",
            "a": a, "b": b,
            "true_answer": d,
            "category": f"d{d}",
        })

    # 验证分布（3×3 Manhattan）：d=1:12, d=2:14, d=3:8, d=4:2
    from collections import Counter
    ct = Counter(t["true_answer"] for t in trials)
    assert ct[1] == 12 and ct[2] == 14 and ct[3] == 8 and ct[4] == 2, ct
    return trials


# ============================================================
# 阶段 D — 20 试次（动作序列流畅度）
# ============================================================

def _seq_actions(seq: List[int]) -> List[str]:
    """返回每一步的有向方向键标签（bus_q / bus_e / subway_a / subway_d / rapidbus_w）。"""
    out = []
    for a, b in zip(seq[:-1], seq[1:]):
        act = _directed_action(a, b)
        assert act is not None, f"非法边 {a}->{b}"
        out.append(act)
    return out


def build_phase_D() -> List[Dict[str, Any]]:
    raw = [
        # G — grid corner chunk (5)
        ("D-G1", [1, 2, 5],     "G_corner"),
        ("D-G2", [5, 6, 3],     "G_corner"),
        ("D-G3", [7, 4, 5],     "G_corner"),
        ("D-G4", [9, 6, 5],     "G_corner"),
        ("D-G5", [4, 5, 8],     "G_corner"),
        # F — face loop (5)
        ("D-F1", [1, 2, 5, 4],  "F_face"),
        ("D-F2", [2, 3, 6, 5],  "F_face"),
        ("D-F3", [4, 5, 8, 7],  "F_face"),
        ("D-F4", [5, 6, 9, 8],  "F_face"),
        ("D-F5", [4, 1, 2, 5],  "F_face"),
        # L — ring loop (4)
        ("D-L1", [1, 3, 9],     "L_ring"),
        ("D-L2", [3, 9, 7],     "L_ring"),
        ("D-L3", [9, 7, 1],     "L_ring"),
        ("D-L4", [1, 3, 9, 7],  "L_ring"),
        # S — straight (3)
        ("D-S1", [1, 2, 3],     "S_straight"),
        ("D-S2", [1, 4, 7],     "S_straight"),
        ("D-S3", [4, 5, 6],     "S_straight"),
        # M — mixed with ring (3)
        ("D-M1", [1, 3, 6, 5],  "M_mixed"),
        ("D-M2", [9, 7, 8, 5],  "M_mixed"),
        ("D-M3", [7, 1, 2, 5],  "M_mixed"),
    ]
    trials = []
    for tid, seq, cat in raw:
        actions = _seq_actions(seq)
        trials.append({
            "id": tid, "phase": "D",
            "sequence": seq, "actions": actions,
            "category": cat,
            "length": len(seq),
        })
    assert len(trials) == 20
    return trials


# ============================================================
# 阶段 E — 27 试次（中转节点报告）
# ============================================================

def build_phase_E() -> List[Dict[str, Any]]:
    """Phase E：仅考虑公交 + 地铁（不含快速巴士 W）时，
    起讫之间在 3×3 网格上的最短距离 ≥ 3 的全部有向对。

    在 3×3 网格中满足该约束的无向对共 10 个：
      d=3 (8 对)：{1,6} {1,8} {2,7} {2,9} {3,4} {3,8} {4,9} {6,7}
      d=4 (2 对)：{1,9} {3,7}
    展开为 20 个有向 (start, end)。
    """
    raw: List[Tuple[int, int]] = []
    for s in ALL_NODE_IDS:
        for e in ALL_NODE_IDS:
            if s == e:
                continue
            if _grid_distance(s, e) >= 3:
                raw.append((s, e))
    # 验证：每对在含 W 的完整图上也非一站直连
    for s, e in raw:
        assert e not in _direct_targets(s), f"({s},{e}) 是一站直连"

    trials = []
    for i, (s, e) in enumerate(raw, 1):
        trials.append({
            "id": f"E-{i:02d}", "phase": "E",
            "start": s, "end": e,
            "grid_distance": _grid_distance(s, e),
        })
    return trials


# ============================================================
# 伪随机 — 阶段内约束
# ============================================================

def pseudo_shuffle(trials: List[Dict[str, Any]],
                   key_fn,
                   max_consecutive: int,
                   max_attempts: int = 5000,
                   rng: Optional[random.Random] = None) -> List[Dict[str, Any]]:
    if rng is None:
        rng = random.Random()
    items = list(trials)
    for _ in range(max_attempts):
        rng.shuffle(items)
        ok = True
        run = 1
        for i in range(1, len(items)):
            if key_fn(items[i]) == key_fn(items[i - 1]):
                run += 1
                if run > max_consecutive:
                    ok = False
                    break
            else:
                run = 1
        if ok:
            return items
    return items


def build_full_trial_list(seed: Optional[int] = None) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    B = pseudo_shuffle(build_phase_B(), key_fn=lambda t: t["true_answer"],
                       max_consecutive=3, rng=rng)
    D = pseudo_shuffle(build_phase_D(), key_fn=lambda t: t["category"],
                       max_consecutive=2, rng=rng)
    E = pseudo_shuffle(build_phase_E(), key_fn=lambda t: t["start"],
                       max_consecutive=2, rng=rng)

    out: List[Dict[str, Any]] = []
    out.append({"phase": "intro", "id": "intro_B", "phase_name": "B"})
    out.extend(B)
    out.append({"phase": "intro", "id": "intro_D", "phase_name": "D"})
    out.extend(D)
    out.append({"phase": "intro", "id": "intro_E", "phase_name": "E"})
    out.extend(E)
    out.append({"phase": "end", "id": "end"})
    return out


# ============================================================
# 数据保存
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data", "tail_task")
os.makedirs(DATA_DIR, exist_ok=True)


def save_session(subject_id: str, started_at: float,
                 trial_list: List[Dict[str, Any]],
                 responses: List[Dict[str, Any]]) -> Tuple[str, str]:
    ts = time.strftime("%Y%m%d_%H%M%S", time.localtime(started_at))
    sid = subject_id.strip() or "anon"
    base = f"{sid}_{ts}"
    json_path = os.path.join(DATA_DIR, base + ".json")
    csv_path = os.path.join(DATA_DIR, base + ".csv")

    payload = {
        "subject_id": sid,
        "started_at": started_at,
        "ended_at": time.time(),
        "graph_version": "NC_MIX_TASK / graph9 (3x3 grid + 快速巴士 1-3-9-7-1; keys Q/E/A/D/W)",
        "lines": {k: v for k, v in LINES.items()},
        "trial_list": trial_list,
        "responses": responses,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    fieldnames = [
        "subject_id", "trial_index", "trial_id", "phase", "category",
        "stimulus", "response", "confidence", "rt_ms", "true_answer",
        "is_correct",
    ]
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in responses:
            w.writerow({
                "subject_id": sid,
                "trial_index": r.get("trial_index"),
                "trial_id": r.get("trial_id"),
                "phase": r.get("phase"),
                "category": r.get("category", ""),
                "stimulus": r.get("stimulus", ""),
                "response": r.get("response", ""),
                "confidence": r.get("confidence", ""),
                "rt_ms": r.get("rt_ms", ""),
                "true_answer": r.get("true_answer", ""),
                "is_correct": r.get("is_correct", ""),
            })
    return json_path, csv_path


# ============================================================
# Flask
# ============================================================

app = Flask(__name__, static_folder=os.path.join(BASE_DIR, "static"))
app.secret_key = "tail_task_ncmix_secret_2026"

SESSION: Dict[str, Any] = {
    "subject_id": "",
    "started_at": 0.0,
    "trial_list": [],
    "trial_index": 0,
    "responses": [],
}


def _node_payload(nid: int) -> Dict[str, Any]:
    n = NODES[nid]
    return {
        "id": nid,
        "name": n["name"],
        "ch": n["ch"],
        "color": n["color"],
        "shape": n["shape"],
    }


def _serialize_trial_for_client(t: Dict[str, Any]) -> Dict[str, Any]:
    phase = t.get("phase")
    if phase == "intro":
        intros = {
            "B": {
                "title": "阶段 B · 两个车站间多容易到达（共 36 题）",
                "body": (
                    "你将看到 36 对车站。\n"
                    "请回答：**这两个车站之间多容易到达？**\n\n"
                    "请凭直觉用 1–5 进行评价：\n"
                    "  ①  非常难到达\n"
                    "  ②  比较难到达\n"
                    "  ③  一般\n"
                    "  ④  比较容易到达\n"
                    "  ⑤  非常容易到达"
                ),
            },
            "D": {
                "title": "阶段 D · 动作组整体性评分（共 20 题）",
                "body": (
                    "你将看到 20 段动作序列：仅展示起点与终点车站，\n中间过程仅以动作箭头拼接（中间车站不显示）。\n"
                    "箭头颜色对应交通线路；同一线路下：\n"
                    "  · **实线** = 正向（公交 E / 地铁 D / 快速巴士 W）\n"
                    "  · **虚线** = 反向（公交 Q / 地铁 A）\n\n"
                    "请用 1–5 评价：**以下动作组在你眼里多大程度上可以构成一个整体？**\n\n"
                    "  ①  完全不像一个整体\n"
                    "  ②  比较松散\n"
                    "  ③  一般\n"
                    "  ④  比较像一个整体\n"
                    "  ⑤  完全像一个整体（脱口而出）"
                ),
            },
            "E": {
                "title": "阶段 E · 中转车站（共 20 题）",
                "body": (
                    "你将看到一对 (起点, 终点) 车站，二者之间距离较远。\n\n"
                    "请回答：**你脑子里最先想到要先经过的中间车站**是哪个？\n"
                    "（从起讫之外的 7 个站里挑 1 个）"
                ),
            },
        }
        info = intros[t["phase_name"]]
        return {"kind": "intro", "title": info["title"], "body": info["body"]}

    if phase == "end":
        return {"kind": "end"}

    if phase == "B":
        a, b = t["a"], t["b"]
        if random.random() < 0.5:
            a, b = b, a
        return {
            "kind": "trial_B",
            "trial_id": t["id"],
            "left": _node_payload(a),
            "right": _node_payload(b),
        }

    if phase == "D":
        return {
            "kind": "trial_D",
            "trial_id": t["id"],
            "sequence": [_node_payload(n) for n in t["sequence"]],
            "actions": t["actions"],
            "category": t["category"],
        }

    if phase == "E":
        s, e = t["start"], t["end"]
        candidates = [n for n in ALL_NODE_IDS if n not in (s, e)]
        random.shuffle(candidates)
        return {
            "kind": "trial_E",
            "trial_id": t["id"],
            "start": _node_payload(s),
            "end": _node_payload(e),
            "candidates": [_node_payload(n) for n in candidates],
        }
    return {"kind": "unknown"}


# ------------------------------------------------------------
# Routes
# ------------------------------------------------------------

@app.route("/")
def index():
    return render_template_string(HTML_PAGE)


@app.route("/api/start", methods=["POST"])
def api_start():
    data = request.get_json(force=True) or {}
    subject_id = (data.get("subject_id") or "").strip()
    seed = data.get("seed")
    SESSION["subject_id"] = subject_id
    SESSION["started_at"] = time.time()
    SESSION["trial_list"] = build_full_trial_list(seed=seed)
    SESSION["trial_index"] = 0
    SESSION["responses"] = []
    return _next_payload()


@app.route("/api/respond", methods=["POST"])
def api_respond():
    data = request.get_json(force=True) or {}
    idx = SESSION["trial_index"]
    if idx >= len(SESSION["trial_list"]):
        return jsonify({"kind": "end"})

    t = SESSION["trial_list"][idx]
    phase = t.get("phase")
    rt_ms = data.get("rt_ms")

    record: Dict[str, Any] = {
        "trial_index": idx,
        "trial_id": t.get("id"),
        "phase": phase,
        "rt_ms": rt_ms,
    }

    if phase == "B":
        # 5 级 Likert（多容易到达），无置信评分；记录真值距离便于事后分析
        resp = int(data.get("response"))    # 1..5
        record.update({
            "category": t["category"],
            "stimulus": f"{t['a']}<->{t['b']}",
            "response": resp,
            "confidence": "",
            "true_answer": t["true_answer"],
            "is_correct": "",
        })
    elif phase == "D":
        # 5 级 Likert（整体性），无对错
        resp = int(data.get("response"))    # 1..5
        seq_str = "->".join(str(n) for n in t["sequence"])
        record.update({
            "category": t["category"],
            "stimulus": seq_str,
            "response": resp,
            "confidence": "",
            "true_answer": "",
            "is_correct": "",
        })
    elif phase == "E":
        chosen = int(data.get("chosen"))
        record.update({
            "category": "E",
            "stimulus": f"{t['start']}->{t['end']}",
            "response": chosen,
            "confidence": "",
        })

    SESSION["responses"].append(record)
    SESSION["trial_index"] += 1
    return _next_payload()


@app.route("/api/finish", methods=["POST"])
def api_finish():
    json_path, csv_path = save_session(
        SESSION["subject_id"], SESSION["started_at"],
        SESSION["trial_list"], SESSION["responses"],
    )
    return jsonify({
        "saved": True,
        "json_path": os.path.relpath(json_path, BASE_DIR),
        "csv_path": os.path.relpath(csv_path, BASE_DIR),
    })


def _next_payload():
    idx = SESSION["trial_index"]
    total = len(SESSION["trial_list"])
    if idx >= total:
        return jsonify({"kind": "end"})

    t = SESSION["trial_list"][idx]
    payload = _serialize_trial_for_client(t)

    if t.get("phase") in ("B", "D", "E"):
        phase = t["phase"]
        same_phase_total = sum(1 for x in SESSION["trial_list"] if x.get("phase") == phase)
        same_phase_done = sum(1 for x in SESSION["trial_list"][:idx] if x.get("phase") == phase)
        payload["progress"] = {
            "phase": phase,
            "current": same_phase_done + 1,
            "total": same_phase_total,
        }

    return jsonify(payload)


# ============================================================
# 内嵌 HTML（沿用 NC_MIX_TASK 视觉风格：彩色形状 + 彩色箭头）
# ============================================================

HTML_PAGE = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>认知地图实验 · 尾部任务</title>
<style>
  :root {
    --bus-color: #3CA0FF;       /* 公交主色（双向边整体） */
    --bus-q-color: #1E5FE6;     /* 公交Q (前, 向左) 深蓝 */
    --bus-e-color: #6FA8FF;     /* 公交E (后, 向右) 浅蓝 */
    --subway-color: #50C878;    /* 地铁主色 */
    --subway-a-color: #2E9F4A;  /* 地铁A (前, 向上) 深绿 */
    --subway-d-color: #6BD884;  /* 地铁D (后, 向下) 浅绿 */
    --rapidbus-color: #C84BD8;  /* 快速巴士W (4 角顺时针单向) 紫/品红 */
    --bg: #1f232c;
    --panel: #2a2f3a;
    --panel-light: #353b48;
    --border: #4a5160;
    --text: #e8ebf2;
    --text-dim: #a8aebb;
    --accent: #5d8eff;
  }
  * { box-sizing: border-box; }
  body { background: var(--bg); color: var(--text); margin: 0;
         font-family: "Microsoft YaHei", "PingFang SC", "Helvetica", sans-serif;
         min-height: 100vh; }
  .container { max-width: 820px; margin: 28px auto; padding: 28px;
               background: var(--panel); border-radius: 14px;
               border: 1px solid var(--border);
               box-shadow: 0 4px 18px rgba(0,0,0,0.4); }
  h2 { margin: 0 0 18px; color: var(--text); }
  .progress { color: var(--text-dim); font-size: 0.88em; margin-bottom: 10px; }
  .question { font-size: 1.1em; line-height: 1.7; margin: 14px 0 22px;
              color: var(--text); }
  .legend-bar { position: fixed; bottom: 0; left: 0; right: 0;
                background: var(--panel); border-top: 1px solid var(--border);
                padding: 10px 24px; display: flex; gap: 24px; justify-content: center;
                font-size: 0.92em; color: var(--text-dim); z-index: 10; }
  .legend-item { display: inline-flex; align-items: center; gap: 8px; }
  .legend-line { width: 32px; height: 4px; border-radius: 2px; display: inline-block; }
  .container { margin-bottom: 80px; }

  /* 节点形状 */
  .node-shape { display: inline-flex; align-items: center; justify-content: center;
                 vertical-align: middle; }
  .node-shape svg { display: block; }
  .node-pair { font-size: 1.4em; text-align: center; margin: 30px 0;
               display: flex; align-items: center; justify-content: center; gap: 30px; }
  .node-pair .arrow { color: var(--text-dim); font-size: 1.2em; }
  .node-with-name { display: inline-flex; flex-direction: column;
                    align-items: center; gap: 6px; }
  .node-with-name .nm { font-size: 0.78em; color: var(--text-dim); }

  /* 4 选 1 / Likert 选项按钮 */
  .opts { display: flex; flex-direction: column; gap: 10px; margin: 16px 0 22px; }
  .opt-btn { padding: 13px 16px; border: 2px solid var(--border); border-radius: 10px;
             background: var(--panel-light); color: var(--text); cursor: pointer;
             font-size: 1em; text-align: left; transition: all 0.12s;
             display: flex; align-items: center; gap: 12px; }
  .opt-btn:hover { border-color: var(--accent); background: #404758; }
  .opt-btn.selected { border-color: var(--accent); background: #3a4a72;
                      box-shadow: 0 0 0 2px rgba(93,142,255,0.35); }
  .opt-btn .badge { display: inline-block; min-width: 22px; text-align: center;
                    font-weight: 700; }
  .opt-btn .arrow-demo { display: inline-block; vertical-align: middle; }

  /* 置信度 */
  .conf-wrap { text-align: center; margin: 14px 0 8px; }
  .conf-wrap .lbl { color: var(--text-dim); font-size: 0.92em; margin-bottom: 8px; }
  .conf-row { display: flex; justify-content: center; gap: 8px; }
  .conf-btn { width: 46px; height: 46px; border: 2px solid var(--border);
              border-radius: 50%; background: var(--panel-light); color: var(--text);
              font-weight: 700; cursor: pointer; font-size: 1em; }
  .conf-btn:hover { border-color: var(--accent); }
  .conf-btn.selected { background: var(--accent); border-color: var(--accent); color: #fff; }
  .conf-ends { display: flex; justify-content: space-between;
               width: 320px; margin: 6px auto 0; color: var(--text-dim);
               font-size: 0.78em; }

  /* 序列 (Phase D) */
  .seq-display { text-align: center; padding: 28px 12px; margin: 18px 0;
                 background: #232732; border: 1px solid var(--border);
                 border-radius: 12px; display: flex; flex-wrap: wrap;
                 align-items: center; justify-content: center; gap: 4px; }

  /* Phase E 候选 */
  .se-display { text-align: center; margin: 18px 0 22px;
                display: flex; align-items: center; justify-content: center;
                gap: 28px; padding: 18px;
                background: #232732; border: 1px solid var(--border);
                border-radius: 12px; }
  .candidate-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
                    margin: 14px 0; }
  .candidate-btn { padding: 14px 6px; border: 2px solid var(--border);
                   border-radius: 10px; background: var(--panel-light);
                   color: var(--text); cursor: pointer;
                   display: flex; flex-direction: column; align-items: center; gap: 6px;
                   font-size: 0.86em; }
  .candidate-btn:hover { border-color: var(--accent); background: #404758; }
  .candidate-btn.selected { border-color: var(--accent); background: #3a4a72;
                            box-shadow: 0 0 0 2px rgba(93,142,255,0.35); }

  .submit-row { text-align: center; margin-top: 24px; }
  .btn-primary { background: var(--accent); color: #fff; border: none;
                  padding: 12px 36px; border-radius: 10px; font-size: 1.05em;
                  cursor: pointer; font-weight: 600; }
  .btn-primary:hover { background: #4a7ce8; }
  .btn-primary:disabled { background: #555a68; cursor: not-allowed; }

  .intro-body { white-space: pre-wrap; line-height: 1.8; padding: 22px;
                background: #232732; border: 1px solid var(--border);
                border-radius: 10px; font-size: 1em; }
  .end-screen { text-align: center; padding: 50px 20px; }
  .end-screen h2 { color: #6ad99e; }
  .file-path { font-family: monospace; color: var(--text-dim);
               background: #232732; padding: 6px 10px; border-radius: 4px;
               display: inline-block; margin: 4px 0; }

  #subject-id { padding: 10px 14px; font-size: 1em; width: 280px;
                background: var(--panel-light); border: 1px solid var(--border);
                border-radius: 8px; color: var(--text); }
</style>
</head>
<body>

<div id="start-screen" class="container" style="text-align:center;">
  <h2>🧭 认知地图实验 · 尾部任务</h2>
  <p style="color: var(--text-dim); margin: 18px 0;">
    请输入被试编号后开始。本任务约 22–25 分钟。
  </p>
  <input id="subject-id" placeholder="被试编号（如 P001）">
  <div style="margin-top: 22px;">
    <button class="btn-primary" onclick="startTask()">开始 →</button>
  </div>
</div>

<div id="trial-screen" class="container" style="display:none;"></div>

<div id="legend" class="legend-bar" style="display:none;">
  <span class="legend-item"><span class="legend-line" style="background:#1E5FE6;"></span>公交 Q</span>
  <span class="legend-item"><span class="legend-line" style="background:#6FA8FF;"></span>公交 E</span>
  <span class="legend-item"><span class="legend-line" style="background:#2E9F4A;"></span>地铁 A</span>
  <span class="legend-item"><span class="legend-line" style="background:#6BD884;"></span>地铁 D</span>
  <span class="legend-item"><span class="legend-line" style="background:#C84BD8;"></span>快速巴士 W</span>
</div>

<script>
// ────────────────────────────────────────────────
// 节点形状 SVG 渲染（与 NC_MIX_TASK common/station_names.py 对齐）
// ────────────────────────────────────────────────
function shapeSvg(shape, color, size=36) {
  const s = size, h = s/2;
  const cx = h, cy = h;
  let inner = '';
  switch(shape) {
    case 'triangle':
      inner = `<polygon points="${cx},2 ${s-2},${s-4} 2,${s-4}" fill="${color}"/>`;
      break;
    case 'square':
      const k = s*0.78, off = (s-k)/2;
      inner = `<rect x="${off}" y="${off}" width="${k}" height="${k}" fill="${color}"/>`;
      break;
    case 'circle':
      inner = `<circle cx="${cx}" cy="${cy}" r="${h-3}" fill="${color}"/>`;
      break;
    case 'diamond':
      inner = `<polygon points="${cx},2 ${s-2},${cy} ${cx},${s-2} 2,${cy}" fill="${color}"/>`;
      break;
    case 'star': {
      const pts = [];
      const oR = h-3, iR = oR*0.4;
      for (let i=0; i<10; i++) {
        const ang = -Math.PI/2 + i*Math.PI/5;
        const r = (i%2===0) ? oR : iR;
        pts.push(`${cx + r*Math.cos(ang)},${cy + r*Math.sin(ang)}`);
      }
      inner = `<polygon points="${pts.join(' ')}" fill="${color}"/>`;
      break;
    }
    case 'hexagon': {
      const r = h-3, pts = [];
      for (let i=0;i<6;i++) {
        const ang = -Math.PI/6 + i*Math.PI/3;
        pts.push(`${cx + r*Math.cos(ang)},${cy + r*Math.sin(ang)}`);
      }
      inner = `<polygon points="${pts.join(' ')}" fill="${color}"/>`;
      break;
    }
    case 'cross': {
      const arm = Math.max(2, s*0.18);
      inner = `<rect x="${cx-arm}" y="2" width="${arm*2}" height="${s-4}" fill="${color}"/>` +
              `<rect x="2" y="${cy-arm}" width="${s-4}" height="${arm*2}" fill="${color}"/>`;
      break;
    }
    case 'inv_triangle':
      inner = `<polygon points="${cx},${s-2} ${s-2},4 2,4" fill="${color}"/>`;
      break;
    case 'pentagon': {
      const r = h-3, pts = [];
      for (let i=0;i<5;i++) {
        const ang = -Math.PI/2 + i*2*Math.PI/5;
        pts.push(`${cx + r*Math.cos(ang)},${cy + r*Math.sin(ang)}`);
      }
      inner = `<polygon points="${pts.join(' ')}" fill="${color}"/>`;
      break;
    }
    default:
      inner = `<circle cx="${cx}" cy="${cy}" r="${h-3}" fill="${color}"/>`;
  }
  return `<svg width="${s}" height="${s}" viewBox="0 0 ${s} ${s}">${inner}</svg>`;
}

function nodeBlock(node, size=42, withName=false) {
  // 仅保留形状图标，不再显示站名文本（withName 参数保留以兼容调用，实际用不上）
  const svg = shapeSvg(node.shape, node.color, size);
  return `<span class="node-with-name"><span class="node-shape">${svg}</span></span>`;
}

function nodeInline(node, size=28) {
  return `<span class="node-shape">${shapeSvg(node.shape, node.color, size)}</span>`;
}

// 渲染动作序列：仅显示箭头，不显示中间节点图标，也不在箭头上标文字。
// 同一线路用同一颜色；**实线 = 正向**（公交 E / 地铁 D / 快速巴士 W），
// **虚线 = 反向**（公交 Q / 地铁 A）。
const LINE_COLORS = {
  bus_q:      '#3CA0FF',  // 公交 (反向 虚线)
  bus_e:      '#3CA0FF',  // 公交 (正向 实线)
  subway_a:   '#50C878',  // 地铁 (反向 虚线)
  subway_d:   '#50C878',  // 地铁 (正向 实线)
  rapidbus_w: '#C84BD8',  // 快速巴士W (单向 实线)
};
const REVERSE_ACTIONS = new Set(['bus_q', 'subway_a']);
const DIRECTED_ACTIONS = new Set(['rapidbus_w']);

function sequenceHTML(nodes, actions) {
  // 仅在两端显示起点与终点节点，中间只用动作箭头拼接（不显示中间节点与文字）。
  let html = '';
  if (nodes && nodes.length > 0) {
    html += `<span style="display:inline-flex;align-items:center;margin:0 6px;">${nodeBlock(nodes[0], 48)}</span>`;
  }
  for (let i = 0; i < actions.length; i++) {
    const ln = actions[i];
    const directed = DIRECTED_ACTIONS.has(ln);
    const dashed = REVERSE_ACTIONS.has(ln);
    const color = LINE_COLORS[ln] || '#888';
    html += `<span style="display:inline-flex;align-items:center;margin:0 6px;">
               ${arrowSvg(color, directed, 90, 24, dashed)}
             </span>`;
  }
  if (nodes && nodes.length > 1) {
    html += `<span style="display:inline-flex;align-items:center;margin:0 6px;">${nodeBlock(nodes[nodes.length - 1], 48)}</span>`;
  }
  return html;
}

// 彩色箭头 SVG：dashed=true 用虚线表示反向；directed=true 则仅右端箭头。
function arrowSvg(color, directed, w=64, h=22, dashed=false) {
  const y = h/2;
  const lineX1 = directed ? 4 : 10;
  const lineX2 = w - 10;
  let leftHead = '';
  if (!directed) {
    leftHead = `<polygon points="4,${y} 14,${y-6} 14,${y+6}" fill="${color}"/>`;
  }
  const rightHead = `<polygon points="${w-4},${y} ${w-14},${y-6} ${w-14},${y+6}" fill="${color}"/>`;
  const dashAttr = dashed ? ' stroke-dasharray="6 4"' : '';
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
    <line x1="${lineX1}" y1="${y}" x2="${lineX2}" y2="${y}" stroke="${color}" stroke-width="4"${dashAttr}/>
    ${leftHead}${rightHead}
  </svg>`;
}

function arrowBlock(line, color, label, directed) {
  return `<span class="node-with-name">
    <span>${arrowSvg(color, directed)}</span>
    <span class="nm" style="color:${color};">${label}</span>
  </span>`;
}

// ────────────────────────────────────────────────
// 主流程
// ────────────────────────────────────────────────
let currentPayload = null;
let trialStart = 0;
let selectedResponse = null;
let selectedConfidence = null;

async function startTask() {
  const sid = document.getElementById("subject-id").value.trim();
  if (!sid) { alert("请输入被试编号"); return; }
  const r = await fetch("/api/start", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({subject_id: sid})
  });
  const payload = await r.json();
  document.getElementById("start-screen").style.display = "none";
  document.getElementById("trial-screen").style.display = "block";
  document.getElementById("legend").style.display = "flex";
  render(payload);
}

function render(payload) {
  currentPayload = payload;
  selectedResponse = null;
  selectedConfidence = null;
  trialStart = performance.now();
  const root = document.getElementById("trial-screen");

  if (payload.kind === "intro") {
    root.innerHTML = `
      <h2>${payload.title}</h2>
      <div class="intro-body">${escapeHtml(payload.body)}</div>
      <div class="submit-row">
        <button class="btn-primary" onclick="submitIntro()">开始本阶段 →</button>
      </div>`;
    return;
  }
  if (payload.kind === "end") { finish(); return; }

  const prog = payload.progress
    ? `阶段 ${payload.progress.phase} · 第 ${payload.progress.current} / ${payload.progress.total} 题`
    : "";

  if (payload.kind === "trial_B") {
    root.innerHTML = `
      <div class="progress">${prog}</div>
      <div class="node-pair">
        ${nodeBlock(payload.left, 64, false)}
        <span class="arrow">↔</span>
        ${nodeBlock(payload.right, 64, false)}
      </div>
      <div class="question"><b>这两个车站之间多容易到达？</b></div>
      <div class="opts" id="opts">
        <div class="opt-btn" data-v="1"><span class="badge">①</span> 非常难到达</div>
        <div class="opt-btn" data-v="2"><span class="badge">②</span> 比较难到达</div>
        <div class="opt-btn" data-v="3"><span class="badge">③</span> 一般</div>
        <div class="opt-btn" data-v="4"><span class="badge">④</span> 比较容易到达</div>
        <div class="opt-btn" data-v="5"><span class="badge">⑤</span> 非常容易到达</div>
      </div>
      ${submitHTML()}`;
    bindOpts("opts", v => { selectedResponse = parseInt(v); selectedConfidence = 0; });
    return;
  }

  if (payload.kind === "trial_D") {
    root.innerHTML = `
      <div class="progress">${prog}</div>
      <div class="question">以下动作组在你眼里<b>多大程度上可以构成一个整体</b>？</div>
      <div class="seq-display">${sequenceHTML(payload.sequence, payload.actions)}</div>
      <div class="opts" id="opts">
        <div class="opt-btn" data-v="1"><span class="badge">①</span> 完全不像一个整体</div>
        <div class="opt-btn" data-v="2"><span class="badge">②</span> 比较松散</div>
        <div class="opt-btn" data-v="3"><span class="badge">③</span> 一般</div>
        <div class="opt-btn" data-v="4"><span class="badge">④</span> 比较像一个整体</div>
        <div class="opt-btn" data-v="5"><span class="badge">⑤</span> 完全像一个整体（脱口而出）</div>
      </div>
      ${submitHTML()}`;
    bindOpts("opts", v => { selectedResponse = parseInt(v); selectedConfidence = 0; });
    return;
  }

  if (payload.kind === "trial_E") {
    const candHtml = payload.candidates.map(c =>
      `<div class="candidate-btn" data-v="${c.id}">
         ${nodeInline(c, 44)}
       </div>`
    ).join("");
    root.innerHTML = `
      <div class="progress">${prog}</div>
      <div class="question">现在让你立刻从<b>起点</b>出发去<b>终点</b>。<br>
        你脑子里<b>最先想到要先经过</b>的中间车站是哪个？（只挑 1 个）
      </div>
      <div class="se-display">
        ${nodeBlock(payload.start, 64, false)}
        <span class="arrow" style="font-size:1.6em; color: var(--text-dim);">→</span>
        ${nodeBlock(payload.end, 64, false)}
      </div>
      <div class="candidate-grid" id="opts">${candHtml}</div>
      ${submitHTML()}`;
    bindOpts("opts", v => { selectedResponse = parseInt(v); selectedConfidence = 0; });
    return;
  }
}

function confHTML() {
  return `
    <div class="conf-wrap">
      <div class="lbl">你的把握程度</div>
      <div class="conf-row" id="conf">
        ${[1,2,3,4,5].map(i => `<button class="conf-btn" data-v="${i}">${i}</button>`).join("")}
      </div>
      <div class="conf-ends"><span>1 = 没把握</span><span>5 = 非常确定</span></div>
    </div>`;
}
function submitHTML() {
  return `<div class="submit-row">
    <button id="submit-btn" class="btn-primary" disabled onclick="submitTrial()">提交</button>
  </div>`;
}
function bindOpts(id, cb) {
  const root = document.getElementById(id);
  root.querySelectorAll(".opt-btn, .candidate-btn").forEach(btn => {
    btn.onclick = () => {
      root.querySelectorAll(".opt-btn, .candidate-btn").forEach(b => b.classList.remove("selected"));
      btn.classList.add("selected");
      cb(btn.dataset.v);
      maybeEnableSubmit();
    };
  });
}
function bindConf() {
  document.querySelectorAll("#conf .conf-btn").forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll("#conf .conf-btn").forEach(b => b.classList.remove("selected"));
      btn.classList.add("selected");
      selectedConfidence = parseInt(btn.dataset.v);
      maybeEnableSubmit();
    };
  });
}
function maybeEnableSubmit() {
  const btn = document.getElementById("submit-btn");
  if (!btn) return;
  // 所有阶段均不再要求置信评分，仅需选择响应。
  btn.disabled = (selectedResponse === null);
}

async function submitTrial() {
  const rt_ms = Math.round(performance.now() - trialStart);
  const body = { rt_ms };
  if (currentPayload.kind === "trial_B") {
    body.response = selectedResponse;
  } else if (currentPayload.kind === "trial_D") {
    body.response = selectedResponse;
  } else if (currentPayload.kind === "trial_E") {
    body.chosen = selectedResponse;
  }
  const r = await fetch("/api/respond", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body)
  });
  render(await r.json());
}

async function submitIntro() {
  const r = await fetch("/api/respond", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({})
  });
  render(await r.json());
}

async function finish() {
  const r = await fetch("/api/finish", {method: "POST"});
  const info = await r.json();
  document.getElementById("trial-screen").innerHTML = `
    <div class="end-screen">
      <h2>✅ 全部完成，谢谢你的参与！</h2>
      <p style="color: var(--text-dim); margin-top: 16px;">数据已保存：</p>
      <div class="file-path">${info.json_path}</div><br>
      <div class="file-path">${info.csv_path}</div>
    </div>`;
}

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
</script>
</body>
</html>
"""


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  尾部任务 (Tail Task · NC_MIX_TASK aligned) 启动中...")
    print(f"  数据目录: {DATA_DIR}")
    print("  访问:    http://127.0.0.1:5001")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5001, debug=False)
