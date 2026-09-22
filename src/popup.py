# -*- coding: utf-8 -*-
"""提醒弹窗：无边框、置顶、像素木牌外观、滑入滑出动画。

外观：整块底板由 pixelart.popup_frame 在原生低分辨率上逐像素绘制后
整数倍放大 —— 阶梯圆角木框 + 顶部草绿色带 + Bayer 抖动羊皮纸内胆 +
铆钉与角落草花装饰。角外保持完全透明（靠 -transparentcolor 真正镂空）。

要点：绝不调用 focus_force()（不抢用户键盘焦点），仅置顶展示。

历史沿革（保留以兼容旧调用方）：
- v1.2 标题居中、休息弹窗按钮文字可自定义
- v1.5 固定在屏幕正中央，自适应分辨率/DPI
- v1.6 支持皮肤参数 theme_name（现已固定为单一像素样式，参数保留兼容）
- v1.7 新增 title / hint 覆盖参数，支持 kind="checkin"（打卡提醒）
- v1.8 像素风：外形改为程序化像素木牌，动画改为阶梯帧（8~12fps 手感）
- v1.9 休息弹窗加第二个按钮「稍后 N 分钟」（defer_minutes > 0 时出现）；
       同一次提醒可同时弹多个（layout_positions 给出互不重叠的桌面落点），
       点击任意一个按钮即关闭全部（on_dismiss 回调由调用方实现）。
"""
import math
import tkinter as tk

from PIL import ImageTk

import pixelart
import theme
from fonts import SIZE_BODY, SIZE_SMALL, SIZE_TITLE, apply_defaults, spec

TRANSPARENT = "#010203"     # 设为透明的颜色键

W, H = 340, 212             # 弹窗尺寸
MARGIN = 20                 # 距屏幕边缘边距（默认落点用）
RADIUS = 18                 # 圆角半径（旧字段，保留兼容）
STRIP_H = 9                 # 顶部色带高度

BTN_W, BTN_H = 176, 38      # 按钮尺寸（单按钮时的默认值）
BTN_GAP = 10                # 双按钮之间的间距
BTN_PAD = 14                # 按钮文字左右留白
BTN_MIN_W = 68              # 双按钮压缩后的最小宽度

MAX_POPUPS = 6              # 同一次提醒最多同时弹出的个数（与 config 保持一致）

# 多弹窗落点：按数量给出「屏幕可用区域内的相对位置」(fx, fy)，0=贴左/上，1=贴右/下。
# 选点原则是尽量分散、彼此不相邻 —— 多弹窗的目的就是"总有一个能被看到"。
_FLOATS = {
    2: ((0.0, 0.0), (1.0, 1.0)),
    3: ((0.0, 0.0), (0.5, 0.5), (1.0, 1.0)),
    4: ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)),
    5: ((0.0, 0.0), (1.0, 0.0), (0.5, 0.5), (0.0, 1.0), (1.0, 1.0)),
    6: ((0.0, 0.0), (0.5, 0.0), (1.0, 0.0), (0.0, 1.0), (0.5, 1.0), (1.0, 1.0)),
}


# 弹窗用字体（统一来自 fonts.py，随像素字体一起切换）
_F_BTN = spec(SIZE_BODY, bold=True)      # 按钮文字
_F_TITLE = spec(SIZE_TITLE, bold=True)   # 标题
_F_MSG = spec(SIZE_BODY)                 # 正文
_F_HINT = spec(SIZE_SMALL)               # 底部小字


# ---------- 多弹窗落点 ----------

def _rects_overlap(pts, w, h, gap):
    """检查给出的一批落点是否两两重叠（含 gap 间隙）。"""
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            (ax, ay), (bx, by) = pts[i], pts[j]
            if ax < bx + w + gap and bx < ax + w + gap and \
                    ay < by + h + gap and by < ay + h + gap:
                return True
    return False


