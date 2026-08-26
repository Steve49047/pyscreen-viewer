#!/usr/bin/env python3
"""
Python GUI Screen Sender
截取GUI程序画面并发送到中继服务器
"""
import asyncio
import json
import sys
import time
import base64
import io
import signal
import struct
import subprocess
import os
from datetime import datetime

try:
    import websockets
except ImportError:
    print("请先安装: pip3 install -i https://mirrors.aliyun.com/pypi/simple/ websockets")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    print("请先安装: pip3 install -i https://mirrors.aliyun.com/pypi/simple/ Pillow")
    sys.exit(1)

try:
    import mss
    import mss.tools
except ImportError:
    print("请先安装: pip3 install -i https://mirrors.aliyun.com/pypi/simple/ mss")
    sys.exit(1)

# ============================================================
# 配置
# ============================================================
DEFAULT_SERVER = "ws://127.0.0.1:8765"
FRAME_QUALITY = 70       # JPEG质量 (1-100)
TARGET_FPS = 15          # 目标帧率
MAX_FRAME_SIZE = 640     # 最大帧宽度
RECONNECT_DELAY = 3      # 重连间隔(秒)

# ============================================================
# 截屏管理
# ============================================================
class ScreenCapture:
    def __init__(self):
        self.sct = None
        try:
            import mss as _mss
            self.sct = _mss.mss()
        except Exception:
            print("mss不可用，将使用subprocess截图")
        self.target_window = None
        self.frame_count = 0
        self.fps_counter = 0
        self.fps_time = time.time()

    def find_gui_window(self):
        """尝试找到GUI程序窗口"""
        try:
            # Linux: 使用xdotool或wmctrl查找窗口
            if sys.platform == "linux":
                result = subprocess.run(
                    ["xdotool", "search", "--name", "."],
                    capture_output=True, text=True, timeout=5
                )
                if result.stdout.strip():
                    windows = result.stdout.strip().split('\n')
                    # 过滤掉终端和桌面窗口
                    for wid in windows:
                        try:
                            name_result = subprocess.run(
                                ["xdotool", "getwindowname", wid],
                                capture_output=True, text=True, timeout=2
                            )
                            name = name_result.stdout.strip()
                            skip_keywords = ["terminal", "bash", "python", "desktop", "finder", "system"]
                            if not any(k in name.lower() for k in skip_keywords):
                                self.target_window = int(wid)
                                print(f"找到目标窗口: {name} (ID: {wid})")
                                return True
                        except:
                            continue
            # macOS
            elif sys.platform == "darwin":
                result = subprocess.run(
                    ["osascript", "-e",
                     'tell application "System Events" to get name of every window of every process whose visible is true'],
                    capture_output=True, text=True, timeout=5
                )
                print(f"可用窗口: {result.stdout[:200]}")
        except Exception as e:
            print(f"查找窗口失败: {e}")

        # 默认截取整个屏幕
        print("将截取整个屏幕")
        return False

    def capture_frame(self):
        """截取一帧画面"""
        try:
            if self.sct and self.target_window:
                # 尝试截取特定窗口 (Linux)
                if sys.platform == "linux":
                    try:
                        import re
                        result = subprocess.run(
                            ["xdotool", "getwindowgeometry", str(self.target_window)],
                            capture_output=True, text=True, timeout=2
                        )
                        parts = result.stdout
                        pos_match = re.search(r'Position: (\d+),(\d+)', parts)
                        size_match = re.search(r'Geometry: (\d+)x(\d+)', parts)
                        if pos_match and size_match:
                            x, y = int(pos_match.group(1)), int(pos_match.group(2))
                            w, h = int(size_match.group(1)), int(size_match.group(2))
                            monitor = {"top": y, "left": x, "width": w, "height": h}
                            screenshot = self.sct.grab(monitor)
                            return self._process_frame(screenshot)
                    except:
                        pass

            if self.sct:
                # 截取整个主屏幕
                screenshot = self.sct.grab(self.sct.monitors[1])
                return self._process_frame(screenshot)

            # 备用: 使用import获取测试帧
            return self._generate_test_frame()
        except Exception as e:
            print(f"截屏失败: {e}")
            return self._generate_test_frame()

    def _generate_test_frame(self):
        """生成测试帧(无可截图源时)"""
        img = Image.new("RGB", (640, 480), (30, 100, 200))
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(img)
        t = time.time()
        x = int((t * 50) % 640)
        draw.rectangle([x, 200, x+100, 280], fill=(255, 100, 50))
        draw.text((10, 10), f"Test Frame #{self.frame_count}", fill=(255,255,255))
        draw.text((10, 30), f"No screen capture available", fill=(200,200,200))

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=FRAME_QUALITY, optimize=True)
        frame_data = buffer.getvalue()

        self.frame_count += 1
        self.fps_counter += 1
        now = time.time()
        if now - self.fps_time >= 1.0:
            fps = self.fps_counter / (now - self.fps_time)
            self.fps_counter = 0
            self.fps_time = now
            print(f"  FPS: {fps:.1f} | 帧数: {self.frame_count}")

        return {
            "type": "frame",
            "data": base64.b64encode(frame_data).decode("ascii"),
            "width": img.size[0],
            "height": img.size[1],
            "timestamp": time.time()
        }

    def _process_frame(self, screenshot):
        """处理帧: 缩放 + JPEG编码"""
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

        # 缩放
        w, h = img.size
        if w > MAX_FRAME_SIZE:
            ratio = MAX_FRAME_SIZE / w
            img = img.resize((MAX_FRAME_SIZE, int(h * ratio)), Image.LANCZOS)

        # 编码为JPEG
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=FRAME_QUALITY, optimize=True)
        frame_data = buffer.getvalue()

        self.frame_count += 1
        self.fps_counter += 1

        now = time.time()
        if now - self.fps_time >= 1.0:
            fps = self.fps_counter / (now - self.fps_time)
            self.fps_counter = 0
            self.fps_time = now
            if self.frame_count % 30 == 0:
                print(f"  FPS: {fps:.1f} | 帧数: {self.frame_count} | 大小: {len(frame_data)/1024:.1f}KB")

        return {
            "type": "frame",
            "data": base64.b64encode(frame_data).decode("ascii"),
            "width": img.size[0],
            "height": img.size[1],
            "timestamp": time.time()
        }

