"""
Navigation6 认知地图可视化：生成三张 SVG（状态图几何布局、谱嵌入、特征值条形图）。
优化：几何/谱布局减少重叠、标题与图例说明、按 N 动态调整画布与标签策略；中文字体修复。
无中文字体环境（如部分 Linux）下标题/图例可能显示为方框，可安装 Noto Sans CJK SC 或系统中文字体。需要 matplotlib。
"""
from __future__ import annotations

import io
import os
from typing import Any, Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.font_manager as fm
import numpy as np

# 中文字体：优先使用系统支持中文的字体，避免标题/图例显示为方框；含 CJK 回退
def _get_chinese_font_name() -> Optional[str]:
    candidates = (
        "Microsoft YaHei", "SimHei", "SimSun", "KaiTi", "FangSong",
        "Noto Sans CJK SC", "Noto Sans CJK TC", "WenQuanYi Micro Hei",
    )
    try:
        for name in candidates:
            for f in fm.fontManager.ttflist:
                if f.name == name:
                    return name
    except Exception:
        pass
    return None

_chinese_font_name = _get_chinese_font_name()
if _chinese_font_name:
    plt.rcParams["font.sans-serif"] = [_chinese_font_name, "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def _chinese_font_properties(size: Optional[float] = None):
    """返回用于标题/图例等中文文本的 FontProperties。"""
    if _chinese_font_name and size is not None:
        return fm.FontProperties(family=_chinese_font_name, size=size)
    if _chinese_font_name:
        return fm.FontProperties(family=_chinese_font_name)
    return None

# 标签显示阈值：N<=LABEL_FULL_MAX 显示完整 (gx,gy)；LABEL_FULL_MAX < N <= LABEL_CODE_MAX 显示编号或抽样；N>LABEL_CODE_MAX 不标
LABEL_FULL_MAX = 25
LABEL_CODE_MAX = 50

NODE_COLORS = [
    "#ef4444", "#f59e0b", "#22c55e", "#3b82f6", "#a855f7", "#ec4899",
    "#06b6d4", "#84cc16", "#f97316", "#8b5cf6", "#14b8a6", "#e11d48",
    "#6366f1", "#10b981", "#d946ef", "#0ea5e9", "#facc15", "#fb923c",
]

EIGEN_COLORS = [
    "#16a34a", "#2563eb", "#9333ea", "#ea580c", "#dc2626",
    "#0891b2", "#db2777", "#65a30d",
]


def _fig_to_svg(fig: plt.Figure) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="svg", bbox_inches="tight", transparent=True)
    plt.close(fig)
    buf.seek(0)
    return buf.read().decode("utf-8")


def _scale_positions_to_box(x: np.ndarray, y: np.ndarray, half_side: float = 1.2) -> tuple:
    """将坐标缩放至约 [-half_side, half_side]，保持比例。"""
    if len(x) == 0:
        return x, y
    mx, Mx = x.min(), x.max()
    my, My = y.min(), y.max()
    rx = Mx - mx if Mx > mx else 1.0
    ry = My - my if My > my else 1.0
    r = max(rx, ry, 1e-8)
    cx = (mx + Mx) / 2
    cy = (my + My) / 2
    x2 = (x - cx) / r * half_side
    y2 = (y - cy) / r * half_side
    return x2, y2


def _apply_jitter(x: np.ndarray, y: np.ndarray, frac: float = 0.005) -> tuple:
    """对重复或近重合点加极小 jitter。"""
    rx = x.max() - x.min() if x.size else 1.0
    ry = y.max() - y.min() if y.size else 1.0
    r = max(rx, ry, 1e-8)
    rng = np.random.default_rng(42)
    jx = rng.uniform(-r * frac, r * frac, size=x.shape)
    jy = rng.uniform(-r * frac, r * frac, size=y.shape)
    return x + jx, y + jy


