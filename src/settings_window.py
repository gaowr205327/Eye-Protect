# -*- coding: utf-8 -*-
"""设置主窗口：三标签页 —— 主功能 / 打卡提醒 / 设置。

- 主功能：休息提醒间隔与提醒文案（展示模式）
- 打卡提醒：每日 4 次上下班打卡，逐条开关 + 时间 + 提示词
- 设置：弹窗停留、提示音、开机自启、弹窗按钮文案、关于

界面：星露谷像素风。所有面板/按钮/标签/输入框外壳都由 pixelart.py
在原生低分辨率上逐像素绘制再整数倍放大（硬边、台阶角、无抗锯齿），
装饰件（木纹、铆钉、草簇、小花、抖动渐变）同样是程序化生成。

**字体为像素字体**（`assets/fonts/` 下的 Fusion Pixel 12px，OFL 授权），
由 `fonts.py` 私有注册到本进程，字号按 12px 设计栅格取整数倍（用负数字号
=像素，避免 DPI 缩放把像素格糊掉）。字体文件缺失时自动回落系统字体。
为了让文字压在木质/绿色底上依然清晰，标题与按钮文字另外用
「多层偏移描边」加上像素字的黑色外轮廓。

布局要点：
- 顶部木质招牌 + 木质标签栏 + 装饰分隔条；内容区随标签切换并按内容
  自动调整窗口高度，避免短标签页出现大片空白；
- 底部常驻操作行 + 草地装饰带；
- 所有修改即时生效并自动保存。

v1.9：
- 修掉"快捷间隔按钮绿色固定"的问题 —— 高亮改为跟随当前值实时刷新；
- 设置页新增"弹窗个数"（同一次提醒同时弹几个，铺在桌面不同位置）
  与"稍后提醒"（休息弹窗第二个按钮的延后分钟数）。
"""
import time
import tkinter as tk
import tkinter.font as tkfont

from PIL import ImageTk

import config
import pixelart
import theme
from fonts import (SIZE_BODY, SIZE_SMALL, SIZE_TITLE, apply_defaults, spec)

APP_VERSION = "v1.9"

# 字号全部来自 fonts.py：像素字体下用「负数字号=像素」，锁定 12px 栅格
FONT = spec(SIZE_BODY)
FONT_BOLD = spec(SIZE_BODY, bold=True)
FONT_SMALL = spec(SIZE_SMALL)
FONT_TITLE = spec(SIZE_TITLE, bold=True)

QUICK_INTERVALS = (20, 25, 45, 60)
TABS = (("main", "主功能", "eye"),
        ("checkin", "打卡提醒", "checklist"),
        ("settings", "设置", "gear"))
WIN_W = 470          # 窗口宽度（固定）
MIN_H = 500          # 窗口最小高度

SHADOW_S = pixelart.SHADOW_N * pixelart.SF   # 卡片硬投影的屏幕像素
FIELD_INSET = (1 + 1) * pixelart.SF + 1      # 输入框外壳向内留给原生控件的边距
TAB_H = 34
DIVIDER_H = 18
FOOTER_H = 46
BANNER_H = 58


def outline_texts(cv, x, y, text, font, fill, outline, width=2, **kw):
    """在 Canvas 上画「带描边」的文字：先按环形偏移画描边色，再盖填充色。

    这是不改字体、又能让系统字体在木面/绿底上站稳的常用手法
    （像素游戏的外描边字也是同样的堆叠原理）。
    """
    offs = [(dx, dy) for dx in range(-width, width + 1)
            for dy in range(-width, width + 1)
            if max(abs(dx), abs(dy)) == width]
    for dx, dy in offs:
        cv.create_text(x + dx, y + dy, text=text, font=font, fill=outline, **kw)
    return cv.create_text(x, y, text=text, font=font, fill=fill, **kw)


# ==================== 像素组件 ====================

IMG_NOTE = "（必须持有 PhotoImage 引用，否则会被 GC 回收导致图变空白）"


class PixelBanner(tk.Canvas):
    """木质招牌标题栏。"""

    def __init__(self, master, bg, text, font=FONT_TITLE):
        super().__init__(master, bg=bg, highlightthickness=0, bd=0,
                         height=BANNER_H)
        self._bg = bg
        self._text = text
        self._font = font
        self._img = None
        self.bind("<Configure>", self._redraw)

    def _redraw(self, event=None):
        w = self.winfo_width()
        if w <= 1:
            return
        self._img = ImageTk.PhotoImage(pixelart.banner(w, BANNER_H))   # 见 IMG_NOTE
        self.delete("all")
        self.create_image(0, 0, image=self._img, anchor="nw")
        t = theme.get()["window"]
        outline_texts(self, w // 2, BANNER_H // 2, self._text, self._font,
                      t["on_wood"], t["ink"], width=2)


class PixelCard(tk.Canvas):
    """木质卡片：硬偏移投影 + 三层木框 + 铆钉 + 角花。

    内容 Frame 经 set_content 嵌入，卡片高度自动随内容伸展
    （与原 RoundedCard 接口完全一致）。
    """

    def __init__(self, master, bg, padx=16, pady=13):
        super().__init__(master, bg=bg, highlightthickness=0, bd=0)
        self._padx = padx
        self._pady = pady
        self._frame = None
        self._img = None
        self.bind("<Configure>", self._redraw)

    def set_content(self, frame):
        self._frame = frame
        frame.bind("<Configure>", lambda e: self._fit_height())
        self._fit_height()

    def _content_height(self):
        if self._frame is None:
            return 0
        return self._frame.winfo_reqheight() + 2 * self._pady

    def _total_height(self):
        return self._content_height() + SHADOW_S

    def _fit_height(self):
        h = self._total_height()
        if h > 0 and int(self.cget("height")) != h:
            self.configure(height=h)

    def _redraw(self, event=None):
        if self._frame is None:
            return
        w = self.winfo_width()
        if w <= 1:
            return
        total = self._total_height()
        self._img = ImageTk.PhotoImage(pixelart.card(w, total))        # 见 IMG_NOTE
        self.delete("all")
        self.create_image(0, 0, image=self._img, anchor="nw")
        self.create_window(self._padx, self._pady, window=self._frame,
                           anchor="nw",
                           width=max(40, w - SHADOW_S - 2 * self._padx))