# ============================================================
# 注入触摸/鼠标事件 (接收自APK)
# ============================================================
def inject_touch_event(action, x, y):
    """将APK发来的触摸事件注入到GUI程序"""
    try:
        if sys.platform == "linux":
            # 使用xdotool模拟鼠标
            if action == "down":
                subprocess.run(["xdotool", "mousemove", "--window", str(capture.target_window or 0),
                              str(int(x)), str(int(y)), "mousedown", "1"],
                             capture_output=True, timeout=2)
            elif action == "up":
                subprocess.run(["xdotool", "mousemove", "--window", str(capture.target_window or 0),
                              str(int(x)), str(int(y)), "mouseup", "1"],
                             capture_output=True, timeout=2)
            elif action == "move":
                subprocess.run(["xdotool", "mousemove", "--window", str(capture.target_window or 0),
                              str(int(x)), str(int(y))],
                             capture_output=True, timeout=2)
            elif action == "scroll_up":
                subprocess.run(["xdotool", "click", "4"], capture_output=True, timeout=2)
            elif action == "scroll_down":
                subprocess.run(["xdotool", "click", "5"], capture_output=True, timeout=2)
        elif sys.platform == "darwin":
            # macOS
            subprocess.run(["cliclick", f"m:{int(x)},{int(y)}"], capture_output=True, timeout=2)
    except Exception as e:
        print(f"注入事件失败: {e}")