def render_all_plots(
    adj: np.ndarray,
    labels: List[str],
    eigenvalues: np.ndarray,
    eigenvectors: np.ndarray,
    highlight_nodes: Optional[List[int]] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """
    生成全部三张 SVG。

    Parameters
    ----------
    adj : (N, N) 邻接矩阵
    labels : 长度 N 的节点标签
    eigenvalues, eigenvectors : 拉普拉斯特征值/特征向量（下标 0..N-1）
    highlight_nodes : 可选，节点下标列表，在谱布局/谱嵌入图中高亮（如目标节点）
    meta : 可选，{n, components, target_code, map_name} 用于标题与说明

    Returns
    -------
    dict with keys: svg_original, svg_spectral, svg_eigenvalues
    """
    N = adj.shape[0]
    return {
        "svg_original": _draw_original_graph(
            adj, N, labels, eigenvectors, highlight_nodes=highlight_nodes, meta=meta
        ),
        # 默认谱嵌入：轻微 jitter 以避免完全重合
        "svg_spectral": _draw_spectral_embedding(
            adj,
            N,
            labels,
            eigenvalues,
            eigenvectors,
            highlight_nodes=highlight_nodes,
            meta=meta,
            spectral_layout="jitter",
        ),
        # 力导向“去重/排斥”：让重叠点在局部展开，但尽量贴近原谱坐标
        "svg_spectral_force": _draw_spectral_embedding(
            adj,
            N,
            labels,
            eigenvalues,
            eigenvectors,
            highlight_nodes=highlight_nodes,
            meta=meta,
            spectral_layout="force_dedup",
        ),
        "svg_eigenvalues": _draw_eigenvalue_bars(eigenvalues, meta=meta),
    }

def _force_dedup_positions(
    v2: np.ndarray,
    v3: np.ndarray,
    *,
    d_min: float,
    iterations: int = 80,
    r_clamp: float = 1.35,
    spring_factor: float = 0.18,
) -> tuple[np.ndarray, np.ndarray]:
    """
    简单力导向/约束松弛：让任意两点距离 >= d_min。
    同时用 spring_factor 把点拉回到初始坐标，避免整体漂移到完全不同形状。
    """
    pos0 = np.stack([v2, v3], axis=1).astype(float, copy=True)
    pos = pos0.copy()
    N = pos.shape[0]
    if N <= 1:
        return pos[:, 0], pos[:, 1]

    tiny = 1e-12
    two_pi = 2.0 * np.pi

    for _ in range(iterations):
        # pairwise relaxation
        for i in range(N):
            xi, yi = pos[i, 0], pos[i, 1]
            for j in range(i + 1, N):
                dx = xi - pos[j, 0]
                dy = yi - pos[j, 1]
                dist2 = dx * dx + dy * dy
                if dist2 >= d_min * d_min:
                    continue
                if dist2 <= tiny:
                    # 完全重合：给一个确定性方向，避免随机导致不可复现
                    angle = ((i * 37 + j * 17) % 997) / 997.0 * two_pi
                    ux, uy = np.cos(angle), np.sin(angle)
                    shift = (d_min * 0.5)
                    pos[i, 0] += ux * shift
                    pos[i, 1] += uy * shift
                    pos[j, 0] -= ux * shift
                    pos[j, 1] -= uy * shift
                    # 更新 xi/yi，减少下一次循环误差
                    xi, yi = pos[i, 0], pos[i, 1]
                    continue
                dist = float(np.sqrt(dist2))
                # overlap = d_min - dist，沿单位方向推开各一半
                overlap = (d_min - dist) * 0.5
                ux, uy = dx / dist, dy / dist
                pos[i, 0] += ux * overlap
                pos[i, 1] += uy * overlap
                pos[j, 0] -= ux * overlap
                pos[j, 1] -= uy * overlap
                xi, yi = pos[i, 0], pos[i, 1]

        # spring back：逐步回到初始谱位置（保持局部形状语义）
        pos = pos + spring_factor * (pos0 - pos)

        # clamp：防止跑出画布导致难看/文字遮挡
        pos[:, 0] = np.clip(pos[:, 0], -r_clamp, r_clamp)
        pos[:, 1] = np.clip(pos[:, 1], -r_clamp, r_clamp)

    return pos[:, 0], pos[:, 1]


def _draw_original_graph(
    adj: np.ndarray,
    N: int,
    labels: List[str],
    eigenvectors: np.ndarray,
    highlight_nodes: Optional[List[int]] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> str:
    """
    状态图：几何/拓扑布局（基于 (gx,gy) 坐标），展示任务空间的直观结构。

    注意：这里不再使用谱坐标，而是直接用 labels 中的 (gx,gy) 作为几何位置，
    再缩放到有限范围，以便与谱嵌入图形成互补视角。
    """
    fig_w = 6.0 if N > 30 else 4.0
    fig_h = 5.0 if N > 30 else 3.5
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_aspect("equal")
    ax.axis("off")

    # 从 label "(gx,gy)" 解析出几何坐标；解析失败时退化为顺序坐标
    gx_vals: List[float] = []
    gy_vals: List[float] = []
    for i, lab in enumerate(labels):
        try:
            inner = lab.strip().strip("()")
            sx, sy = inner.split(",")
            gx, gy = float(sx), float(sy)
        except Exception:
            gx, gy = float(i), 0.0
        gx_vals.append(gx)
        gy_vals.append(gy)
    xs = np.asarray(gx_vals, dtype=float)
    ys = np.asarray(gy_vals, dtype=float)
    pos_x, pos_y = _scale_positions_to_box(xs, ys, half_side=1.2)

    edge_alpha = 0.6 if N <= 30 else 0.15
    edge_lw = 1.0 if N <= 30 else (0.35 if N <= 50 else 0.25)
    for i in range(N):
        for j in range(i + 1, N):
            if adj[i, j]:
                ax.plot(
                    [pos_x[i], pos_x[j]], [pos_y[i], pos_y[j]],
                    color="#cbd5e1", alpha=edge_alpha, linewidth=edge_lw,
                    zorder=1,
                )

    node_size = 80 if N <= 20 else (30 if N <= 50 else 10)
    colors = []
    for i in range(N):
        if highlight_nodes and i in highlight_nodes:
            colors.append("#ef4444")
        else:
            colors.append(NODE_COLORS[i % len(NODE_COLORS)])
    ax.scatter(pos_x, pos_y, s=node_size, c=colors, edgecolors="#0f172a",
               linewidths=0.8 if N <= 50 else 0.3, zorder=2)

    # 标签策略
    if N <= LABEL_FULL_MAX:
        for i in range(N):
            dx = pos_x[i]
            dy = pos_y[i]
            norm = np.sqrt(dx * dx + dy * dy) or 1.0
            off = 10
            ax.annotate(
                labels[i], (pos_x[i], pos_y[i]),
                textcoords="offset points",
                xytext=(dx / norm * off, dy / norm * off),
                ha="center", va="center", fontsize=6, fontfamily="monospace",
                color="#334155",
            )
    elif N <= LABEL_CODE_MAX:
        step = max(1, N // 15)
        for i in range(N):
            if (highlight_nodes and i in highlight_nodes) or (i % step == 0):
                ax.annotate(
                    str(i + 1), (pos_x[i], pos_y[i]),
                    textcoords="offset points", xytext=(0, 6),
                    ha="center", fontsize=5, fontfamily="monospace",
                    color="#334155",
                )

    ax.set_xlim(-1.35, 1.35)
    ax.set_ylim(-1.35, 1.35)

    fp_title = _chinese_font_properties(11)
    fp_text = _chinese_font_properties(8)
    ax.set_title("状态图（几何布局）", fontsize=11, color="#334155",
                 fontproperties=fp_title if fp_title else None)
    if meta:
        parts = [f"N = {meta.get('n', N)}", f"连通分量 = {meta.get('components', '?')}"]
        if meta.get("target_code") is not None:
            parts.append(f"目标节点 = {meta['target_code']}")
        ax.text(0.5, -0.06, "，".join(parts), transform=ax.transAxes,
                ha="center", fontsize=8, color="#64748b",
                fontproperties=fp_text if fp_text else None)
    if highlight_nodes:
        from matplotlib.lines import Line2D
        leg = ax.legend(
            [Line2D([0], [0], marker="o", color="w", markerfacecolor="#ef4444", markersize=8)],
            ["目标节点"], loc="upper right", fontsize=8, framealpha=0.9,
            prop=(fp_text if fp_text else None),
        )
        leg.get_frame().set_edgecolor("#e2e8f0")

    return _fig_to_svg(fig)


def _draw_spectral_embedding(
    adj: np.ndarray,
    N: int,
    labels: List[str],
    eigenvalues: np.ndarray,
    eigenvectors: np.ndarray,
    highlight_nodes: Optional[List[int]] = None,
    meta: Optional[Dict[str, Any]] = None,
    spectral_layout: str = "jitter",
) -> str:
    """
    谱嵌入 (v2, v3)：每个节点一个点，反映谱几何结构。

    - 使用 v2, v3 作为坐标，并做轻微 jitter 以避免完全重合。
    - highlight_nodes 用颜色高亮（如目标节点）。
    - 不再进行簇级别的大圆合并，以保持谱图的标准语义。
    """
    fig_w = 6.0 if N > 30 else 5.5
    fig_h = 5.0 if N > 30 else 4.5
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    fp_title = _chinese_font_properties(11)
    fp_text = _chinese_font_properties(8)

    if N < 3 or eigenvectors.shape[1] < 2:
        ax.text(0.5, 0.5, "N < 3: spectral embedding not available",
                ha="center", va="center", fontsize=12, color="#999")
        ax.axis("off")
        return _fig_to_svg(fig)

    # 谱坐标
    v2 = eigenvectors[:, 1].astype(float).copy()
    v3 = eigenvectors[:, 2].astype(float).copy() if eigenvectors.shape[1] > 2 else np.zeros(N)
    v2, v3 = _scale_positions_to_box(v2, v3, half_side=1.2)

    # 避免重合/遮挡：两种可选布局策略
    if spectral_layout == "jitter":
        v2, v3 = _apply_jitter(v2, v3, frac=0.01)
        layout_name = "谱嵌入 (v₂, v₃)（jitter）"
    elif spectral_layout == "force_dedup":
        # 依据 N 粗略选择最小间距（单位是“缩放到 [-1.2, 1.2] 的坐标”）
        if N <= 20:
            d_min = 0.11
        elif N <= 50:
            d_min = 0.075
        else:
            d_min = 0.055
        # 先极小 jitter 破除完全重合，再做局部约束松弛
        v2, v3 = _apply_jitter(v2, v3, frac=0.002)
        v2, v3 = _force_dedup_positions(v2, v3, d_min=d_min, iterations=90, spring_factor=0.2)
        layout_name = "谱嵌入 (v₂, v₃)（力导向去重）"
    else:
        raise ValueError(f"未知 spectral_layout: {spectral_layout}")

    # 边：直接在点之间连线
    edge_alpha = 0.5 if N <= 30 else 0.12
    edge_lw = 0.8 if N <= 30 else 0.3
    for i in range(N):
        for j in range(i + 1, N):
            if adj[i, j]:
                ax.plot(
                    [v2[i], v2[j]], [v3[i], v3[j]],
                    color="#94a3b8", alpha=edge_alpha, linewidth=edge_lw,
                    zorder=1,
                )

    # 点：每个节点一个散点
    node_size = 80 if N <= 20 else (25 if N <= 50 else 8)
    colors = []
    for i in range(N):
        if highlight_nodes and i in highlight_nodes:
            colors.append("#ef4444")
        else:
            colors.append(NODE_COLORS[i % len(NODE_COLORS)])

    ax.scatter(v2, v3, s=node_size, c=colors, edgecolors="#0f172a",
               linewidths=0.8 if N <= 50 else 0.2, zorder=2)

    # 标签策略：小图可标 label，大图标编号/抽样
    if N <= LABEL_FULL_MAX:
        for i in range(N):
            ax.annotate(
                labels[i], (v2[i], v3[i]),
                textcoords="offset points", xytext=(0, 7),
                ha="center", fontsize=5.5, fontfamily="monospace",
                color="#334155",
            )
    elif N <= LABEL_CODE_MAX:
        step = max(1, N // 15)
        for i in range(N):
            if (highlight_nodes and i in highlight_nodes) or (i % step == 0):
                ax.annotate(
                    str(i + 1), (v2[i], v3[i]),
                    textcoords="offset points", xytext=(0, 6),
                    ha="center", fontsize=5, fontfamily="monospace",
                    color="#334155",
                )

    # 视口范围：稍微放大确保所有点都在图内
    if N > 0:
        margin = 0.1 * max(v2.max() - v2.min(), v3.max() - v3.min(), 1.0)
        ax.set_xlim(v2.min() - margin, v2.max() + margin)
        ax.set_ylim(v3.min() - margin, v3.max() + margin)

    ax.set_xlabel("v₂ →", fontsize=10, color="#94a3b8")
    ax.set_ylabel("v₃ →", fontsize=10, color="#94a3b8")
    ax.axhline(0, color="#f1f5f9", linewidth=0.5, zorder=0)
    ax.axvline(0, color="#f1f5f9", linewidth=0.5, zorder=0)
    ax.tick_params(labelsize=7, colors="#94a3b8")
    for spine in ax.spines.values():
        spine.set_color("#e2e8f0")
    ax.set_aspect("equal")

    ax.set_title(layout_name, fontsize=11, color="#334155",
                 fontproperties=fp_title if fp_title else None)
    if meta:
        parts = [f"N = {meta.get('n', N)}", f"连通分量 = {meta.get('components', '?')}"]
        if meta.get("target_code") is not None:
            parts.append(f"目标节点 = {meta['target_code']}")
        ax.text(0.5, -0.05, "，".join(parts), transform=ax.transAxes,
                ha="center", fontsize=8, color="#64748b",
                fontproperties=fp_text if fp_text else None)
    if highlight_nodes:
        from matplotlib.lines import Line2D
        leg = ax.legend(
            [Line2D([0], [0], marker="o", color="w", markerfacecolor="#ef4444", markersize=8)],
            ["目标节点"], loc="upper right", fontsize=8, framealpha=0.9,
            prop=(fp_text if fp_text else None),
        )
        leg.get_frame().set_edgecolor("#e2e8f0")

    return _fig_to_svg(fig)


def _draw_eigenvalue_bars(eigenvalues: np.ndarray, meta: Optional[Dict[str, Any]] = None) -> str:
    """拉普拉斯特征值条形图；标题与说明。"""
    count = min(len(eigenvalues), 12)
    vals = eigenvalues[:count]
    max_val = max(np.abs(vals).max(), 0.01)

    fig_w = 3.5
    fig_h = max(1.4, count * 0.28)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))

    y_pos = np.arange(count)[::-1]
    bar_widths = np.abs(vals)
    colors = [EIGEN_COLORS[i % len(EIGEN_COLORS)] for i in range(count)]

    ax.barh(y_pos, bar_widths, height=0.6, color=colors, edgecolor="none")

    for i in range(count):
        ax.text(
            -max_val * 0.02, y_pos[i],
            f"λ{i + 1} = {vals[i]:.4f}",
            ha="right", va="center", fontsize=7, fontfamily="monospace",
            color="#334155",
        )

    ax.set_xlim(-max_val * 0.55, max_val * 1.1)
    ax.set_yticks([])
    ax.set_xticks([])
    ax.axis("off")

    fp_title = _chinese_font_properties(11)
    fp_text = _chinese_font_properties(8)
    ax.set_title("拉普拉斯特征值", fontsize=11, color="#334155",
                 fontproperties=fp_title if fp_title else None)
    cap = "前 12 个特征值（λ₁=0 的个数 = 连通分量数）"
    if meta and meta.get("components") is not None:
        cap += f"；连通分量 = {meta['components']}"
    ax.text(0.5, -0.12, cap, transform=ax.transAxes, ha="center", fontsize=8, color="#64748b",
            fontproperties=fp_text if fp_text else None)

    if len(eigenvalues) > count:
        ax.text(
            0.5, -0.28, f"... 共 {len(eigenvalues)} 个特征值",
            transform=ax.transAxes, fontsize=7, color="#94a3b8", ha="center",
            fontproperties=fp_text if fp_text else None,
        )

    return _fig_to_svg(fig)


def save_plots_to_dir(
    svg_dict: Dict[str, str],
    output_dir: str,
    basename: str = "cogmap",
) -> List[str]:
    """
    将三张 SVG 写入目录。文件名：{basename}_original.svg, _spectral.svg, _eigenvalues.svg。

    Returns
    -------
    写入的绝对路径列表。
    """
    os.makedirs(output_dir, exist_ok=True)
    paths = []
    for key, suffix in [
        ("svg_original", "original"),
        ("svg_spectral", "spectral"),
        ("svg_spectral_force", "spectral_force"),
        ("svg_eigenvalues", "eigenvalues"),
    ]:
        if key not in svg_dict:
            continue
        p = os.path.join(output_dir, f"{basename}_{suffix}.svg")
        with open(p, "w", encoding="utf-8") as f:
            f.write(svg_dict[key])
        paths.append(os.path.abspath(p))
    return paths
