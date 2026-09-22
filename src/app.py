# -*- coding: utf-8 -*-
"""应用主控制器：串联 配置 / 调度器 / 设置窗口 / 弹窗 / 托盘。

线程模型：
- 调度器（后台线程）与托盘回调只向 queue 投递事件；
- 主线程每 100ms 轮询 queue，所有 tkinter 操作都在主线程完成。
"""
import io
import os
import queue
import random
import sys
import time
import tkinter as tk

import config
from icons import thumb_icon
from popup import ReminderPopup, layout_positions
from scheduler import ReminderScheduler
from settings_window import SettingsWindow

try:
    import winsound
except ImportError:  # 非 Windows 环境兜底
    winsound = None

try:
    import winreg
except ImportError:
    winreg = None

AUTOSTART_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_NAME = "HuYanZhuShou"


class EyeReminderApp:
    def __init__(self, root):
        self.root = root
        self.config = config.load()
        self.queue = queue.Queue()
        self._msg_index = 0
        self._popups = []            # 当前屏幕上的全部弹窗（同一批，一起关）
        self._popup = None           # 主弹窗（旧字段，保留兼容：等于 _popups[0]）
        self._closed_to_tray_notified = False
        self._quit_requested = False

        self._set_window_icon(root)

        # 调度器：通过闭包读取最新配置，避免线程间共享可变对象
        self.scheduler = ReminderScheduler(
            self.queue,
            get_interval_seconds=lambda: self.config["interval_minutes"] * 60,
            get_next_message=self._next_message,
            get_checkins_spec=self._checkins_spec,
        )
        if not self.config["running"]:
            self.scheduler.pause()

        self.win = SettingsWindow(root, self)

        # 托盘（失败则降级：关闭窗口 = 退出程序）
        self.tray = None
        try:
            from tray import TrayIcon
            self.tray = TrayIcon(self.queue)
            self.tray.start()
            self._has_tray = True
        except Exception:
            self._has_tray = False

        root.protocol("WM_DELETE_WINDOW", self._on_close_window)
        root.after(100, self._poll_queue)

    # ---------- 文案轮换 ----------
    def _next_message(self) -> str:
        msgs = self.config["messages"] or ["该休息一下眼睛啦！"]
        if self.config["random_order"]:
            return random.choice(msgs)
        msg = msgs[self._msg_index % len(msgs)]
        self._msg_index += 1
        return msg

    def _checkins_spec(self) -> list:
        """供调度器读取的每日打卡配置（闭包，线程间只读）。

        只返回**已启用**的条目；时间非法或缺失的条目直接跳过。
        """
        out = []
        for item in self.config.get("checkins", []):
            if not item.get("enabled"):
                continue
            try:
                h, m = str(item["time"]).split(":")
                hour, minute = int(h), int(m)
            except (ValueError, TypeError, KeyError, AttributeError):
                continue
            out.append({
                "label": str(item.get("label") or "打卡"),
                "kind": "checkin",
                "hour": max(0, min(23, hour)),
                "minute": max(0, min(59, minute)),
                "message": str(item.get("message") or ""),
            })
        return out

    @staticmethod
    def _set_window_icon(root):
        """窗口标题栏图标：👍（程序化生成 PNG，无外部文件依赖）。"""
        try:
            buf = io.BytesIO()
            thumb_icon(64).save(buf, format="PNG")
            photo = tk.PhotoImage(data=buf.getvalue())
            root.iconphoto(True, photo)
        except Exception:
            pass

    # ---------- 设置窗口回调 ----------
    def update_config(self, cfg: dict):
        """合并界面值并保存；间隔变化时重置计时。"""
        changed_interval = cfg["interval_minutes"] != self.config["interval_minutes"]
        self.config.update(cfg)
        config.save(self.config)
        self.win._update_toggle_btn()
        if changed_interval:
            self.scheduler.reset()
        self.win.show_saved_hint()

    def toggle_running(self):
        """开始/暂停切换。"""
        if self.config["running"]:
            self.config["running"] = False
            self.scheduler.pause()
        else:
            self.config["running"] = True
            self.scheduler.resume()
        config.save(self.config)
        self.win._update_toggle_btn()

    def preview_popup(self):
        """预览休息弹窗（不重置计时）。"""
        self._show_popup(self._next_message())

    def preview_checkin_popup(self):
        """预览打卡弹窗：取第一条已启用的打卡，全部停用时取第一条。"""
        items = self.config.get("checkins") or []
        target = next((i for i in items if i.get("enabled")),
                      items[0] if items else None)
        if not target:
            self.preview_popup()
            return
        self._show_popup(target.get("message") or "", kind="checkin",
                         title=str(target.get("label") or "打卡"),
                         hint=f"每天 {target.get('time', '09:00')} 打卡")

    def set_autostart(self, enable: bool) -> bool:
        """写入/删除 HKCU 注册表 Run 键；失败返回 False（句柄用 finally 确保关闭）。"""
        if winreg is None:
            return False
        exe = os.path.abspath(sys.executable)
        if not getattr(sys, "frozen", False):
            exe = os.path.join(os.path.dirname(exe), "pythonw.exe")
            script = os.path.abspath(sys.argv[0])
            command = f'"{exe}" "{script}"'
        else:
            command = f'"{exe}"'
        key = None
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_KEY,
                                 0, winreg.KEY_SET_VALUE)
            if enable:
                winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ, command)
            else:
                try:
                    winreg.DeleteValue(key, AUTOSTART_NAME)
                except FileNotFoundError:
                    pass
            return True
        except Exception:
            return False
        finally:
            if key is not None:
                try:
                    winreg.CloseKey(key)
                except Exception:
                    pass

    # ---------- 弹窗 ----------
    def _show_popup(self, message, kind="rest", title=None, hint=None):
        """弹出提醒窗口。

        title/hint 用于打卡弹窗（覆盖标题与底部说明）。
        一次提醒按配置同时弹 popup_count 个，铺在桌面的不同位置（互不重叠）；
        点击其中任意一个按钮即关闭全部 —— 这样即使有一个被别的窗口挡住、
        或者落在副屏上，用户处理任意一个都算处理过了。
        """
        self._close_all_popups(0)        # 上一批立即清掉，避免叠在一起
        if winsound is not None and self.config["sound"]:
            try:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass
        if title:   # 打卡弹窗：按钮文案独立配置
            button_text = self.config.get("checkin_button_text", "已打卡，继续")
        else:
            button_text = self.config.get("button_text", "知道了，继续干活")

        # 同一次提醒共用一份设置：个数 / 稍后分钟数
        count = self._clamp_count(self.config.get("popup_count", 1))
        defer_minutes = self._clamp_defer(self.config.get("defer_minutes", 5))
        positions = layout_positions(
            count, self.root.winfo_screenwidth(),
            self.root.winfo_screenheight())

        for pos in positions:
            try:
                self._popups.append(ReminderPopup(
                    self.root, message,
                    remain_seconds=self.config["popup_seconds"],
                    next_interval_minutes=self.config["interval_minutes"],
                    kind=kind, title=title, hint=hint,
                    button_text=button_text,
                    on_close=self._on_popup_closed,
                    defer_minutes=defer_minutes,
                    on_defer=self._on_defer,
                    on_dismiss=self._close_all_popups,
                    theme_name=self.config.get("theme"),
                    target=pos))
            except Exception:
                pass                 # 单个弹窗创建失败不影响其余弹窗
        self._popup = self._popups[0] if self._popups else None

    @staticmethod
    def _clamp_count(value):
        try:
            return max(1, min(config.MAX_POPUP_COUNT, int(value)))
        except (TypeError, ValueError):
            return 1

    @staticmethod
    def _clamp_defer(value):
        try:
            return max(1, min(config.MAX_DEFER_MINUTES, int(value)))
        except (TypeError, ValueError):
            return config.DEFAULTS["defer_minutes"]

    def _on_popup_closed(self, popup):
        """某个弹窗彻底销毁后，从在屏列表里摘掉它。"""
        try:
            self._popups.remove(popup)
        except ValueError:
            pass
        if self._popup is popup:
            self._popup = self._popups[0] if self._popups else None

    def _close_all_popups(self, fade=4):
        """关闭当前所有弹窗：fade=0 立即销毁，否则阶梯淡出。

        先把在屏列表清空再逐个处理：淡出是异步的（约 200ms），
        清空可保证紧接着弹出的新一批不会和正在消失的旧弹窗混在一起。
        """
        snapshot = self._popups
        self._popups = []
        self._popup = None
        for p in snapshot:
            try:
                if fade <= 0:
                    p._destroy_popup()
                else:
                    p._animate_out(fade)
            except Exception:
                pass

    def _on_defer(self, minutes):
        """「稍后提醒」：重置休息计时到 minutes 分钟后，并关掉同批弹窗。"""
        try:
            minutes = self._clamp_defer(minutes)
        except Exception:
            minutes = config.DEFAULTS["defer_minutes"]
        self.scheduler.defer(minutes * 60)

    # ---------- 事件轮询（主线程） ----------
    def _poll_queue(self):
        try:
            while True:
                event = self.queue.get_nowait()
                self._handle_event(event)
                if self._quit_requested:
                    return
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _handle_event(self, event):
        """处理单个事件；异常被隔离，绝不让单个事件中断轮询（防弹窗停摆）。"""
        try:
            name = event[0]
            if name == "show_popup":
                self._show_popup(event[1], kind="rest")
            elif name == "show_offwork":
                self._show_popup(event[1], kind="offwork")
            elif name == "show_checkin":
                # ("show_checkin", 名称, 时刻, 文案)：标题=打卡名称，副文案=每天时刻
                label, at, message = event[1], event[2], event[3]
                self._show_popup(message, kind="checkin", title=label,
                                 hint=f"每天 {at} 打卡")
            elif name == "open_settings":
                self._show_settings_window()
            elif name == "remind_now":
                self._show_popup(self._next_message())
                self.scheduler.reset()  # 手动提醒后重新计时
            elif name == "quit":
                self._quit()
        except Exception:
            pass  # 单事件失败不影响后续事件处理

    def _show_settings_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(200, lambda: self.root.attributes("-topmost", False))

    # ---------- 关闭 / 退出 ----------
    def _on_close_window(self):
        """点关闭按钮：有托盘则隐藏到托盘，否则退出程序。"""
        if self._has_tray:
            self.root.withdraw()
            if not self._closed_to_tray_notified:
                self._closed_to_tray_notified = True
                from tkinter import messagebox
                self.root.after(100, lambda: messagebox.showinfo(
                    "护眼助手",
                    "程序仍在后台运行，会继续定时提醒。\n"
                    "点击右下角托盘图标可随时打开设置或退出。"))
        else:
            self._quit()

    def _quit(self):
        self._quit_requested = True
        try:
            self.scheduler.stop()
        except Exception:
            pass
        if self.tray is not None:
            try:
                self.tray.stop()
            except Exception:
                pass
        try:
            self.root.destroy()
        except Exception:
            pass
        # 兜底：确保后台线程与进程一并结束
        os._exit(0)
