#!/usr/bin/env python3
"""
Relay Server with TUI Control Panel
WebSocket中继服务器 + TUI终端控制面板
"""
import asyncio
import json
import time
import signal
import sys
import os
import curses
import threading
from collections import defaultdict
from datetime import datetime

try:
    import websockets
except ImportError:
    print("请先安装: pip3 install -i https://mirrors.aliyun.com/pypi/simple/ websockets")
    sys.exit(1)

# ============================================================
# 配置
# ============================================================
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8765
MAX_LOG_LINES = 200

# ============================================================
# 全局状态
# ============================================================
class ServerState:
    def __init__(self):
        self.host = DEFAULT_HOST
        self.port = DEFAULT_PORT
        self.running = False
        self.sender = None
        self.viewers = {}
        self.viewer_counter = 0
        self.logs = []
        self.stats = {
            "frames_relayed": 0,
            "touch_events_relayed": 0,
            "total_connections": 0,
            "start_time": None,
            "bytes_relayed": 0,
        }
        self.tui_mode = True

state = ServerState()

def log(msg, level="INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = f"[{timestamp}] [{level}] {msg}"
    state.logs.append(entry)
    if len(state.logs) > MAX_LOG_LINES:
        state.logs = state.logs[-MAX_LOG_LINES:]
    if not state.tui_mode:
        print(entry)

# ============================================================
# 异步操作函数
# ============================================================
_server_loop = None

def get_loop():
    return _server_loop

async def disconnect_all_viewers():
    for vid, vws in list(state.viewers.items()):
        try:
            await vws.close(1000, "管理员断开")
        except:
            pass
    state.viewers.clear()
    log("已断开所有Viewer", "CONTROL")

async def disconnect_sender():
    if state.sender:
        try:
            await state.sender.close(1000, "管理员断开")
        except:
            pass
        state.sender = None
        log("已断开Sender", "CONTROL")

async def send_to_sender(msg):
    if state.sender:
        try:
            await state.sender.send(json.dumps(msg))
        except:
            log("发送失败", "ERROR")

def run_async(coro):
    if _server_loop:
        asyncio.run_coroutine_threadsafe(coro, _server_loop)

# ============================================================
# WebSocket 处理
# ============================================================
async def handler(websocket):
    client_id = None
    client_type = None
    addr = websocket.remote_address
    state.stats["total_connections"] += 1

    try:
        raw = await asyncio.wait_for(websocket.recv(), timeout=10)
        msg = json.loads(raw)

        if msg.get("type") != "register":
            await websocket.close(4001, "必须先发送register消息")
            return

        client_type = msg.get("role", "viewer")
        client_id = f"{client_type}_{state.viewer_counter}"
        state.viewer_counter += 1

        if client_type == "sender":
            if state.sender:
                await websocket.close(4002, "已经有一个sender连接了")
                log("Sender连接被拒绝: 已有sender存在", "WARN")
                return
            state.sender = websocket
            log(f"Sender已连接: {addr}", "CONNECT")
            await websocket.send(json.dumps({"type": "registered", "id": client_id}))

            try:
                async for raw_msg in websocket:
                    data = json.loads(raw_msg)
                    if data.get("type") == "frame":
                        state.stats["frames_relayed"] += 1
                        state.stats["bytes_relayed"] += len(raw_msg)
                        dead = []
                        for vid, vws in state.viewers.items():
                            try:
                                await vws.send(raw_msg)
                            except:
                                dead.append(vid)
                        for vid in dead:
                            del state.viewers[vid]
                            log(f"Viewer {vid} 已断开(发送失败)", "DISCONNECT")
                    elif data.get("type") == "status":
                        log(f"Sender状态: {data.get('state', 'unknown')}", "INFO")
            except websockets.ConnectionClosed:
                pass
            finally:
                state.sender = None
                log("Sender已断开", "DISCONNECT")

        elif client_type == "viewer":
            state.viewers[client_id] = websocket
            log(f"Viewer已连接: {addr} (共{len(state.viewers)}个)", "CONNECT")
            await websocket.send(json.dumps({"type": "registered", "id": client_id}))

            if state.sender:
                try:
                    await state.sender.send(json.dumps({
                        "type": "viewer_count",
                        "count": len(state.viewers)
                    }))
                except:
                    pass

            try:
                async for raw_msg in websocket:
                    data = json.loads(raw_msg)
                    if data.get("type") == "touch" and state.sender:
                        state.stats["touch_events_relayed"] += 1
                        data["viewer_id"] = client_id
                        try:
                            await state.sender.send(json.dumps(data))
                        except:
                            log("转发触摸事件到Sender失败", "ERROR")
            except websockets.ConnectionClosed:
                pass
            finally:
                state.viewers.pop(client_id, None)
                log(f"Viewer {client_id} 已断开 (共{len(state.viewers)}个)", "DISCONNECT")
                if state.sender:
                    try:
                        await state.sender.send(json.dumps({
                            "type": "viewer_count",
                            "count": len(state.viewers)
                        }))
                    except:
                        pass

    except asyncio.TimeoutError:
        log(f"客户端超时未注册: {addr}", "WARN")
    except websockets.ConnectionClosed:
        pass
    except Exception as e:
        log(f"客户端错误: {e}", "ERROR")
    finally:
        if client_type == "sender" and state.sender == websocket:
            state.sender = None
        if client_id and client_type == "viewer":
            state.viewers.pop(client_id, None)

# ============================================================
# 服务器启动
# ============================================================
async def run_server():
    global _server_loop
    _server_loop = asyncio.get_running_loop()
    state.running = True
    state.stats["start_time"] = time.time()
    log(f"服务器启动 {state.host}:{state.port}")

    async with websockets.serve(handler, state.host, state.port):
        await asyncio.Future()

def start_server_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_server())

