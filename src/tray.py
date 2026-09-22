# -*- coding: utf-8 -*-
"""系统托盘：pystray 图标（👍）+ 菜单（打开设置 / 立即提醒 / 退出）。

注意：pystray 的菜单回调运行在 pystray 自己的线程中，
所有需要操作 tkinter 的动作一律通过事件队列投递到主线程处理。
"""
import threading

import pystray

from icons import thumb_icon


class TrayIcon:
    """托盘封装：start() 后在后台线程运行；stop() 退出。"""

    def __init__(self, queue):
        self._queue = queue  # 事件队列，回调经此投递到主线程
        self._icon = pystray.Icon(
            "huyanzhushou", thumb_icon(64), "护眼助手",
            menu=pystray.Menu(
                pystray.MenuItem("打开设置", lambda i, m: self._emit("open_settings"),
                                 default=True),
                pystray.MenuItem("立即提醒", lambda i, m: self._emit("remind_now")),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("退出", lambda i, m: self._emit("quit")),
            ))
        self._thread = threading.Thread(target=self._icon.run, daemon=True)

    def _emit(self, event):
        self._queue.put((event,))

    def start(self):
        self._thread.start()

    def stop(self):
        try:
            self._icon.stop()
        except Exception:
            pass