class PixelButton(tk.Canvas):
    """像素按钮：三态（常态 / 悬停 / 按下）。

    兼容原 tk.Button 的两处用法：
      configure(text=...) / cget("text")  —— 标签切换时会改文案
    """

    _BASES = ("primary", "soft", "warn")

    def __init__(self, master, text, command, variant="soft", font=FONT_BOLD,
                 fg=None, height=34, width=None, padx=16, bg=None):
        bg = bg or self._parent_bg(master)
        super().__init__(master, bg=bg, highlightthickness=0, bd=0, height=height)
        self._text = text
        self._command = command
        self._variant = variant
        self._font = font
        t = theme.get()["window"]
        self._fg = fg or (t["accent_fg"] if variant in ("primary", "warn")
                          else t["soft_fg"])
        self._h = height
        self._padx = padx
        self._state = ""
        self._img = None
        self._auto_w = width is None
        if width is None:
            width = tkfont.Font(font=font).measure(text) + 2 * padx
        self.configure(width=width)
        self.bind("<Configure>", self._redraw)
        self.bind("<Enter>", lambda e: self._set_state("_hover"))
        self.bind("<Leave>", lambda e: self._set_state(""))
        self.bind("<ButtonPress-1>", lambda e: self._set_state("_press"))
        self.bind("<ButtonRelease-1>", self._on_release)

    @staticmethod
    def _parent_bg(master):
        try:
            return master.cget("bg")
        except tk.TclError:
            return theme.get()["window"]["bg"]

    def _on_release(self, event):
        pressed = self._state == "_press"
        self._set_state("_hover" if 0 <= event.x <= self.winfo_width()
                        and 0 <= event.y <= self.winfo_height() else "")
        if pressed and self._command:
            self._command()

    def _set_state(self, state):
        if state != self._state:
            self._state = state
            self._redraw()

    def _full_variant(self):
        base = self._variant if self._variant in self._BASES else "soft"
        return base + self._state

    def _redraw(self, event=None):
        w = max(10, self.winfo_width())
        h = max(10, self.winfo_height())
        self._img = ImageTk.PhotoImage(pixelart.button(w, h, self._full_variant()))
        self.delete("all")
        self.create_image(0, 0, image=self._img, anchor="nw")
        t = theme.get()["window"]
        # 描边色跟着"底色明暗"走：浅字压深底用墨色描边，
        # 深字压浅底用奶油色描边（否则 1px 墨线会把中文笔画糊成一团）。
        outline = t["ink"] if self._variant in ("primary", "warn") else t["pap_lt"]
        dy = 2 if self._state == "_press" else 0     # 按下时文字跟着下沉（像素风"按下位移"）
        outline_texts(self, w // 2, h // 2 + dy, self._text, self._font,
                      self._fg, outline, width=1)

    # ---- 兼容 tk.Button 的接口 ----
    def configure(self, **kw):
        if "text" in kw:
            self._text = kw.pop("text")
            if self._auto_w:                      # 文案变了要重新量宽
                super().configure(
                    width=tkfont.Font(font=self._font).measure(self._text)
                    + 2 * self._padx)
            self._redraw()
        kw.pop("bg", None)                # 配色由 variant 决定，忽略外部 bg
        kw.pop("activebackground", None)
        if kw:
            super().configure(**kw)

    config = configure

    def cget(self, key):
        if key == "text":
            return self._text
        return super().cget(key)

    def set_variant(self, variant):
        self._variant = variant
        self._redraw()