# ============================================================
# TUI 控制面板
# ============================================================
def process_command(cmd):
    if cmd.startswith("port "):
        try:
            new_port = int(cmd.split(" ")[1])
            state.port = new_port
            log(f"端口已修改为 {new_port}，需重启生效", "CONTROL")
        except:
            log("端口格式错误", "ERROR")
    elif cmd.startswith("send "):
        msg = cmd[5:]
        run_async(send_to_sender({"type": "command", "command": msg}))
        log(f"已发送命令给Sender: {msg}", "CONTROL")
    elif cmd == "help":
        log("命令: port <端口>, send <消息>, clear, export", "INFO")
    elif cmd == "clear":
        state.logs.clear()
    elif cmd == "export":
        export_logs()
    else:
        log(f"未知命令: {cmd} (输入help查看帮助)", "WARN")

def export_logs():
    filename = f"relay_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    try:
        with open(filename, 'w') as f:
            f.write("\n".join(state.logs))
        log(f"日志已导出: {filename}", "CONTROL")
    except Exception as e:
        log(f"导出失败: {e}", "ERROR")

def tui_main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(100)

    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_GREEN, -1)
    curses.init_pair(2, curses.COLOR_YELLOW, -1)
    curses.init_pair(3, curses.COLOR_RED, -1)
    curses.init_pair(4, curses.COLOR_CYAN, -1)
    curses.init_pair(5, curses.COLOR_WHITE, curses.COLOR_BLUE)
    curses.init_pair(6, curses.COLOR_BLACK, curses.COLOR_GREEN)

    current_section = 0
    scroll_offset = 0
    input_mode = False
    input_buf = ""
    input_prompt = ""

    while True:
        height, width = stdscr.getmaxyx()
        stdscr.clear()

        # 标题栏
        title = " PyScreen Relay Server - TUI Control Panel "
        try:
            stdscr.attron(curses.color_pair(6) | curses.A_BOLD)
            stdscr.addstr(0, 0, title.center(width)[:width])
            stdscr.attroff(curses.color_pair(6) | curses.A_BOLD)
        except:
            pass

        # 状态行
        uptime = ""
        if state.stats["start_time"]:
            secs = int(time.time() - state.stats["start_time"])
            uptime = f"{secs//3600}h{(secs%3600)//60}m{secs%60}s"

        sender_status = "已连接" if state.sender else "未连接"
        viewer_count = len(state.viewers)
        status_line = f" Sender:{sender_status} | Viewers:{viewer_count} | 帧:{state.stats['frames_relayed']} | 触摸:{state.stats['touch_events_relayed']} | {uptime} "
        try:
            stdscr.addstr(1, 0, status_line[:width-1], curses.color_pair(4))
        except:
            pass

        # Tab栏
        tabs = ["[1]概览", "[2]日志", "[3]控制"]
        try:
            stdscr.addstr(2, 0, " ".join(tabs)[:width-1], curses.A_UNDERLINE)
        except:
            pass

        content_top = 3
        content_bottom = height - 3

        # 概览
        if current_section == 0:
            info = [
                f"服务器: {state.host}:{state.port}",
                f"状态: {'运行中' if state.running else '已停止'}",
                "",
                f"--- 连接 ---",
                f"Sender: {sender_status}",
                f"Viewer数: {viewer_count}",
            ]
            for vid in state.viewers:
                info.append(f"  {vid}")
            if not state.viewers:
                info.append("  (无)")
            info.extend([
                "",
                f"--- 统计 ---",
                f"总连接: {state.stats['total_connections']}",
                f"帧转发: {state.stats['frames_relayed']}",
                f"触摸转发: {state.stats['touch_events_relayed']}",
                f"数据量: {state.stats['bytes_relayed']/1024/1024:.2f} MB",
                f"运行: {uptime}",
            ])
            for i, line in enumerate(info):
                y = content_top + i
                if y < content_bottom:
                    try:
                        stdscr.addstr(y, 2, line[:width-4])
                    except:
                        pass

        # 日志
        elif current_section == 1:
            vis = content_bottom - content_top - 1
            if state.logs:
                mx = max(0, len(state.logs) - vis)
                scroll_offset = min(scroll_offset, mx)
                for i, line in enumerate(state.logs[scroll_offset:scroll_offset+vis]):
                    y = content_top + i
                    c = curses.color_pair(4)
                    if "WARN" in line: c = curses.color_pair(2)
                    elif "ERROR" in line: c = curses.color_pair(3)
                    elif "CONNECT" in line or "DISCONNECT" in line: c = curses.color_pair(1)
                    try:
                        stdscr.addstr(y, 1, line[:width-2], c)
                    except:
                        pass
            else:
                try:
                    stdscr.addstr(content_top+1, 2, "(暂无日志)")
                except:
                    pass

        # 控制
        elif current_section == 2:
            ctrl = [
                "可用命令 (按数字键):",
                "",
                "  [1] 终断所有Viewer",
                "  [2] 终断Sender",
                "  [3] 发送命令给Sender",
                "  [4] 清空日志",
                "  [5] 导出日志",
                "",
                "  [/] 输入自定义命令",
                "  Tab 切换面板 | q 退出",
            ]
            for i, line in enumerate(ctrl):
                y = content_top + i
                if y < content_bottom:
                    try:
                        stdscr.addstr(y, 2, line[:width-4])
                    except:
                        pass

        # 底部
        try:
            stdscr.attron(curses.color_pair(6))
            stdscr.addstr(height-2, 0, " "*(width-1))
            if input_mode:
                stdscr.addstr(height-2, 0, f" {input_prompt}: {input_buf}_"[:width-1])
            else:
                stdscr.addstr(height-2, 0, " Tab:切换 | q:退出 | /:命令 "[:width-1])
            stdscr.attroff(curses.color_pair(6))
        except:
            pass

        try:
            stdscr.addstr(height-1, 0, " [1-3]面板 [Tab]切换 [q]退出 [↑↓]滚动 "[:width-1], curses.A_DIM)
        except:
            pass

        stdscr.refresh()

        try:
            key = stdscr.getch()
        except:
            key = -1

        if key == -1:
            continue

        if input_mode:
            if key == 27:
                input_mode = False
                input_buf = ""
            elif key in (10, 13):
                input_mode = False
                cmd = input_buf.strip()
                input_buf = ""
                if cmd:
                    process_command(cmd)
            elif key in (127, curses.KEY_BACKSPACE, 8):
                input_buf = input_buf[:-1]
            elif 32 <= key <= 126:
                input_buf += chr(key)
            continue

        if key in (ord('q'), ord('Q')):
            state.running = False
            break
        elif key == 9:  # Tab
            current_section = (current_section + 1) % 3
            scroll_offset = 0
        elif key == ord('1'):
            current_section = 0
        elif key == ord('2'):
            current_section = 1
        elif key == ord('3'):
            current_section = 2
        elif key == curses.KEY_UP:
            scroll_offset = max(0, scroll_offset - 1)
        elif key == curses.KEY_DOWN:
            scroll_offset += 1
        elif key == ord('/'):
            input_mode = True
            input_prompt = "命令"
            input_buf = ""
        elif current_section == 2:
            if key == ord('1'):
                run_async(disconnect_all_viewers())
            elif key == ord('2'):
                run_async(disconnect_sender())
            elif key == ord('3'):
                input_mode = True
                input_prompt = "发送给Sender"
                input_buf = ""
            elif key == ord('4'):
                state.logs.clear()
                log("日志已清空", "CONTROL")
            elif key == ord('5'):
                export_logs()

# ============================================================
# 入口
# ============================================================
def main():
    import argparse
    parser = argparse.ArgumentParser(description="PyScreen Relay Server")
    parser.add_argument("--host", default=DEFAULT_HOST, help="监听地址")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="监听端口")
    parser.add_argument("--no-tui", action="store_true", help="禁用TUI模式")
    args = parser.parse_args()

    state.host = args.host
    state.port = args.port
    state.tui_mode = not args.no_tui

    server_thread = threading.Thread(target=start_server_thread, daemon=True)
    server_thread.start()
    time.sleep(0.5)

    if state.tui_mode:
        try:
            curses.wrapper(tui_main)
        except KeyboardInterrupt:
            pass
    else:
        print(f"服务器运行中: {state.host}:{state.port} (Ctrl+C退出)")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

    state.running = False

if __name__ == "__main__":
    main()
