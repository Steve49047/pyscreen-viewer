#!/usr/bin/env python3
"""
PyScreen Viewer - Android APK
远程画面查看器，支持手机和电视两种画面模式
"""
import os
import sys
import json
import time
import base64
import threading
from io import BytesIO

# Kivy imports
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.slider import Slider
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.popup import Popup
from kivy.uix.image import Image as KivyImage
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, Line, Ellipse
from kivy.properties import StringProperty, NumericProperty, BooleanProperty, ListProperty
from kivy.utils import platform
from kivy.metrics import dp, sp
from kivy.core.image import Image as CoreImage

# WebSocket
try:
    import websocket
except ImportError:
    # Android may need different ws library
    pass

import json as json_mod
import base64 as base64_mod
import threading
import time as time_mod

# ============================================================
# 配置存储
# ============================================================
CONFIG_FILE = "pyscreen_config.json"
DEFAULT_CONFIG = {
    "server_host": "192.168.1.100",
    "server_port": 8765,
    "display_mode": "phone",  # "phone" 或 "tv"
    "auto_connect": True,
    "show_buttons": True,
    "button_opacity": 0.7,
    "quality": 70,
    "fps_limit": 30,
}

def load_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return json_mod.load(f)
    except:
        pass
    return DEFAULT_CONFIG.copy()

def save_config(config):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json_mod.dump(config, f, indent=2)
    except Exception as e:
        print(f"保存配置失败: {e}")