class PixelTab(tk.Canvas):
    """木质标签页：像素底 + 图标 + 文字（选中态描边高亮）。"""

    def __init__(self, master, text, icon_name, command, width=100):
        super().__init__(master, bg=self._pbg(master), highlightthickness=0,
                         bd=0, height=TAB_H, width=width)
        self._text = text
        self._icon_name = icon_name
        self._command = command
        self._active = False
        self._img = None
        self._icon = None
        self.bind("<Configure>", self._redraw)
        self.bind("<Button-1>", lambda e: command())
        self.bind("<Enter>", lambda e: self.configure(cursor="hand2"))

    @staticmethod
    def _pbg(master):
        try:
            return master.cget("bg")
        except tk.TclError:
            return theme.get()["window"]["bg"]

    def set_active(self, active):
        if active != self._active:
            self._active = active
            self._redraw()

    def _redraw(self, event=None):
        w = self.winfo_width()
        if w <= 1:
            return
        t = theme.get()["window"]
        self._img = ImageTk.PhotoImage(pixelart.tab(w, TAB_H, self._active))
        self._icon = ImageTk.PhotoImage(
            pixelart.icon(self._icon_name, 20 if self._active else 18))
        self.delete("all")
        self.create_image(0, 0, image=self._img, anchor="nw")
        tw = tkfont.Font(font=FONT_BOLD).measure(self._text)
        iw = self._icon.width()
        total = iw + 5 + tw
        x0 = max(6, (w - total) // 2)
        self.create_image(x0, TAB_H // 2, image=self._icon, anchor="w")
        fg = t["on_wood"] if self._active else t["soft_fg"]
        outline = t["ink"] if self._active else t["pap_lt"]
        outline_texts(self, x0 + iw + 5 + tw // 2, TAB_H // 2,
                      self._text, FONT_BOLD, fg, outline, width=1)


class PixelField(tk.Canvas):
    """像素内凹外框 + 内嵌**原生**输入控件。

    Spinbox / Entry / Text 由系统绘制，无法真正像素化；
    这里把"像素感"做在外框上（厚描边 + 内凹方向光），
    内部控件设为无边框并统一底色，功能与原生完全一致。
    """

    def __init__(self, master, factory, height=30, bg=None):
        bg = bg or self._pb(master)
        super().__init__(master, bg=bg, highlightthickness=0, bd=0, height=height)
        self._h = height
        self._img = None
        self._child = factory(self)
        self.bind("<Configure>", self._redraw)

    @staticmethod
    def _pb(master):
        try:
            return master.cget("bg")
        except tk.TclError:
            return theme.get()["window"]["card_bg"]

    def _redraw(self, event=None):
        w = self.winfo_width()
        if w <= 1:
            return
        self._img = ImageTk.PhotoImage(pixelart.field(w, self._h))
        self.delete("all")
        self.create_image(0, 0, image=self._img, anchor="nw")
        self.create_window(self._padx(), self._h // 2, window=self._child,
                           anchor="w",
                           width=max(20, w - 2 * self._padx()),
                           height=max(12, self._h - 2 * FIELD_INSET + 4))

    def _padx(self):
        return FIELD_INSET + 2


class PixelCheck(tk.Frame):
    """像素勾选框：外观自绘，**变量仍是 BooleanVar**，与原 tk.Checkbutton 行为一致。"""

    def __init__(self, master, text, var, command=None, bg=None, size=18):
        bg = bg or self._pb(master)
        super().__init__(master, bg=bg)
        t = theme.get()["window"]
        self._var = var
        self._command = command
        self._size = size
        self._img_on = ImageTk.PhotoImage(pixelart.checkbox(size, True))
        self._img_off = ImageTk.PhotoImage(pixelart.checkbox(size, False))
        self._cv = tk.Canvas(self, width=size, height=size, bg=bg,
                             highlightthickness=0, bd=0, cursor="hand2")
        self._cv.pack(side="left")
        self._lbl = tk.Label(self, text=text, bg=bg, fg=t["text"], font=FONT,
                             cursor="hand2")
        self._lbl.pack(side="left", padx=(5, 0))
        self._cv.bind("<Button-1>", self._toggle)
        self._lbl.bind("<Button-1>", self._toggle)
        self._var.trace_add("write", lambda *a: self._render())
        self._render()

    @staticmethod
    def _pb(master):
        try:
            return master.cget("bg")
        except tk.TclError:
            return theme.get()["window"]["card_bg"]

    def _toggle(self, event=None):
        self._var.set(not bool(self._var.get()))
        if self._command:
            self._command()

    def _render(self):
        self._cv.delete("all")
        self._cv.create_image(0, 0, anchor="nw",
                              image=self._img_on if self._var.get() else self._img_off)


class PixelRadio(tk.Frame):
    """像素单选框：同上，语义与 tk.Radiobutton 一致（点击把变量设为 value）。"""

    def __init__(self, master, text, var, value, command=None, bg=None, size=18):
        bg = bg or self._pb(master)
        super().__init__(master, bg=bg)
        t = theme.get()["window"]
        self._var = var
        self._value = value
        self._command = command
        self._img_on = ImageTk.PhotoImage(pixelart.radio(size, True))
        self._img_off = ImageTk.PhotoImage(pixelart.radio(size, False))
        self._cv = tk.Canvas(self, width=size, height=size, bg=bg,
                             highlightthickness=0, bd=0, cursor="hand2")
        self._cv.pack(side="left")
        self._lbl = tk.Label(self, text=text, bg=bg, fg=t["text"], font=FONT,
                             cursor="hand2")
        self._lbl.pack(side="left", padx=(5, 0))
        self._cv.bind("<Button-1>", self._pick)
        self._lbl.bind("<Button-1>", self._pick)
        self._var.trace_add("write", lambda *a: self._render())
        self._render()

    @staticmethod
    def _pb(master):
        try:
            return master.cget("bg")
        except tk.TclError:
            return theme.get()["window"]["card_bg"]

    def _pick(self, event=None):
        if self._var.get() == self._value:
            return
        self._var.set(self._value)
        if self._command:
            self._command()

    def _render(self):
        on = self._var.get() == self._value
        self._cv.delete("all")
        self._cv.create_image(0, 0, anchor="nw",
                              image=self._img_on if on else self._img_off)


class DecorBand(tk.Canvas):
    """装饰色带：'divider'（分隔条）或 'footer'（底部草地）。"""

    def __init__(self, master, kind, bg, height):
        super().__init__(master, bg=bg, highlightthickness=0, bd=0, height=height)
        self._kind = kind
        self._h = height
        self._img = None
        self.bind("<Configure>", self._redraw)

    def _redraw(self, event=None):
        w = self.winfo_width()
        if w <= 1:
            return
        maker = pixelart.divider if self._kind == "divider" else pixelart.footer
        self._img = ImageTk.PhotoImage(maker(w, self._h))
        self.delete("all")
        self.create_image(0, 0, image=self._img, anchor="nw")


class SparkStar(tk.Canvas):
    """像素星星：8fps 阶梯闪烁（两帧交替，不用缓动 —— 像素风要"跳帧"感）。"""

    FRAMES = (14, 10)

    def __init__(self, master, bg):
        super().__init__(master, width=self.FRAMES[0], height=self.FRAMES[0],
                         bg=bg, highlightthickness=0, bd=0)
        self._imgs = [ImageTk.PhotoImage(pixelart.icon("star", f))
                      for f in self.FRAMES]
        self._i = 0
        self._running = False
        self._draw()

    def _draw(self):
        f = self.FRAMES[self._i]
        self.delete("all")
        self.create_image((self.FRAMES[0] - f) // 2, (self.FRAMES[0] - f) // 2,
                          image=self._imgs[self._i], anchor="nw")

    def start(self):
        if not self._running:
            self._running = True
            self._tick()

    def stop(self):
        self._running = False

    def _tick(self):
        if not self._running:
            return
        self._i = (self._i + 1) % len(self.FRAMES)
        self._draw()
        self.after(125, self._tick)      # 125ms = 8fps


# ==================== 主窗口 ====================

class SettingsWindow:
    def __init__(self, root, app):
        self.app = app
        self.cfg = app.config
        self.t = theme.get()["window"]

        # 把 Tk 内置命名字体也换成像素字体，让原生控件（下拉箭头、
        # 输入光标、消息框等）跟着统一（幂等，重复调用无副作用）
        apply_defaults(root)

        root.title("护眼助手")
        root.configure(bg=self.t["bg"])
        root.geometry("%dx%d" % (WIN_W, 760))
        root.minsize(430, MIN_H)
        self.root = root

        self._cards = []
        self._pages = {}
        self._tab_buttons = {}
        self._checkin_rows = []
        self._active_tab = None

        self._build_ui()
        self._refresh_status()
        root.after(1000, self._tick_status)

    # ---------- 控件工厂 ----------
    def _spinbox(self, master, **kw):
        """原生 Spinbox（保留上下箭头与 command 回调），外观对齐像素外框。"""
        t = self.t
        return tk.Spinbox(master, font=FONT, justify="center", relief="flat",
                          bd=0, highlightthickness=0, bg=t["input_bg"],
                          fg=t["text"], insertbackground=t["text"],
                          selectbackground=t["accent"],
                          selectforeground=t["accent_fg"],
                          buttonbackground=t["input_bg"], **kw)

    def _entry(self, master, **kw):
        t = self.t
        return tk.Entry(master, font=FONT, relief="flat", bd=0,
                        highlightthickness=0, bg=t["input_bg"], fg=t["text"],
                        insertbackground=t["text"], selectbackground=t["accent"],
                        selectforeground=t["accent_fg"], **kw)

    def _field(self, master, factory, height=30, width=None):
        """把原生输入控件塞进像素内凹外框里。

        注意：Tk 只接受**画布的后代**作为画布项，所以 factory 拿到的
        master 必须是这个 Canvas 本身 —— 原生控件要在 factory 里创建。
        """
        f = PixelField(master, factory, height=height)
        if width is not None:
            f.configure(width=width)
        return f

    def _field_native(self, master, maker, height=28, width=None):
        """像素外框 + 原生输入控件；返回 (外框, 控件)，控件在 maker(canvas) 内创建。

        maker 须返回新建的控件（供 frame/entry/text 用同一套写法）。
        """
        box = {}
        field = self._field(master, lambda cv: box.setdefault("w", maker(cv)),
                            height=height, width=width)
        return field, box["w"]

    def _card(self, parent, pady=6):
        """在指定容器内建一张木框卡片，返回用于放内容的内部 Frame。"""
        t = self.t
        card = PixelCard(parent, bg=t["bg"])
        card.pack(fill="x", padx=16, pady=pady)
        self._cards.append(card)
        frame = tk.Frame(card, bg=t["card_bg"])
        card.set_content(frame)
        return frame

    def _label(self, master, text, font=FONT, color="text", **kw):
        return tk.Label(master, text=text, bg=kw.pop("bg", self.t["card_bg"]),
                        fg=self.t[color], font=font, **kw)

    def _title(self, master, icon_name, text, padx=14, pady=(4, 6)):
        """卡片标题：像素小图标 + 文字（装饰）。返回整行 Frame，便于 pack。"""
        row = tk.Frame(master, bg=self.t["card_bg"])
        ic = ImageTk.PhotoImage(pixelart.icon(icon_name, 18))
        lbl = tk.Label(row, image=ic, bg=self.t["card_bg"], bd=0)
        lbl.image = ic                       # 见 IMG_NOTE
        lbl.pack(side="left")
        tk.Label(row, text=text, bg=self.t["card_bg"], fg=self.t["text"],
                 font=FONT_BOLD).pack(side="left", padx=(6, 0))
        row.pack(anchor="w", padx=padx, pady=pady)
        return row

    def _dotted(self, parent, padx=14):
        """打卡条目之间的点状分隔线（简单 1px 几何交给 Canvas，天然无抗锯齿）。"""
        cv = tk.Canvas(parent, bg=self.t["card_bg"], height=9,
                       highlightthickness=0, bd=0)

        def draw(event=None):
            w = cv.winfo_width()
            if w <= 1:
                return
            cv.delete("all")
            for x in range(14, w - 14, 5):
                cv.create_line(x, 4, x + 1, 4, fill=self.t["bevel"])
            cv.create_line(w // 2 - 3, 4, w // 2 + 3, 4, fill=self.t["wood"])
            cv.create_line(w // 2, 2, w // 2, 3, fill=self.t["grass"])

        cv.bind("<Configure>", draw)
        cv.pack(fill="x", padx=padx, pady=(2, 0))
        return cv

    # ---------- 界面 ----------
    def _build_ui(self):
        root = self.root
        t = self.t

        # ---- 标题区：像素木质招牌 + 副标题 ----
        header = tk.Frame(root, bg=t["bg"])
        header.pack(fill="x", padx=16, pady=(12, 4))
        self.banner = PixelBanner(header, bg=t["bg"], text="护眼助手")
        self.banner.pack(fill="x")
        sub = tk.Frame(header, bg=t["bg"])
        sub.pack(fill="x", pady=(5, 0))
        si = ImageTk.PhotoImage(pixelart.icon("sprout", 16))
        sl = tk.Label(sub, image=si, bg=t["bg"], bd=0)
        sl.image = si                        # 见 IMG_NOTE
        sl.pack(side="left", padx=(6, 0))
        tk.Label(sub, text="定时休息 · 每日打卡", bg=t["bg"], fg=t["sub"],
                 font=FONT_SMALL).pack(side="left", padx=(5, 0))

        # ---- 标签栏 ----
        tabbar = tk.Frame(root, bg=t["bg"])
        tabbar.pack(fill="x", padx=16, pady=(6, 0))
        for i, (key, label, icon_name) in enumerate(TABS):
            tab = PixelTab(tabbar, label, icon_name,
                           lambda k=key: self._show_tab(k))
            tab.pack(side="left", expand=True, fill="x",
                     padx=(0 if i == 0 else 5, 0))
            self._tab_buttons[key] = tab

        # ---- 装饰分隔条 ----
        DecorBand(root, "divider", bg=t["bg"], height=DIVIDER_H).pack(
            fill="x", padx=16, pady=(4, 0))

        # ---- 内容区：三页各建一次，切换时显隐 ----
        self._body = tk.Frame(root, bg=t["bg"])
        self._body.pack(fill="x")
        for key, builder in (("main", self._build_page_main),
                             ("checkin", self._build_page_checkin),
                             ("settings", self._build_page_settings)):
            page = tk.Frame(self._body, bg=t["bg"])
            self._pages[key] = page
            builder(page)

        # ---- 底部操作行（常驻） ----
        btn_row = tk.Frame(root, bg=t["bg"])
        btn_row.pack(fill="x", padx=16, pady=(8, 2))
        self.preview_btn = PixelButton(btn_row, "预览弹窗", self._on_preview,
                                       variant="soft", bg=t["bg"], height=34)
        self.preview_btn.pack(side="left")

        self.countdown_label = tk.Label(btn_row, text="", bg=t["bg"],
                                        fg=t["status_ok"], font=FONT_SMALL)
        self.countdown_label.pack(side="left", expand=True)

        self.toggle_btn = PixelButton(btn_row, "", self.app.toggle_running,
                                      variant="primary", bg=t["bg"], height=34,
                                      padx=22)
        self.toggle_btn.pack(side="right")
        self._update_toggle_btn()

        # ---- 保存提示（配像素星星，8fps 阶梯闪烁） ----
        status = tk.Frame(root, bg=t["bg"])
        status.pack(fill="x", padx=16, pady=(2, 0))
        self.saved_label = tk.Label(status, text="", bg=t["bg"],
                                    fg=t["status_ok"], font=FONT_SMALL)
        self.saved_label.pack(side="right")
        self.spark = SparkStar(status, bg=t["bg"])
        self.spark.pack(side="right", padx=(0, 5))

        # ---- 底部草地装饰带 ----
        DecorBand(root, "footer", bg=t["bg"], height=FOOTER_H).pack(
            fill="x", pady=(6, 0))

        # 首帧渲染后修正卡片高度（Canvas 高度依赖内容 reqheight）
        root.update_idletasks()
        for card in self._cards:
            card._fit_height()
        root.bind("<Map>", self._on_map)
        self._show_tab("main")

    # ---------- 标签页一：主功能 ----------
    def _build_page_main(self, page):
        t = self.t

        # --- 提醒间隔 ---
        c1 = self._card(page, pady=(2, 6))
        self._title(c1, "clock", "提醒间隔", padx=14, pady=(3, 4))
        row1 = tk.Frame(c1, bg=t["card_bg"])
        row1.pack(fill="x", padx=14, pady=(0, 2))
        self.interval_var = tk.StringVar(value=str(self.cfg["interval_minutes"]))
        self._field(row1, lambda m: self._spinbox(
            m, from_=1, to=180, width=5, textvariable=self.interval_var,
            command=self._on_field_change), height=30, width=78).pack(side="left")
        self._label(row1, "分钟", FONT, "sub").pack(side="left", padx=(8, 0))
        self._label(row1, "（1 ~ 180）", FONT_SMALL, "sub").pack(side="right")

        row1b = tk.Frame(c1, bg=t["card_bg"])
        row1b.pack(fill="x", padx=14, pady=(6, 2))
        self._label(row1b, "快捷设置", FONT_SMALL, "sub").pack(
            side="left", padx=(0, 6))
        # 高亮必须"跟着当前值走"：按钮只建一次，之后靠 _update_quick_btns()
        # 重算变体 —— 否则会固定在初始值上（点别的按钮绿色不动）。
        self._quick_btns = {}
        for mins in QUICK_INTERVALS:
            btn = PixelButton(row1b, f"{mins}分", lambda m=mins: self._set_interval(m),
                              variant="soft", font=FONT_SMALL, height=28,
                              padx=14, bg=t["card_bg"])
            btn.pack(side="left", padx=(0, 5))
            self._quick_btns[mins] = btn
        self._update_quick_btns()

        # --- 提醒文案 ---
        c2 = self._card(page)
        self._title(c2, "scroll", "提醒文案（每行一条，轮流展示）",
                    padx=14, pady=(3, 4))
        self.text = None
        self._text_field, self.text = self._field_native(
            c2, lambda cv: tk.Text(cv, height=5, font=FONT, wrap="word",
                                   relief="flat", bd=0, highlightthickness=0,
                                   bg=t["input_bg"], fg=t["text"], padx=8, pady=6,
                                   insertbackground=t["text"],
                                   selectbackground=t["accent"]),
            height=118)
        self.text.insert("1.0", "\n".join(self.cfg["messages"]))
        self._text_field.pack(fill="x", padx=14, pady=(0, 2))
        self.text.bind("<KeyRelease>", lambda e: self._on_field_change())

        row2 = tk.Frame(c2, bg=t["card_bg"])
        row2.pack(fill="x", padx=14, pady=(6, 3))
        self.random_var = tk.BooleanVar(value=self.cfg["random_order"])
        PixelRadio(row2, "顺序轮流", self.random_var, False,
                   command=self._on_field_change, bg=t["card_bg"]).pack(side="left")
        PixelRadio(row2, "随机", self.random_var, True,
                   command=self._on_field_change, bg=t["card_bg"]).pack(
                       side="left", padx=(18, 0))

    # ---------- 标签页二：打卡提醒 ----------
    def _build_page_checkin(self, page):
        t = self.t
        card = self._card(page, pady=(2, 6))
        head = tk.Frame(card, bg=t["card_bg"])
        head.pack(fill="x", padx=14, pady=(3, 2))
        ic = ImageTk.PhotoImage(pixelart.icon("checklist", 18))
        il = tk.Label(head, image=ic, bg=t["card_bg"], bd=0)
        il.image = ic                        # 见 IMG_NOTE
        il.pack(side="left")
        tk.Label(head, text="每日打卡（上下班共 4 次）", bg=t["card_bg"],
                 fg=t["text"], font=FONT_BOLD).pack(side="left", padx=(6, 0))
        PixelButton(head, "全部停用", lambda: self._set_all_checkins(False),
                    variant="soft", font=FONT_SMALL, height=28, padx=13,
                    bg=t["card_bg"]).pack(side="right")
        PixelButton(head, "全部启用", lambda: self._set_all_checkins(True),
                    variant="primary", font=FONT_SMALL, height=28, padx=13,
                    bg=t["card_bg"]).pack(side="right", padx=(0, 5))
        self._label(card, "到点弹出提醒打卡，可逐条开关；修改后自动保存。",
                    FONT_SMALL, "sub").pack(anchor="w", padx=14, pady=(2, 0))

        for i, item in enumerate(self.cfg["checkins"]):
            self._build_checkin_block(card, i, item)

    def _build_checkin_block(self, parent, idx, item):
        """一条打卡：勾选 + 名称（左）／时间（右），下一行是提示词。"""
        t = self.t
        if idx > 0:
            self._dotted(parent)

        row_a = tk.Frame(parent, bg=t["card_bg"])
        row_a.pack(fill="x", padx=14, pady=(4, 0))
        enabled = tk.BooleanVar(value=bool(item.get("enabled")))
        PixelCheck(row_a, item["label"], enabled, bg=t["card_bg"]).pack(side="left")

        # 时间控件右对齐，保证各行时间列整齐
        time_box = tk.Frame(row_a, bg=t["card_bg"])
        time_box.pack(side="right")
        self._label(time_box, "时间", FONT_SMALL, "sub").pack(side="left", padx=(0, 4))
        try:
            hh, mm = str(item["time"]).split(":")
        except (ValueError, AttributeError):
            hh, mm = "09", "00"
        hour = tk.StringVar(value=hh)
        minute = tk.StringVar(value=mm)
        self._field(time_box, lambda m: self._spinbox(
            m, from_=0, to=23, width=3, textvariable=hour,
            command=self._on_field_change), height=28, width=62).pack(side="left")
        self._label(time_box, "时", FONT_SMALL, "sub").pack(side="left", padx=(4, 0))
        self._field(time_box, lambda m: self._spinbox(
            m, from_=0, to=59, width=3, textvariable=minute,
            command=self._on_field_change), height=28, width=62).pack(side="left")
        self._label(time_box, "分", FONT_SMALL, "sub").pack(side="left", padx=(4, 0))

        row_b = tk.Frame(parent, bg=t["card_bg"])
        row_b.pack(fill="x", padx=14, pady=(4, 2))
        self._label(row_b, "提示词", FONT_SMALL, "sub").pack(side="left")
        msg = tk.StringVar(value=str(item.get("message", "")))
        fld, ent = self._field_native(
            row_b, lambda cv: self._entry(cv, textvariable=msg), height=28)
        fld.pack(side="left", fill="x", expand=True, padx=(8, 0))
        ent.bind("<KeyRelease>", lambda e: self._on_field_change())

        self._checkin_rows.append({
            "label": str(item["label"]), "enabled": enabled,
            "hour": hour, "minute": minute, "msg": msg,
            "default_msg": str(item.get("message", "")),
        })

    # ---------- 标签页三：设置 ----------
    def _build_page_settings(self, page):
        t = self.t

        # --- 通用设置 ---
        c1 = self._card(page, pady=(2, 6))
        self._title(c1, "gear", "通用设置", padx=14, pady=(3, 4))
        row1 = tk.Frame(c1, bg=t["card_bg"])
        row1.pack(fill="x", padx=14, pady=(0, 2))
        self._label(row1, "弹窗停留", FONT_BOLD).pack(side="left")
        self.seconds_var = tk.StringVar(value=str(self.cfg["popup_seconds"]))
        self._field(row1, lambda m: self._spinbox(
            m, from_=3, to=120, width=5, textvariable=self.seconds_var,
            command=self._on_field_change), height=30, width=78).pack(
                side="left", padx=(14, 0))
        self._label(row1, "秒", FONT, "sub").pack(side="left", padx=(8, 0))

        row1b = tk.Frame(c1, bg=t["card_bg"])
        row1b.pack(fill="x", padx=14, pady=(8, 2))
        self.sound_var = tk.BooleanVar(value=self.cfg["sound"])
        self.autostart_var = tk.BooleanVar(value=self.cfg["auto_start"])
        PixelCheck(row1b, "弹窗时响提示音", self.sound_var,
                   bg=t["card_bg"]).pack(side="left")
        PixelCheck(row1b, "开机自动启动", self.autostart_var,
                   command=self._on_autostart_toggle,
                   bg=t["card_bg"]).pack(side="left", padx=(22, 0))

        # 弹窗个数 / 稍后提醒（v1.9）
        row1c = tk.Frame(c1, bg=t["card_bg"])
        row1c.pack(fill="x", padx=14, pady=(8, 2))
        self._label(row1c, "弹窗个数", FONT_SMALL, "sub").pack(side="left")
        self.popup_count_var = tk.StringVar(value=str(self.cfg["popup_count"]))
        self._field(row1c, lambda m: self._spinbox(
            m, from_=1, to=config.MAX_POPUP_COUNT, width=3,
            textvariable=self.popup_count_var,
            command=self._on_field_change), height=28, width=62).pack(
                side="left", padx=(6, 0))
        self._label(row1c, "个（铺在桌面不同位置）",
                    FONT_SMALL, "sub").pack(side="left", padx=(6, 0))

        row1d = tk.Frame(c1, bg=t["card_bg"])
        row1d.pack(fill="x", padx=14, pady=(6, 2))
        self._label(row1d, "稍后提醒", FONT_SMALL, "sub").pack(side="left")
        self.defer_minutes_var = tk.StringVar(
            value=str(self.cfg["defer_minutes"]))
        self._field(row1d, lambda m: self._spinbox(
            m, from_=1, to=60, width=3, textvariable=self.defer_minutes_var,
            command=self._on_field_change), height=28, width=62).pack(
                side="left", padx=(6, 0))
        self._label(row1d, "分钟（休息弹窗第二个按钮）",
                    FONT_SMALL, "sub").pack(side="left", padx=(6, 0))

        # --- 按钮文案 ---
        c2 = self._card(page)
        self._title(c2, "heart", "弹窗按钮文案", padx=14, pady=(3, 4))
        row2 = tk.Frame(c2, bg=t["card_bg"])
        row2.pack(fill="x", padx=14, pady=(0, 4))
        self._label(row2, "休息弹窗", FONT_SMALL, "sub", width=8,
                    anchor="w").pack(side="left")
        self.button_text_var = tk.StringVar(
            value=self.cfg.get("button_text", "知道了，继续干活"))
        f1, e1 = self._field_native(
            row2, lambda cv: self._entry(cv, textvariable=self.button_text_var),
            height=28)
        f1.pack(side="left", fill="x", expand=True, padx=(8, 0))
        e1.bind("<KeyRelease>", lambda e: self._on_field_change())

        row2b = tk.Frame(c2, bg=t["card_bg"])
        row2b.pack(fill="x", padx=14, pady=(0, 4))
        self._label(row2b, "打卡弹窗", FONT_SMALL, "sub", width=8,
                    anchor="w").pack(side="left")
        self.checkin_button_var = tk.StringVar(
            value=self.cfg.get("checkin_button_text", "已打卡，继续"))
        f2, e2 = self._field_native(
            row2b, lambda cv: self._entry(
                cv, textvariable=self.checkin_button_var), height=28)
        f2.pack(side="left", fill="x", expand=True, padx=(8, 0))
        e2.bind("<KeyRelease>", lambda e: self._on_field_change())

        # --- 关于 ---
        c3 = self._card(page)
        self._title(c3, "info", f"关于 · 护眼助手 {APP_VERSION}",
                    padx=14, pady=(3, 4))
        self._label(c3,
                    "完全离线运行，不联网、不收集数据。\n"
                    "定时休息提醒（可「稍后提醒」）+ 每日 4 次上下班打卡提醒；\n"
                    "关闭窗口后仍在托盘后台运行。",
                    FONT_SMALL, "sub", justify="left").pack(
                        anchor="w", padx=14, pady=(0, 3))

    # ---------- 标签切换 ----------
    def _show_tab(self, key):
        if key not in self._pages:
            return
        self._active_tab = key
        for k, page in self._pages.items():
            if k == key:
                page.pack(fill="x")
            else:
                page.pack_forget()
        self._update_tab_buttons()
        self.root.update_idletasks()
        for card in self._cards:
            card._fit_height()
        self._resize_to_content()

    def _update_tab_buttons(self):
        for key, tab in self._tab_buttons.items():
            tab.set_active(key == self._active_tab)
        # 预览按钮随标签页变化：打卡页预览打卡弹窗
        self.preview_btn.configure(
            text="预览打卡" if self._active_tab == "checkin" else "预览弹窗")

    def _on_preview(self):
        """预览弹窗：打卡页预览打卡弹窗，其余页预览休息弹窗。"""
        if self._active_tab == "checkin":
            self.app.preview_checkin_popup()
        else:
            self.app.preview_popup()

    def _resize_to_content(self):
        """按当前标签页内容高度调整窗口高度（宽度固定），避免空白或裁切。

        窗口未映射（如开机自启的隐藏启动）时 winfo_reqheight 不可信，
        此时跳过；窗口显示后由 <Map> 回调重新贴合。
        """
        if not self.root.winfo_viewable():
            return
        self.root.update_idletasks()
        h = max(MIN_H, self.root.winfo_reqheight())
        cap = self.root.winfo_screenheight() - 80      # 不超出屏幕
        self.root.geometry("%dx%d" % (WIN_W, min(h, cap)))

    def _on_map(self, event):
        """窗口显示时重新贴合内容高度（只需响应顶层窗口自身的 Map 事件）。"""
        if event.widget is self.root:
            self._resize_to_content()

    # ---------- 事件 ----------
    def _on_field_change(self):
        """任一设置变化：立即写入配置并保存。"""
        self.app.update_config(self._collect())
        self._update_quick_btns()

    def _update_quick_btns(self):
        """快捷间隔按钮高亮：只让"等于当前值"的那个是绿色。"""
        cur = self._clamp_int(self.interval_var.get(), 1, 180, 45)
        for mins, btn in getattr(self, "_quick_btns", {}).items():
            btn.set_variant("primary" if mins == cur else "soft")

    def _on_autostart_toggle(self):
        """开机自启：同步注册表，失败则回滚勾选。"""
        ok = self.app.set_autostart(self.autostart_var.get())
        if not ok:
            self.autostart_var.set(False)
            self.app.update_config(self._collect())
            from tkinter import messagebox
            messagebox.showwarning("提示", "写入开机自启注册表失败，已取消该设置。")
        else:
            self._on_field_change()

    def _set_interval(self, mins):
        self.interval_var.set(str(mins))
        self._on_field_change()

    def _set_all_checkins(self, enabled):
        """一键启用/停用全部打卡。"""
        for row in self._checkin_rows:
            row["enabled"].set(bool(enabled))
        self._on_field_change()

    @staticmethod
    def _clamp_int(value, lo, hi, default):
        try:
            return max(lo, min(hi, int(str(value).strip())))
        except (TypeError, ValueError):
            return default

    def _collect(self) -> dict:
        """收集界面上的全部值（文本按行拆分，过滤空行）。

        防御性限制：最多 100 条、单条最长 200 字符（与 config 校验一致）。
        """
        msgs = [m.strip() for m in self.text.get("1.0", "end").splitlines()]
        msgs = [m[:200] for m in msgs if m][:100]
        checkins = []
        for row in self._checkin_rows:
            hh = self._clamp_int(row["hour"].get(), 0, 23, 9)
            mm = self._clamp_int(row["minute"].get(), 0, 59, 0)
            checkins.append({
                "label": row["label"],
                "enabled": bool(row["enabled"].get()),
                "time": "%02d:%02d" % (hh, mm),
                "message": row["msg"].get().strip() or row["default_msg"],
            })
        return {
            "interval_minutes": self._clamp_int(self.interval_var.get(), 1, 180, 45),
            "messages": msgs or ["该休息一下眼睛啦！"],
            "random_order": bool(self.random_var.get()),
            "popup_seconds": self._clamp_int(self.seconds_var.get(), 3, 120, 10),
            "popup_count": self._clamp_int(self.popup_count_var.get(), 1,
                                           config.MAX_POPUP_COUNT, 1),
            "defer_minutes": self._clamp_int(self.defer_minutes_var.get(), 1, 60, 5),
            "sound": bool(self.sound_var.get()),
            "auto_start": bool(self.autostart_var.get()),
            "running": self.cfg["running"],
            "checkins": checkins,
            "button_text": self.button_text_var.get().strip() or "知道了，继续干活",
            "checkin_button_text": self.checkin_button_var.get().strip()
                                   or "已打卡，继续",
        }

    # ---------- 状态刷新 ----------
    def _update_toggle_btn(self):
        running = self.cfg["running"]
        self.toggle_btn.configure(text="暂停提醒" if running else "开始提醒")
        self.toggle_btn.set_variant("warn" if running else "primary")

    def _tick_status(self):
        self._refresh_status()
        self.root.after(1000, self._tick_status)

    def _refresh_status(self):
        """按钮中间的倒计时：显示休息与最近一次打卡的剩余时间，每秒跳动。"""
        st = self.app.scheduler.status()
        if not st["running"]:
            self.countdown_label.configure(text="提醒已暂停",
                                           fg=self.t["status_pause"])
            return
        parts = []
        if st["rest"] >= 0:
            mins, secs = divmod(int(st["rest"]), 60)
            parts.append(f"休息 {mins}分{secs:02d}秒")
        if st.get("checkin", -1) >= 0:
            hours, rem = divmod(int(st["checkin"]), 3600)
            mins, secs = divmod(rem, 60)
            label = st.get("checkin_label") or "打卡"
            parts.append(f"{label} {hours}时{mins:02d}分{secs:02d}秒")
        self.countdown_label.configure(
            text=" · ".join(parts) if parts else "提醒运行中",
            fg=self.t["status_ok"])

    def show_saved_hint(self):
        self.saved_label.configure(text=f"已自动保存 {time.strftime('%H:%M:%S')}")
        self.spark.start()
        self.root.after(3000, self._hide_saved_hint)

    def _hide_saved_hint(self):
        self.saved_label.configure(text="")
        self.spark.stop()