# ============================================================
# Sender主逻辑
# ============================================================
capture = ScreenCapture()

async def sender_main(server_url):
    global capture

    print(f"=== Python GUI Screen Sender ===")
    print(f"服务器: {server_url}")

    # 查找目标窗口
    capture.find_gui_window()

    reconnect_delay = RECONNECT_DELAY

    while True:
        try:
            async with websockets.connect(server_url, ping_interval=20, ping_timeout=10) as ws:
                # 注册为sender
                await ws.send(json.dumps({
                    "type": "register",
                    "role": "sender",
                    "name": "PythonGUI",
                    "version": "1.0"
                }))

                response = json.loads(await ws.recv())
                if response.get("type") == "registered":
                    print(f"已注册到服务器: {response.get('id')}")
                    reconnect_delay = RECONNECT_DELAY
                else:
                    print(f"注册失败: {response}")
                    continue

                # 主循环: 截屏并发送
                frame_interval = 1.0 / TARGET_FPS
                last_frame_time = time.time()

                async def send_loop():
                    while True:
                        now = time.time()
                        if now - last_frame_time >= frame_interval:
                            frame = capture.capture_frame()
                            if frame:
                                await ws.send(json.dumps(frame))
                        await asyncio.sleep(0.001)

                async def recv_loop():
                    async for raw_msg in ws:
                        try:
                            data = json.loads(raw_msg)
                            if data.get("type") == "touch":
                                action = data.get("action", "")
                                x = data.get("x", 0)
                                y = data.get("y", 0)
                                inject_touch_event(action, x, y)
                            elif data.get("type") == "command":
                                cmd = data.get("command", "")
                                if cmd == "stop":
                                    print("收到停止命令")
                                    return
                                elif cmd == "list_windows":
                                    # 列出可用窗口
                                    pass
                            elif data.get("type") == "viewer_count":
                                print(f"当前Viewer数量: {data.get('count', 0)}")
                        except json.JSONDecodeError:
                            pass

                await asyncio.gather(send_loop(), recv_loop())

        except (websockets.ConnectionClosed, ConnectionRefusedError, OSError) as e:
            print(f"连接断开: {e}, {reconnect_delay}秒后重连...")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 1.5, 30)
        except KeyboardInterrupt:
            print("Sender已停止")
            break
        except Exception as e:
            print(f"错误: {e}")
            await asyncio.sleep(reconnect_delay)

# ============================================================
# 入口
# ============================================================
def main():
    global FRAME_QUALITY, TARGET_FPS, MAX_FRAME_SIZE

    import argparse
    parser = argparse.ArgumentParser(description="Python GUI Screen Sender")
    parser.add_argument("gui_script", nargs="?", help="要截取的Python GUI程序脚本路径")
    parser.add_argument("--server", "-s", default=DEFAULT_SERVER, help="服务器地址 (默认: ws://127.0.0.1:8765)")
    parser.add_argument("--fps", type=int, default=TARGET_FPS, help="目标帧率")
    parser.add_argument("--quality", type=int, default=FRAME_QUALITY, help="JPEG质量 (1-100)")
    parser.add_argument("--width", type=int, default=MAX_FRAME_SIZE, help="最大帧宽度")
    args = parser.parse_args()

    FRAME_QUALITY = args.quality
    TARGET_FPS = args.fps
    MAX_FRAME_SIZE = args.width

    # 如果指定了GUI脚本，尝试启动它
    gui_proc = None
    if args.gui_script:
        print(f"启动GUI程序: {args.gui_script}")
        gui_proc = subprocess.Popen([sys.executable, args.gui_script])
        time.sleep(2)  # 等待窗口出现
        capture.find_gui_window()

    try:
        asyncio.run(sender_main(args.server))
    except KeyboardInterrupt:
        print("Sender已停止")
    finally:
        if gui_proc:
            gui_proc.terminate()

if __name__ == "__main__":
    main()