# ============================================================
# WebSocket客户端
# ============================================================
class WebSocketClient:
    def __init__(self, app):
        self.app = app
        self.ws = None
        self.connected = False
        self.thread = None
        self.running = False
        self.reconnect_delay = 2

    def connect(self, host, port):
        self.running = True
        self.thread = threading.Thread(target=self._connect_loop, args=(host, port), daemon=True)
        self.thread.start()

    def _connect_loop(self, host, port):
        import websocket
        while self.running:
            try:
                url = f"ws://{host}:{port}"
                print(f"连接到: {url}")
                self.ws = websocket.WebSocketApp(
                    url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self.ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as e:
                print(f"连接错误: {e}")
            if self.running:
                print(f"重连中... ({self.reconnect_delay}秒)")
                time_mod.sleep(self.reconnect_delay)
                self.reconnect_delay = min(self.reconnect_delay * 1.5, 15)

    def _on_open(self, ws):
        print("已连接到服务器")
        self.connected = True
        self.reconnect_delay = 2
        # 注册为viewer
        ws.send(json_mod.dumps({
            "type": "register",
            "role": "viewer",
            "platform": platform,
        }))
        Clock.schedule_once(lambda dt: self.app.on_connected())

    def _on_message(self, ws, message):
        try:
            data = json_mod.loads(message)
            if data.get("type") == "frame":
                # 更新画面
                Clock.schedule_once(lambda dt: self.app.update_frame(data), 0)
            elif data.get("type") == "registered":
                print(f"注册成功: {data.get('id')}")
        except Exception as e:
            print(f"消息处理错误: {e}")

    def _on_error(self, ws, error):
        print(f"WebSocket错误: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        print(f"连接关闭: {close_status_code} {close_msg}")
        self.connected = False
        Clock.schedule_once(lambda dt: self.app.on_disconnected())

    def send_touch(self, action, x, y):
        if self.ws and self.connected:
            try:
                self.ws.send(json_mod.dumps({
                    "type": "touch",
                    "action": action,
                    "x": x,
                    "y": y,
                }))
            except:
                pass

    def send_command(self, command):
        if self.ws and self.connected:
            try:
                self.ws.send(json_mod.dumps({
                    "type": "command",
                    "command": command,
                }))
            except:
                pass

    def disconnect(self):
        self.running = False
        if self.ws:
            try:
                self.ws.close()
            except:
                pass

# ============================================================
# 设置面板
# ============================================================
class SettingsPanel(BoxLayout):
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self.orientation = 'vertical'
        self.padding = dp(20)
        self.spacing = dp(10)

        # 标题
        title = Label(text='[b]PyScreen 连接设置[/b]', markup=True,
                      font_size=sp(24), size_hint_y=None, height=dp(50))
        self.add_widget(title)

        # 服务器地址
        self.add_widget(Label(text='服务器地址:', size_hint_y=None, height=dp(30),
                             halign='left', text_size=(None, None)))
        self.host_input = TextInput(
            text=app.config.get("server_host", "192.168.1.100"),
            multiline=False, size_hint_y=None, height=dp(40),
            font_size=sp(16)
        )
        self.add_widget(self.host_input)

        # 端口
        self.add_widget(Label(text='端口:', size_hint_y=None, height=dp(30),
                             halign='left'))
        self.port_input = TextInput(
            text=str(app.config.get("server_port", 8765)),
            multiline=False, size_hint_y=None, height=dp(40),
            font_size=sp(16), input_filter='int'
        )
        self.add_widget(self.port_input)

        # 显示模式
        mode_layout = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(10))
        mode_layout.add_widget(Label(text='画面模式:'))
        self.phone_btn = ToggleButton(text='手机', group='mode',
                                       size_hint_x=0.5,
                                       state='down' if app.config.get("display_mode") == "phone" else 'normal')
        self.tv_btn = ToggleButton(text='电视', group='mode',
                                    size_hint_x=0.5,
                                    state='down' if app.config.get("display_mode") == "tv" else 'normal')
        mode_layout.add_widget(self.phone_btn)
        mode_layout.add_widget(self.tv_btn)
        self.add_widget(mode_layout)

        # 自动连接
        self.auto_connect = ToggleButton(
            text='自动连接', size_hint_y=None, height=dp(40),
            state='down' if app.config.get("auto_connect") else 'normal'
        )
        self.add_widget(self.auto_connect)

        # 连接按钮
        self.connect_btn = Button(
            text='连接', size_hint_y=None, height=dp(50),
            background_color=(0.2, 0.7, 0.3, 1)
        )
        self.connect_btn.bind(on_press=self.on_connect)
        self.add_widget(self.connect_btn)

        # 返回按钮
        back_btn = Button(text='返回', size_hint_y=None, height=dp(40))
        back_btn.bind(on_press=lambda x: app.show_main())
        self.add_widget(back_btn)

    def on_connect(self, *args):
        host = self.host_input.text.strip()
        port = int(self.port_input.text.strip() or "8765")
        mode = "tv" if self.tv_btn.state == "down" else "phone"
        auto = self.auto_connect.state == "down"

        self.app.config["server_host"] = host
        self.app.config["server_port"] = port
        self.app.config["display_mode"] = mode
        self.app.config["auto_connect"] = auto
        save_config(self.app.config)

        self.app.connect_to_server(host, port)

# ============================================================
# 虚拟按钮面板
# ============================================================
class VirtualButtons(FloatLayout):
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self.buttons = []

        # 基本按钮布局
        btn_config = [
            {"text": "▲", "pos": (0.15, 0.7), "action": "up"},
            {"text": "▼", "pos": (0.15, 0.3), "action": "down"},
            {"text": "◀", "pos": (0.05, 0.5), "action": "left"},
            {"text": "▶", "pos": (0.25, 0.5), "action": "right"},
            {"text": "A", "pos": (0.8, 0.5), "action": "a"},
            {"text": "B", "pos": (0.7, 0.35), "action": "b"},
            {"text": "X", "pos": (0.9, 0.35), "action": "x"},
            {"text": "Y", "pos": (0.8, 0.2), "action": "y"},
            {"text": "SEL", "pos": (0.35, 0.15), "action": "select"},
            {"text": "STR", "pos": (0.65, 0.15), "action": "start"},
        ]

        for cfg in btn_config:
            btn = Button(
                text=cfg["text"],
                pos_hint={"x": cfg["pos"][0], "y": cfg["pos"][1]},
                size_hint=(0.15, 0.12),
                font_size=sp(14),
                background_color=(1, 1, 1, 0.3),
                color=(1, 1, 1, 0.8),
            )
            btn.action = cfg["action"]
            btn.bind(on_press=self.on_button_press)
            self.add_widget(btn)
            self.buttons.append(btn)

    def on_button_press(self, btn):
        if self.app.ws_client and self.app.ws_client.connected:
            self.app.ws_client.send_command(f"btn_{btn.action}")

    def set_opacity_all(self, opacity):
        for btn in self.buttons:
            btn.opacity = opacity

# ============================================================
# 主界面
# ============================================================
class MainScreen(FloatLayout):
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app

        # 画面显示区域
        self.screen_img = KivyImage(
            allow_stretch=True,
            keep_ratio=True,
            size_hint=(1, 1),
        )
        self.add_widget(self.screen_img)

        # 虚拟按钮
        self.virtual_buttons = VirtualButtons(app)
        self.add_widget(self.virtual_buttons)

        # 顶部状态栏
        top_bar = BoxLayout(
            size_hint=(1, None), height=dp(35),
            pos_hint={"top": 1}, spacing=dp(5)
        )
        with top_bar.canvas.before:
            Color(0, 0, 0, 0.6)
            Rectangle(pos=top_bar.pos, size=top_bar.size)
        self.status_label = Label(
            text='未连接', size_hint_x=0.6,
            font_size=sp(12), color=(0.5, 1, 0.5, 1)
        )
        self.fps_label = Label(
            text='FPS: 0', size_hint_x=0.2,
            font_size=sp(12), color=(1, 1, 0.5, 1)
        )
        self.mode_label = Label(
            text='手机模式', size_hint_x=0.2,
            font_size=sp(12), color=(0.5, 0.8, 1, 1)
        )
        top_bar.add_widget(self.status_label)
        top_bar.add_widget(self.fps_label)
        top_bar.add_widget(self.mode_label)
        self.add_widget(top_bar)

        # 底部控制栏
        bottom_bar = BoxLayout(
            size_hint=(1, None), height=dp(45),
            pos_hint={"y": 0}, spacing=dp(5)
        )
        with bottom_bar.canvas.before:
            Color(0, 0, 0, 0.6)
            Rectangle(pos=bottom_bar.pos, size=bottom_bar.size)

        settings_btn = Button(text='设置', size_hint_x=0.25, font_size=sp(12))
        settings_btn.bind(on_press=lambda x: app.show_settings())
        self.connect_btn = Button(text='连接', size_hint_x=0.25, font_size=sp(12),
                                   background_color=(0.2, 0.7, 0.3, 1))
        self.connect_btn.bind(on_press=self.on_connect_btn)
        self.disconnect_btn = Button(text='断开', size_hint_x=0.25, font_size=sp(12),
                                      background_color=(0.7, 0.2, 0.2, 1))
        self.disconnect_btn.bind(on_press=lambda x: app.disconnect())
        self.toggle_btns = Button(text='按钮', size_hint_x=0.25, font_size=sp(12))
        self.toggle_btns.bind(on_press=self.on_toggle_buttons)

        bottom_bar.add_widget(settings_btn)
        bottom_bar.add_widget(self.connect_btn)
        bottom_bar.add_widget(self.disconnect_btn)
        bottom_bar.add_widget(self.toggle_btns)
        self.add_widget(bottom_bar)

        # FPS计算
        self.frame_count = 0
        self.fps_time = time.time()

    def on_connect_btn(self, *args):
        cfg = self.app.config
        self.app.connect_to_server(cfg["server_host"], cfg["server_port"])

    def on_toggle_buttons(self, *args):
        self.app.config["show_buttons"] = not self.app.config.get("show_buttons", True)
        self.virtual_buttons.set_opacity_all(
            0.7 if self.app.config["show_buttons"] else 0
        )

# ============================================================
# 主App
# ============================================================
class PyScreenApp(App):
    def build(self):
        self.config = load_config()
        self.title = 'PyScreen Viewer'

        # 设置窗口大小 (手机 or TV)
        mode = self.config.get("display_mode", "phone")
        if mode == "tv":
            Window.size = (1280, 720)
        else:
            Window.size = (480, 800)

        self.ws_client = WebSocketClient(self)

        # 主界面
        self.main_screen = MainScreen(self)
        self.settings_panel = None
        self.current_screen = self.main_screen

        # 根布局
        self.root_widget = FloatLayout()
        self.root_widget.add_widget(self.main_screen)

        # 触摸事件
        Window.bind(on_touch_down=self.on_touch_down)
        Window.bind(on_touch_up=self.on_touch_up)
        Window.bind(on_touch_move=self.on_touch_move)

        # 更新UI
        Clock.schedule_interval(self.update_ui, 0.5)

        # 自动连接
        if self.config.get("auto_connect"):
            Clock.schedule_once(lambda dt: self.auto_connect(), 1)

        return self.root_widget

    def auto_connect(self):
        host = self.config.get("server_host", "")
        port = self.config.get("server_port", 8765)
        if host:
            self.connect_to_server(host, port)

    def connect_to_server(self, host, port):
        self.main_screen.status_label.text = f'连接中: {host}:{port}...'
        self.main_screen.status_label.color = (1, 1, 0, 1)
        self.ws_client.connect(host, port)

    def disconnect(self):
        self.ws_client.disconnect()
        self.main_screen.status_label.text = '已断开'
        self.main_screen.status_label.color = (1, 0.3, 0.3, 1)

    def on_connected(self):
        self.main_screen.status_label.text = '已连接'
        self.main_screen.status_label.color = (0.3, 1, 0.3, 1)

    def on_disconnected(self):
        self.main_screen.status_label.text = '连接断开'
        self.main_screen.status_label.color = (1, 0.3, 0.3, 1)

    def update_frame(self, data):
        """更新显示的画面"""
        try:
            frame_b64 = data.get("data", "")
            if not frame_b64:
                return
            frame_bytes = base64.b64decode(frame_b64)
            buf = BytesIO(frame_bytes)
            buf.seek(0)
            img = CoreImage(buf, ext='jpg')
            self.main_screen.screen_img.texture = img.texture

            # 更新FPS
            self.main_screen.frame_count += 1
            now = time.time()
            if now - self.main_screen.fps_time >= 1.0:
                fps = self.main_screen.frame_count / (now - self.main_screen.fps_time)
                self.main_screen.fps_label.text = f'FPS: {fps:.0f}'
                self.main_screen.frame_count = 0
                self.main_screen.fps_time = now
        except Exception as e:
            print(f"更新画面失败: {e}")

    def update_ui(self, dt):
        """定时更新UI状态"""
        mode = self.config.get("display_mode", "phone")
        self.main_screen.mode_label.text = '电视模式' if mode == 'tv' else '手机模式'

        # 更新按钮显示
        self.main_screen.virtual_buttons.set_opacity_all(
            0.7 if self.config.get("show_buttons") else 0
        )

    def on_touch_down(self, window, touch):
        if not self.ws_client or not self.ws_client.connected:
            return
        # 只处理画面区域的触摸 (排除控件)
        if touch.y > Window.height * 0.9 or touch.y < Window.height * 0.1:
            return  # 在顶部或底部栏
        # 计算相对坐标 (0-1)
        rx = touch.x / Window.width
        ry = touch.y / Window.height
        self.ws_client.send_touch("down", rx, ry)
        return True

    def on_touch_up(self, window, touch):
        if not self.ws_client or not self.ws_client.connected:
            return
        if touch.y > Window.height * 0.9 or touch.y < Window.height * 0.1:
            return
        rx = touch.x / Window.width
        ry = touch.y / Window.height
        self.ws_client.send_touch("up", rx, ry)
        return True

    def on_touch_move(self, window, touch):
        if not self.ws_client or not self.ws_client.connected:
            return
        if touch.y > Window.height * 0.9 or touch.y < Window.height * 0.1:
            return
        rx = touch.x / Window.width
        ry = touch.y / Window.height
        self.ws_client.send_touch("move", rx, ry)
        return True

    def show_settings(self):
        if self.settings_panel:
            self.root_widget.remove_widget(self.main_screen)
            self.root_widget.add_widget(self.settings_panel)
        else:
            self.settings_panel = SettingsPanel(self)
            self.root_widget.remove_widget(self.main_screen)
            self.root_widget.add_widget(self.settings_panel)

    def show_main(self):
        if self.settings_panel:
            self.root_widget.remove_widget(self.settings_panel)
        self.root_widget.remove_widget(self.main_screen)
        self.root_widget.add_widget(self.main_screen)

    def on_pause(self):
        return True

    def on_resume(self):
        pass

if __name__ == "__main__":
    PyScreenApp().run()
