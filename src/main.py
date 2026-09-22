# -*- coding: utf-8 -*-
"""程序入口：DPI 感知 → 单实例检测 → 启动主窗口 / 开机自启后台运行。

单实例实现（安全考量）：
- 绑定本地回环端口作为唯一实例标志；
- 绑定失败时先尝试连接该端口：能连上 = 确有本应用实例在运行（正常退出）；
  连不上 = 端口被其他程序占用（恶意或巧合），此时降级使用备选端口继续
  运行，避免"端口被占即无法启动"的本地 DoS 面。
"""
import os
import socket
import sys
import threading
import tkinter as tk

# 兼容打包后与源码直跑两种形态
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import EyeReminderApp  # noqa: E402

SINGLE_INSTANCE_PORT = 42685
BACKUP_INSTANCE_PORT = 42686    # 主端口被其他程序占用时的降级端口
APP_QUEUE = None       # 由 app 创建后注册，供单实例监听线程投递事件
_lock_socket = None    # 持有引用，防止端口被回收

# 应用层握手协议：真实实例收到请求字节后必须回复响应字节。
# 仅靠 TCP connect 成功无法区分真实实例与"恰好监听该端口"的其他程序
# （listen 后三次握手即可完成），握手可让探测结果可信。
_HANDSHAKE_REQ = b"H"
_HANDSHAKE_RESP = b"E"


def _enable_dpi_awareness():
    """高分屏下让 tkinter 界面不模糊。"""
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def _acquire_single_instance(port) -> bool:
    """尝试绑定指定端口；成功返回 True（并启动监听线程）。"""
    global _lock_socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # 注意：绝不能设置 SO_REUSEADDR —— Windows 上它允许端口重复绑定，
        # 会导致单实例机制失效。
        sock.bind(("127.0.0.1", port))
        sock.listen(4)
        _lock_socket = sock
        threading.Thread(target=_instance_listener, args=(sock,),
                         daemon=True).start()
        return True
    except OSError:
        return False


def _is_real_instance(port) -> bool:
    """应用层握手探测：发送请求字节并校验响应字节，返回是否为真实实例。"""
    try:
        with socket.create_connection(("127.0.0.1", port), 1) as conn:
            conn.settimeout(1)
            conn.sendall(_HANDSHAKE_REQ)
            resp = conn.recv(2)
            return resp.startswith(_HANDSHAKE_RESP)
    except OSError:
        return False


def _instance_listener(sock):
    """已有实例：完成握手后提示打开设置窗口（非本应用连接不受影响）。

    仅 accept 失败（socket 被关闭）才退出线程；单个连接的任何异常
    （超时、非本应用连接、恶意空连接）都被隔离，不影响监听线程存活。
    """
    while True:
        try:
            conn, _ = sock.accept()
        except OSError:
            break
        try:
            conn.settimeout(1)
            data = conn.recv(2)
            if data.startswith(_HANDSHAKE_REQ):
                conn.sendall(_HANDSHAKE_RESP)  # 先应答，再投递事件
                if APP_QUEUE is not None:
                    APP_QUEUE.put(("open_settings",))
        except OSError:
            pass  # 单连接异常不影响监听线程
        finally:
            try:
                conn.close()
            except OSError:
                pass


def _notify_existing(port):
    """向已有实例发送握手请求（请它打开设置窗口）。"""
    try:
        with socket.create_connection(("127.0.0.1", port), 1) as conn:
            conn.settimeout(1)
            conn.sendall(_HANDSHAKE_REQ)
            conn.recv(2)
    except OSError:
        pass


def main():
    global APP_QUEUE
    _enable_dpi_awareness()

    # 主端口：可绑定 → 成为唯一实例
    if _acquire_single_instance(SINGLE_INSTANCE_PORT):
        port = SINGLE_INSTANCE_PORT
    else:
        # 主端口被占用：探测是否为真实实例
        if _is_real_instance(SINGLE_INSTANCE_PORT):
            _notify_existing(SINGLE_INSTANCE_PORT)  # 真实实例：请它打开窗口，本实例退出
            return
        # 端口被其他程序占用（非本应用）：降级用备选端口继续运行
        if not _acquire_single_instance(BACKUP_INSTANCE_PORT):
            # 备选端口也被占用（极端情况）：再探测备选端口是否为本应用
            if _is_real_instance(BACKUP_INSTANCE_PORT):
                _notify_existing(BACKUP_INSTANCE_PORT)
                return
            # 两个端口都被其他程序占用：仍无法启动，给出提示后退出
            try:
                from tkinter import messagebox
                root_tmp = tk.Tk()
                root_tmp.withdraw()
                messagebox.showerror(
                    "护眼助手",
                    "无法启动：单实例端口被其他程序占用。\n"
                    "请关闭占用 127.0.0.1:42685 端口的程序后重试。")
                root_tmp.destroy()
            except Exception:
                pass
            return
        port = BACKUP_INSTANCE_PORT

    root = tk.Tk()
    app = EyeReminderApp(root)
    APP_QUEUE = app.queue

    if app.config.get("auto_start") and app.config.get("running"):
        # 开机自启：不打扰用户，直接后台运行（托盘常驻）
        root.withdraw()
    else:
        root.deiconify()

    root.mainloop()


if __name__ == "__main__":
    main()
