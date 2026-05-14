#!/usr/bin/env bash
# ================================================================
#  open_session.sh — 直接打开某个 session 的 xlsx 数据文件
#
#  用法:
#    ./open_session.sh 1              打开最新实验的 session 1
#    ./open_session.sh 3              打开最新实验的 session 3
#    ./open_session.sh 1 proposal5_navigation_first_20260404_205458
#                                    打开指定实验目录的 session 1
# ================================================================

set -euo pipefail

SESSION_NUM="${1:-}"
EXPERIMENT_DIR="${2:-}"

if [ -z "$SESSION_NUM" ]; then
    echo "用法: ./open_session.sh <session_number> [experiment_dir_name]"
    echo ""
    echo "示例:"
    echo "  ./open_session.sh 1              打开最新实验的 session 1"
    echo "  ./open_session.sh 3              打开最新实验的 session 3"
    echo "  ./open_session.sh 1 proposal5_navigation_first_20260404_205458"
    exit 1
fi

# 零填充 session 编号
SESSION_PAD=$(printf "%02d" "$SESSION_NUM")

# 定位 data/raw/trajectory 目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TRAJ_DIR="$SCRIPT_DIR/data/raw/trajectory"

if [ ! -d "$TRAJ_DIR" ]; then
    echo "[错误] 数据目录不存在: $TRAJ_DIR"
    exit 1
fi

# 如果未指定实验目录，则自动找最新的 proposal5_ 目录
if [ -z "$EXPERIMENT_DIR" ]; then
    EXP_PATH=$(ls -d "$TRAJ_DIR"/proposal5_* 2>/dev/null | sort | tail -n 1)
    if [ -z "$EXP_PATH" ]; then
        echo "[错误] 未找到 proposal5_* 实验目录，请在 $TRAJ_DIR 中确认。"
        exit 1
    fi
else
    EXP_PATH="$TRAJ_DIR/$EXPERIMENT_DIR"
fi

if [ ! -d "$EXP_PATH" ]; then
    echo "[错误] 实验目录不存在: $EXP_PATH"
    exit 1
fi

# 查找匹配的 session xlsx 文件
FOUND=$(ls "$EXP_PATH"/session_${SESSION_PAD}_*.xlsx 2>/dev/null | head -n 1)

if [ -z "$FOUND" ]; then
    echo "[错误] 未找到 session $SESSION_NUM 的 xlsx 文件。"
    echo "目录: $EXP_PATH"
    echo ""
    echo "可用文件:"
    ls "$EXP_PATH"/*.xlsx 2>/dev/null || echo "  (无 xlsx 文件)"
    exit 1
fi

echo "正在打开: $FOUND"

# 跨平台打开
if command -v xdg-open &>/dev/null; then
    xdg-open "$FOUND"
elif command -v open &>/dev/null; then
    open "$FOUND"
else
    echo "请手动打开文件: $FOUND"
fi
