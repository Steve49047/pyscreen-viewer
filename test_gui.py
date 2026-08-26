#!/usr/bin/env python3
"""
测试用GUI程序 - 模拟一个简单界面
用于测试PyScreen的截屏和远程控制功能
"""
import tkinter as tk
import math
import time

class TestGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("PyScreen Test GUI")
        self.root.geometry("640x480")
        self.root.configure(bg="#1a1a2e")

        # 画布
        self.canvas = tk.Canvas(self.root, width=640, height=350, bg="#16213e", highlightthickness=0)
        self.canvas.pack(pady=10)

        # 按钮区
        btn_frame = tk.Frame(self.root, bg="#1a1a2e")
        btn_frame.pack(pady=5)

        colors = ["#e94560", "#0f3460", "#533483", "#e94560"]
        labels = ["按钮A", "按钮B", "按钮C", "按钮D"]
        for i, (text, color) in enumerate(zip(labels, colors)):
            btn = tk.Button(btn_frame, text=text, bg=color, fg="white",
                          width=10, height=2, font=("Arial", 12))
            btn.grid(row=0, column=i, padx=5)

        # 状态标签
        self.status = tk.Label(self.root, text="PyScreen测试界面 - 运行中",
                              bg="#1a1a2e", fg="#e94560", font=("Arial", 14))
        self.status.pack(pady=5)

        self.frame_count = 0
        self.animate()

    def animate(self):
        self.canvas.delete("all")
        self.frame_count += 1
        t = time.time()

        # 绘制动画
        for i in range(5):
            x = 320 + 200 * math.cos(t + i * 1.2)
            y = 175 + 100 * math.sin(t * 0.7 + i)
            r = 20 + 10 * math.sin(t * 2 + i)
            color = f"#{int(128+127*math.sin(t+i)):02x}{int(128+127*math.sin(t+i+2)):02x}{int(128+127*math.sin(t+i+4)):02x}"
            self.canvas.create_oval(x-r, y-r, x+r, y+r, fill=color, outline="")

        # 绘制文字
        self.canvas.create_text(320, 175, text=f"Frame: {self.frame_count}",
                               fill="white", font=("Arial", 20))

        # 绘制进度条
        progress = (t * 50) % 640
        self.canvas.create_rectangle(0, 340, progress, 350, fill="#e94560")

        self.status.config(text=f"帧: {self.frame_count} | 时间: {t:.1f}s")
        self.root.after(33, self.animate)  # ~30fps

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = TestGUI()
    app.run()
