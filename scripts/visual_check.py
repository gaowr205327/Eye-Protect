# -*- coding: utf-8 -*-
"""视觉验证脚本（开发用）：弹出设置窗口（三标签页）与两类提醒弹窗，截图到 assets/。
用法: python scripts/visual_check.py
"""
import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from PIL import ImageGrab

import config
from popup import ReminderPopup, W, H, MARGIN
from settings_window import SettingsWindow

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
os.makedirs(OUT_DIR, exist_ok=True)

root = tk.Tk()


class FakeApp:
    """最小假控制器，避免拉起完整 app（托盘/调度器）。"""

    def __init__(self):
        self.config = config.load()
        self.scheduler = type("S", (), {
            "status": lambda self: {"running": True, "rest": 2700,
                                    "checkin": 4 * 3600 + 10 * 60 + 2,
                                    "checkin_label": "午休结束"},
        })()

    def update_config(self, cfg):
        self.config.update(cfg)

    def toggle_running(self):
        pass

    def preview_popup(self):
        pass

    def preview_checkin_popup(self):
        pass

    def set_autostart(self, enable):
        return True


app = FakeApp()
win = SettingsWindow(root, app)
win._update_toggle_btn()

# 窗口落点可用环境变量挪开（避开桌面上的其他窗口/开始菜单）
_pos = os.environ.get("VISUAL_POS")
if _pos:
    root.geometry("+%s" % _pos)
    for _ in range(4):
        root.update()
        root.update_idletasks()

# 两类弹窗：休息（屏幕正中央）与打卡（左下角）
sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
p_rest = ReminderPopup(root, "眼睛累了，看看远处 20 秒吧～\n记得眨眼，记得喝水，站起来活动一下。",
                       remain_seconds=8, next_interval_minutes=45, kind="rest",
                       button_text="我先眯一会儿")
p_check = ReminderPopup(root, "午休结束，记得打卡回来上班。",
                        remain_seconds=8, kind="checkin",
                        title="午休结束", hint="每天 13:30 打卡",
                        button_text="已打卡，继续",
                        target=(MARGIN, sh - H - MARGIN))


def shot_popups():
    cx, cy = (sw - W) // 2, (sh - H) // 2
    ImageGrab.grab(bbox=(cx - 30, cy - 60, cx + W + 30, cy + H + 60)).save(
        os.path.join(OUT_DIR, "shot_rest.png"))
    ImageGrab.grab(bbox=(0, sh - 280, 410, sh - 10)).save(
        os.path.join(OUT_DIR, "shot_checkin.png"))
    print("弹窗截图已保存（休息 / 打卡）")


def shot_main():
    root.deiconify()
    root.lift()
    root.update()
    shots = (("main", "shot_main.png"),
             ("checkin", "shot_main_checkin.png"),
             ("settings", "shot_main_settings.png"))
    for key, name in shots:
        win._show_tab(key)
        for _ in range(4):
            root.update()
            root.update_idletasks()
        w, h = root.winfo_width(), root.winfo_height()
        # 优先按窗口句柄抓取：不经过屏幕合成，屏幕上第三方浮层（如时间水印）不会混进来。
        # 注意不能用 FindWindowW(None, 标题) —— 弹窗标题相同会先被匹配到。
        # root.winfo_id() 就是本 Tk 顶层窗口的 HWND，精确且不受其它窗口干扰。
        dst = os.path.join(OUT_DIR, name)
        try:
            import ctypes
            hwnd = root.winfo_id()
            img = ImageGrab.grab(window=hwnd)
            if img.size == (w, h):
                img.save(dst)
                continue
        except Exception:
            pass
        ImageGrab.grab(bbox=(root.winfo_rootx(), root.winfo_rooty(),
                             root.winfo_rootx() + w, root.winfo_rooty() + h)).save(dst)
    print("设置窗口截图已保存（主功能 / 打卡提醒 / 设置）")
    for p in (p_rest, p_check):
        try:
            p._close_now()
        except Exception:
            pass
    root.after(800, root.destroy)


root.after(2500, shot_popups)   # 弹窗动画完成后截图
root.after(3500, shot_main)     # 再截设置窗口
root.mainloop()
print("完成")