def _grid_positions(count, sw, sh, w, h, margin, gap):
    """兜底排布：算一个能装下的网格，整块居中（小屏/超多弹窗时用）。"""
    cols = max(1, (sw - 2 * margin + gap) // max(1, w + gap))
    rows = max(1, (sh - 2 * margin + gap) // max(1, h + gap))
    best = None
    for c in range(1, cols + 1):
        r = (count + c - 1) // c
        if r > rows:
            continue
        score = (c * r, abs(c - r))
        if best is None or score < best[0]:
            best = (score, c, r)
    c, r = (best[1], best[2]) if best else (cols, rows)
    x0 = max(margin, (sw - (c * w + (c - 1) * gap)) // 2)
    y0 = max(margin, (sh - (r * h + (r - 1) * gap)) // 2)
    return [(x0 + (i % c) * (w + gap), y0 + (i // c) * (h + gap))
            for i in range(count)]


def layout_positions(count, sw, sh, w=W, h=H, margin=MARGIN, gap=BTN_GAP):
    """给出 count 个弹窗在屏幕上的落点（左上角坐标），互不重叠。

    - count == 1：屏幕正中央（与 v1.5 起的既有行为完全一致）
    - count >= 2：铺到桌面的不同位置（对角 / 四角 / 上下边），先分散再兜底，
      屏幕过小时自动回退成居中网格排布，保证不叠在一起。
    """
    try:
        count = int(count)
    except (TypeError, ValueError):
        count = 1
    count = max(1, min(MAX_POPUPS, count))
    if count == 1:
        return [((sw - w) // 2, (sh - h) // 2)]
    ax = max(0, sw - w - 2 * margin)
    ay = max(0, sh - h - 2 * margin)
    pts = [(margin + int(round(ax * fx)), margin + int(round(ay * fy)))
           for fx, fy in _FLOATS[count]]
    if _rects_overlap(pts, w, h, gap):
        pts = _grid_positions(count, sw, sh, w, h, margin, gap)
    return pts


def _pair_widths(label_a, label_b, avail=W - 2 * 28):
    """双按钮宽度分配：按文字实际宽度算，总宽超限时等比压缩（不低于 BTN_MIN_W）。"""
    import tkinter.font as tkfont
    n = tkfont.Font(font=_F_BTN)
    wa = n.measure(label_a) + 2 * BTN_PAD
    wb = n.measure(label_b) + 2 * BTN_PAD
    if wa + wb + BTN_GAP > avail:
        scale = (avail - BTN_GAP) / float(max(1, wa + wb))
        wa = max(BTN_MIN_W, int(wa * scale))
        wb = max(BTN_MIN_W, int(wb * scale))
    return wa, wb


def _lerp_color(c1, c2, t):
    """两个 #rrggbb 颜色按比例 t 插值（旧接口，保留兼容）。"""
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    return "#%02x%02x%02x" % (
        int(r1 + (r2 - r1) * t),
        int(g1 + (g2 - g1) * t),
        int(b1 + (b2 - b1) * t),
    )


def _rounded_rows(canvas, x1, y1, x2, y2, radius, color_fn, step=4,
                  apply_top=True, apply_bottom=True):
    """逐行绘制矩形条并按弧形圆角裁切（旧实现，保留兼容；像素风已改用 PNG 底板）。"""
    w = x2 - x1
    h = y2 - y1
    r = radius
    for i in range(0, h, step):
        y = y1 + i
        left, right = 0.0, float(w)
        if apply_top:
            dy_top = r - (y - y1)
            if 0 < dy_top <= r:
                dx = r - math.sqrt(max(0.0, r * r - dy_top * dy_top))
                left = max(left, dx)
                right = min(right, w - dx)
        if apply_bottom:
            dy_bot = r - (y2 - y)
            if 0 < dy_bot <= r:
                dx = r - math.sqrt(max(0.0, r * r - dy_bot * dy_bot))
                left = max(left, dx)
                right = min(right, w - dx)
        if right - left < 1:
            continue
        t = i / max(1, h - 1)
        canvas.create_rectangle(x1 + left, y, x1 + right, min(y2, y + step),
                                fill=color_fn(t), outline="")


def _sanitize_text(text, limit=110):
    """清洗弹窗文案：保留换行、折叠行内空白、去除控制字符、超长截断。

    安全考量：过滤 C0 控制字符（\\x00-\\x08 等）与 DEL，避免异常字符
    导致界面渲染异常；限制总长度防止超长文本耗尽渲染资源。
    """
    if text is None:
        return "休息一下吧"
    if not isinstance(text, str):
        text = str(text)
    text = "".join(ch for ch in text if ch >= "\x20" or ch in "\n\t")
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    lines = [" ".join(line.split()) for line in lines]
    text = "\n".join(lines)
    if len(text) > limit:
        text = text[:limit] + "…"
    return text or "休息一下吧"


class _PixelButton(tk.Canvas):
    """弹窗内的像素按钮：三态 + 文字描边（variant: primary / soft）。"""

    def __init__(self, master, text, command, width=BTN_W, height=BTN_H,
                 variant="primary"):
        t = theme.get()["window"]
        super().__init__(master, width=width, height=height, bg=TRANSPARENT,
                         highlightthickness=0, bd=0, cursor="hand2")
        self._text = text
        self._command = command
        self._variant = variant if variant in ("primary", "soft", "warn") \
            else "primary"
        # 配色规则与主界面 PixelButton 一致：深底用浅字+墨线，浅底用深字+奶油线
        self._fg = t["accent_fg"] if self._variant == "primary" else t["soft_fg"]
        self._outline = t["ink"] if self._variant == "primary" else t["pap_lt"]
        self._state = ""
        # 注意：不能用 self._w —— 那是 tkinter 内部的 Tcl 路径名
        self._bw, self._bh = width, height
        self._imgs = {s: ImageTk.PhotoImage(
            pixelart.button(width, height, self._variant + s))
            for s in ("", "_hover", "_press")}
        self.bind("<Enter>", lambda e: self._set("_hover"))
        self.bind("<Leave>", lambda e: self._set(""))
        self.bind("<ButtonPress-1>", lambda e: self._set("_press"))
        self.bind("<ButtonRelease-1>", self._release)
        self._draw()

    def _set(self, s):
        if s != self._state:
            self._state = s
            self._draw()

    def _release(self, event):
        pressed = self._state == "_press"
        inside = 0 <= event.x <= self._bw and 0 <= event.y <= self._bh
        self._set("_hover" if inside else "")
        if pressed and inside and self._command:
            self._command()

    def _draw(self):
        self.delete("all")
        self.create_image(0, 0, image=self._imgs[self._state], anchor="nw")
        dy = 2 if self._state == "_press" else 0
        cx, cy = self._bw // 2, self._bh // 2 + dy
        for dx, ddy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            self.create_text(cx + dx, cy + ddy, text=self._text,
                             font=_F_BTN, fill=self._outline)
        self.create_text(cx, cy, text=self._text,
                         font=_F_BTN, fill=self._fg)


class ReminderPopup(tk.Toplevel):
    """kind: "rest"（休息提醒）/ "offwork"（下班提醒）/ "checkin"（打卡提醒）。

    "checkin" 由调用方通过 title/hint 传入标题与底部说明（如"上班打卡"）。
    """

    def __init__(self, master, message, remain_seconds=10,
                 next_interval_minutes=45, kind="rest", button_text="知道了，继续干活",
                 on_close=None, target=None, theme_name=None, title=None, hint=None,
                 defer_minutes=0, on_defer=None, on_dismiss=None):
        """button_text: 弹窗按钮文字（可自定义）；
        target: 落点坐标（多弹窗时由 layout_positions 给出；None=屏幕正中央）；
        theme_name: 皮肤键（历史参数，现为单一像素样式，仅保留兼容）；
        title / hint: 覆盖标题与底部说明（打卡弹窗用，None=按 kind 取默认）；
        defer_minutes: >0 时在按钮左侧多出一个「稍后 N 分钟」按钮（仅休息弹窗用）；
        on_defer: 点「稍后」时的回调，收到 defer_minutes；
        on_dismiss: 点任一按钮时的回调 —— 多弹窗场景下由调用方在这里关掉全部。
        """
        super().__init__(master)
        apply_defaults(self)      # 幂等：确保弹窗内原生控件也用像素字体
        self._message = _sanitize_text(message)
        self._remain_seconds = max(3, remain_seconds)
        self._next_minutes = max(1, next_interval_minutes)
        self._kind = kind
        self._button_text = button_text or "知道了，继续干活"
        self._title_override = str(title).strip() if title else None
        self._hint_override = str(hint).strip() if hint else None
        self._on_close = on_close
        self._closed = False
        self._fading = False      # 已在淡出中？（防止"一键全关"触发两次动画）
        self._c = theme.get(theme_name)["popup"]   # 配色（弹窗部分）
        self._hint_base = self._make_hint()        # 底部基准文案（倒计时前缀）
        # 「稍后提醒」按钮：只有休息弹窗才有 —— 打卡是"到点就该做"的事，
        # 延后它没有意义（调度器里的 defer 也只作用于休息计时）。
        try:
            defer_minutes = int(defer_minutes)
        except (TypeError, ValueError):
            defer_minutes = 0
        self._defer_minutes = defer_minutes if (defer_minutes > 0
                                                and kind == "rest") else 0
        self._on_defer = on_defer
        self._on_dismiss = on_dismiss

        # 窗口属性：无边框、置顶、透明色键、初始全透明
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-transparentcolor", TRANSPARENT)
        self.attributes("-alpha", 0.0)
        self.configure(bg=TRANSPARENT)

        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        if target is not None:
            self._target_x, self._target_y = int(target[0]), int(target[1])
        else:
            self._target_x, self._target_y = (sw - W) // 2, (sh - H) // 2
        self._start_x = self._target_x  # 从屏幕上方滑入
        # 落到屏幕下半部时改从下方滑入，避免"横穿整个桌面"的怪异走位
        self._start_y = -H if self._target_y <= (sh - H) // 2 else sh
        self.geometry(f"{W}x{H}+{self._start_x}+{self._start_y}")

        self._build_ui()
        self._animate_in(0)

    # ---------- 文案 ----------
    @property
    def _title(self):
        if self._title_override:
            return self._title_override
        return "下班时间到" if self._kind == "offwork" else "该休息啦"

    @property
    def _button_label(self):
        if self._title_override:
            return self._button_text      # 打卡等自定义弹窗：直接用传入文案
        return "知道啦，下班！" if self._kind == "offwork" else self._button_text

    @property
    def _defer_label(self):
        """第二个按钮的文案：「稍后 N 分钟」。"""
        return f"稍后 {self._defer_minutes} 分钟"

    @property
    def _icon_name(self):
        """标题左侧的像素小图标（装饰，也帮助一眼区分弹窗类型）。"""
        return {"offwork": "clock", "checkin": "checklist"}.get(self._kind, "eye")

    def _make_hint(self):
        """底部基准说明文字；倒计时在其后追加"（Ns 自动关闭）"。"""
        if self._hint_override:
            return self._hint_override
        if self._kind == "offwork":
            return "今天辛苦啦，明天见，注意休息"
        return f"下次提醒 {self._next_minutes} 分钟后"

    # ---------- 界面 ----------
    def _build_ui(self):
        cv = tk.Canvas(self, width=W, height=H, bg=TRANSPARENT,
                       highlightthickness=0, bd=0)
        cv.pack(fill="both", expand=True)
        self._cv = cv

        t = theme.get()["window"]
        # 像素木牌底板（角外透明）
        self._bg_img = ImageTk.PhotoImage(pixelart.popup_frame(W, H, STRIP_H))
        cv.create_image(0, 0, image=self._bg_img, anchor="nw")

        # 标题（像素小图标 + 带描边的文字，整体居中）
        import tkinter.font as tkfont
        f_title = _F_TITLE
        tw = tkfont.Font(font=f_title).measure(self._title)
        ico = ImageTk.PhotoImage(pixelart.icon(self._icon_name, 20))
        self._ico_img = ico
        gap = 7
        x0 = (W - (ico.width() + gap + tw)) // 2
        cv.create_image(x0, 54, image=ico, anchor="w")
        tx = x0 + ico.width() + gap + tw // 2
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            cv.create_text(tx + dx, 54 + dy, text=self._title, font=f_title,
                           fill=t["ink"])
        cv.create_text(tx, 54, text=self._title, font=f_title, fill=t["text"])

        # 正文（自动换行居中）
        cv.create_text(W / 2, 108, width=W - 56, justify="center",
                       text=self._message, fill=t["text"], font=_F_MSG)

        # 按钮：主按钮（像素草地绿）；休息弹窗左侧再挂一个「稍后 N 分钟」
        self._defer_btn = None
        if self._defer_minutes:
            wa, wb = _pair_widths(self._button_label, self._defer_label)
            x0 = (W - (wa + BTN_GAP + wb)) // 2
            self._btn = _PixelButton(self, self._button_label, self._close_now,
                                     width=wa, height=BTN_H)
            cv.create_window(x0 + wa // 2, 164, window=self._btn,
                             width=wa, height=BTN_H)
            self._defer_btn = _PixelButton(self, self._defer_label,
                                           self._defer_now, width=wb,
                                           height=BTN_H, variant="soft")
            cv.create_window(x0 + wa + BTN_GAP + wb // 2, 164,
                             window=self._defer_btn, width=wb, height=BTN_H)
        else:
            self._btn = _PixelButton(self, self._button_label, self._close_now)
            cv.create_window(W / 2, 164, window=self._btn,
                             width=BTN_W, height=BTN_H)

        # 底部小字
        self._hint = cv.create_text(W / 2, 196, text=self._hint_base,
                                    fill=t["sub"], font=_F_HINT)

    # ---------- 动画（阶梯帧：像素风要的是"跳帧"，不是平滑过渡） ----------
    IN_STEPS = 8        # 入场帧数（8 帧 @40ms ≈ 12fps）
    OUT_STEPS = 6       # 淡出基准帧数（step=0 表示立即销毁）

    def _animate_in(self, step):
        if self._closed:
            return
        progress = min(1.0, step / float(self.IN_STEPS))
        x = self._start_x + int((self._target_x - self._start_x) * progress)
        y = self._start_y + int((self._target_y - self._start_y) * progress)
        self.geometry(f"{W}x{H}+{x}+{y}")
        # 透明度只取 4 档（不是逐帧线性），观感是"一格格亮起来"
        self.attributes("-alpha", round(progress * 3) / 3.0)
        if progress < 1.0:
            self.after(40, lambda: self._animate_in(step + 1))
        else:
            self.attributes("-alpha", 1.0)
            self.geometry(f"{W}x{H}+{self._target_x}+{self._target_y}")
            self._schedule_auto_close()

    def _schedule_auto_close(self):
        self._countdown = self._remain_seconds
        self._tick_countdown()

    def _tick_countdown(self):
        """每秒倒计时，到点自动淡出；底部小字同步显示剩余秒数（每秒跳动）。"""
        if self._closed:
            return
        self._countdown -= 1
        if self._countdown <= 0:
            self._animate_out(6)
            return
        try:
            text = f"{self._hint_base}（{self._countdown}s 自动关闭）"
            self._cv.itemconfig(self._hint, text=text)
        except tk.TclError:
            pass
        self.after(1000, self._tick_countdown)

    def _animate_out(self, step=None):
        """开始淡出。重复调用无效（多弹窗"一键全关"时会重复触发）。

        step 越大淡出越慢：6=自动关闭，4=点击按钮，0=立即销毁。
        """
        if self._closed or self._fading:
            return
        self._fading = True
        self._fade_step(self.OUT_STEPS if step is None else step)

    def _fade_step(self, step):
        if self._closed:
            return
        alpha = step / float(self.OUT_STEPS)
        if alpha <= 0.0:
            self._destroy_popup()
            return
        self.attributes("-alpha", round(alpha * 3) / 3.0)
        self.after(40, lambda: self._fade_step(step - 1))

    def _close_now(self):
        """点击主按钮：通知调用方关闭同批弹窗，然后加速淡出。"""
        if self._closed:
            return
        self._notify_dismiss()
        self._animate_out(4)

    def _defer_now(self):
        """点击「稍后 N 分钟」：重置休息计时（交给调用方），并关闭同批弹窗。"""
        if self._closed:
            return
        self._notify_dismiss()
        if self._on_defer:
            try:
                self._on_defer(self._defer_minutes)
            except Exception:
                pass
        self._animate_out(4)

    def _notify_dismiss(self):
        """告知调用方"用户已处理这条提醒"（多弹窗时由它关掉全部）。"""
        if self._on_dismiss:
            try:
                self._on_dismiss()
            except Exception:
                pass

    def _destroy_popup(self):
        if self._closed:
            return
        self._closed = True
        try:
            self.destroy()
        except tk.TclError:
            pass
        if self._on_close:
            try:
                self._on_close(self)      # 带上自己，便于多弹窗时从列表摘除
            except Exception:
                pass
