# -*- coding: utf-8 -*-
"""端到端测试（开发用）：真实 App 实例，验证 调度器→队列→主线程→弹窗
完整链路，覆盖休息（定时触发）与打卡（注入触发）两种弹窗。
用法: python -u scripts/e2e_test.py
"""
import os
import sys
import tempfile
import time
import tkinter as tk

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import config as cfg_mod
from app import EyeReminderApp

# 隔离配置目录，不污染真实配置
_tmp = tempfile.mkdtemp()
cfg_mod.CONFIG_DIR = _tmp
cfg_mod.CONFIG_PATH = os.path.join(_tmp, "config.json")

root = tk.Tk()
app = EyeReminderApp(root)

# 休息间隔 5 秒（保证打卡弹窗有充足观察窗口）；打卡注入 2 秒后触发；关声音
app.config["interval_minutes"] = 5 / 60.0
app.config["sound"] = False
app.config["running"] = True
app.config["checkins"][0].update({"enabled": True, "time": "09:00",
                                  "message": "E2E打卡提示：记得打卡！"})
for item in app.config["checkins"][1:]:
    item["enabled"] = False
app.scheduler.reset()          # 先重置（内部会按打卡配置重算时间）
time.sleep(0.3)                # 等调度线程完成重置，避免覆盖注入值
app.scheduler._checkins[0]["ts"] = time.time() + 2.0  # 注入打卡触发时刻
print("E2E: injected checkin in 2s, rest in 5s", flush=True)

results = {"rest": False, "checkin": False}


def final_shot():
    from PIL import ImageGrab
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    shot = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "assets", "shot_e2e.png")
    ImageGrab.grab(bbox=(sw - 420, sh - 280, sw - 10, sh - 10)).save(shot)
    print("E2E: both popups OK, screenshot saved", flush=True)
    app._quit()


def pos_check():
    """弹窗位置（v1.5）：固定屏幕正中央；配色（v1.7）：单一固定样式。"""
    import theme as theme_mod  # noqa: E402
    from popup import ReminderPopup, W, H  # noqa: E402
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    p = ReminderPopup(root, "位置测试", remain_seconds=3)
    p2 = ReminderPopup(root, "配色测试", remain_seconds=3, theme_name="dark")

    def verify():
        try:
            assert p.winfo_x() == (sw - W) // 2 \
                and p.winfo_y() == (sh - H) // 2, \
                "弹窗未居中: %s,%s" % (p.winfo_x(), p.winfo_y())
            assert p2._c["accent"] == theme_mod.get()["popup"]["accent"], \
                "弹窗配色未应用（应回退到唯一固定样式）"
            print("E2E: popup centered + theme PASS", flush=True)
        finally:
            try:
                p._close_now()
            except Exception:
                pass
            try:
                p2._close_now()
            except Exception:
                pass
            final_shot()
    root.after(500, verify)  # 等滑入动画结束再取坐标


def check():
    p = app._popup
    if p is not None:
        try:
            if p.winfo_exists():
                kind = p._kind
                if not results[kind]:
                    results[kind] = True
                    print("E2E: %s popup shown (title=%s)" % (kind, p._title),
                          flush=True)
                if results["rest"] and results["checkin"]:
                    # 两种弹窗都已触发：先验证位置功能，再截图退出
                    root.after(400, pos_check)
                    return
        except Exception as exc:
            print("E2E: popup error:", exc, flush=True)
            app._quit()
            return
    root.after(200, check)


root.after(200, check)
root.after(20000, lambda: (print("E2E: TIMEOUT, results=%s" % results, flush=True),
                           app._quit()))
root.mainloop()
print("E2E done", flush=True)
