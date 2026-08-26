#!/bin/bash
# ============================================
# PyScreen 系统 - 一键启动脚本
# ============================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==============================="
echo " PyScreen 系统"
echo "==============================="
echo ""
echo "  1. 启动服务器"
echo "  2. 启动发送端"
echo "  3. 构建APK (需要x86_64 Linux)"
echo "  0. 退出"
echo ""
read -p "请选择: " choice

case $choice in
    1)
        echo "启动中继服务器..."
        python3 "$SCRIPT_DIR/server/relay_server.py" "$@"
        ;;
    2)
        SERVER=${2:-"ws://127.0.0.1:8765"}
        GUI_SCRIPT=${1:-""}
        if [ -n "$GUI_SCRIPT" ]; then
            echo "启动发送端: $GUI_SCRIPT -> $SERVER"
            python3 "$SCRIPT_DIR/sender/screen_sender.py" "$GUI_SCRIPT" --server "$SERVER"
        else
            echo "启动发送端 (仅截屏模式) -> $SERVER"
            python3 "$SCRIPT_DIR/sender/screen_sender.py" --server "$SERVER"
        fi
        ;;
    3)
        echo "开始构建APK..."
        bash "$SCRIPT_DIR/android/build.sh"
        ;;
    0)
        exit 0
        ;;
    *)
        echo "无效选择"
        ;;
esac
