# -*- coding: utf-8 -*-
"""星露谷像素风外观 —— 可行性验证（PoC）

核心手法：全部图形都在 **低分辨率原生像素** 上绘制（16px 左右），
再用整数倍 NEAREST 放大 —— 这样得到的是真正的像素画，边缘硬朗、
无抗锯齿模糊，而不是"把矢量图形调成土黄色"。

输出：docs/preview/像素风-PoC-控件总览.png
"""
import os

from PIL import Image, ImageDraw, ImageFont

PREVIEW_DIR = r"D:\Test\AR\docs\preview"
FONT_DIR = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")

# ============ 星露谷配色（低饱和、暖调、高对比描边） ============
PAL = {
    # 描边 / 墨色
    "outline":   (61, 43, 31),
    "ink":       (58, 36, 22),
    "ink_sub":   (124, 92, 58),
    # 木质
    "wood_dk":   (92, 56, 28),
    "wood":      (139, 90, 43),
    "wood_mid":  (168, 116, 63),
    "wood_lt":   (200, 154, 91),
    "wood_hi":   (226, 190, 132),
    # 羊皮纸 / 奶油面板
    "pap_dk":    (214, 183, 132),
    "pap":       (245, 222, 179),
    "pap_lt":    (255, 246, 222),
    # 草绿（主强调）
    "grass_dk":  (43, 95, 28),
    "grass":     (94, 158, 61),
    "grass_mid": (122, 182, 74),
    "grass_lt":  (166, 214, 108),
    # 麦穗金
    "gold_dk":   (168, 118, 34),
    "gold":      (242, 193, 78),
    "gold_lt":   (255, 226, 142),
    # 红心 / 告警
    "red_dk":    (140, 34, 42),
    "red":       (204, 62, 62),
    "red_lt":    (240, 126, 118),
    # 天空蓝（瞳孔高光等）
    "sky":       (137, 196, 244),
    "white":     (255, 255, 255),
}


def load_font(size, bold=False):
    name = "msyhbd.ttc" if bold else "msyh.ttc"
    try:
        return ImageFont.truetype(os.path.join(FONT_DIR, name), size)
    except Exception:
        return ImageFont.load_default()


# ============ 像素形状原语 ============
def _insets(h, r):
    """阶梯式圆角：返回每一行需要左右内缩的像素数（像素画的"圆角"是台阶，不是弧线）。"""
    r = max(0, min(int(r), h // 2))
    if r == 0:
        return [0] * h
    return list(range(r, 0, -1)) + [0] * (h - 2 * r) + list(range(1, r + 1))


def shape(d, x, y, w, h, r, color):
    """绘制阶梯圆角实心块。"""
    if w <= 0 or h <= 0:
        return
    for i, ins in enumerate(_insets(h, r)):
        x0, x1 = x + ins, x + w - 1 - ins
        if x1 < x0:
            continue
        d.line([(x0, y + i), (x1, y + i)], fill=color)


def put(img, x, y, color, skip_outline=True):
    """单像素写入；跳过透明区（可选跳过描边色，避免高光溢出轮廓）。"""
    if not (0 <= x < img.width and 0 <= y < img.height):
        return
    p = img.getpixel((x, y))
    if p[3] == 0:
        return
    if skip_outline and p[:3] == PAL["outline"]:
        return
    img.putpixel((x, y), tuple(color) + (255,))


def pixel_box(w, h, r=4, border="wood", face="pap", band=2,
              border_hi=None, border_lo=None, face_hi=None, face_lo=None,
              outline="outline"):
    """像素风方框：外描边 → 边框（band px）→ 内胆，并按方向光加高光/暗边。

    这是整套外观的地基：卡片、按钮、输入框、标签栏全部由它派生，
    只换配色与 band 就能得到完全不同的质感（木质面板 / 草绿按钮 / 内凹输入框）。
    """
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    shape(d, 0, 0, w, h, r, PAL[outline])
    shape(d, 1, 1, w - 2, h - 2, max(0, r - 1), PAL[border])
    shape(d, 1 + band, 1 + band, w - 2 - 2 * band, h - 2 - 2 * band,
          max(0, r - 1 - band), PAL[face])

    if border_hi:
        c = PAL[border_hi]
        for x in range(2, w - 2):
            put(img, x, 1, c)
        for y in range(2, h - 2):
            put(img, 1, y, c)
    if border_lo:
        c = PAL[border_lo]
        for x in range(2, w - 2):
            put(img, x, h - 2, c)
        for y in range(2, h - 2):
            put(img, w - 2, y, c)
    if face_hi:
        y = 1 + band
        for x in range(3 + band, w - 3 - band):
            put(img, x, y, PAL[face_hi], False)
    if face_lo:
        y = h - 2 - band
        for x in range(3 + band, w - 3 - band):
            put(img, x, y, PAL[face_lo], False)
    return img


def add_nails(img, color="wood_dk", off=3):
    """木框四角铆钉（1 像素，像素画的标志性细节）。"""
    w, h = img.size
    c = PAL[color]
    for (x, y) in ((off, off - 1), (w - 1 - off, off - 1),
                   (off, h - off), (w - 1 - off, h - off)):
        put(img, x, y, c, False)
    return img


def add_grain(img, seed=7, n=7, color_lo="wood_dk", color_hi="wood_lt",
              inset=5, avoid_y=None, only_hi=False):
    """木纹：确定性伪随机的短横线（不引 random，保证每次构建完全一致）。

    avoid_y=(y0, y1)：该纵向区间的行不画木纹 —— 招牌用来给标题文字让位。
    """
    w, h = img.size
    if h <= 2 * inset + 4:
        return img
    x0 = inset
    span = max(1, w - 2 * inset)
    for i in range(n):
        s = (seed * 37 + i * 91) % span
        ln = 4 + (seed * 13 + i * 29) % 7
        y = inset + 1 + (i * (h - 2 * inset - 2)) // max(1, n)
        if avoid_y and avoid_y[0] <= y <= avoid_y[1]:
            continue
        col = PAL[color_hi] if only_hi else (
            PAL[color_lo] if i % 2 == 0 else PAL[color_hi])
        for k in range(ln):
            put(img, x0 + s + k, y, col, False)
    return img


def scale(img, factor):
    """整数倍 NEAREST 放大 —— 像素保持锐利，绝不产生插值模糊。"""
    return img.resize((img.width * factor, img.height * factor), Image.NEAREST)


# ============ 像素图标（原生 16×16 绘制） ============
ISZ = 16


def icon_coin(sz=ISZ):
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([0, 0, sz - 1, sz - 1], fill=PAL["gold_dk"])
    d.ellipse([1, 1, sz - 2, sz - 2], fill=PAL["gold"])
    d.ellipse([4, 4, sz - 5, sz - 5], fill=PAL["gold_dk"])
    d.ellipse([5, 5, sz - 6, sz - 6], fill=PAL["gold_lt"])
    put(img, 4, 3, PAL["white"], False)
    put(img, 5, 3, PAL["white"], False)
    put(img, 3, 4, PAL["white"], False)
    return img


def icon_heart(sz=ISZ):
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([0, 1, 7, 8], fill=PAL["red_dk"])
    d.ellipse([8, 1, 15, 8], fill=PAL["red_dk"])
    d.polygon([(0, 6), (15, 6), (7, 15)], fill=PAL["red_dk"])
    d.ellipse([1, 2, 7, 8], fill=PAL["red"])
    d.ellipse([8, 2, 14, 8], fill=PAL["red"])
    d.polygon([(1, 6), (14, 6), (7, 14)], fill=PAL["red"])
    put(img, 3, 3, PAL["red_lt"], False)
    put(img, 4, 3, PAL["red_lt"], False)
    put(img, 3, 4, PAL["red_lt"], False)
    return img


def icon_clock(sz=ISZ):
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([0, 0, sz - 1, sz - 1], fill=PAL["outline"])
    d.ellipse([1, 1, sz - 2, sz - 2], fill=PAL["wood_lt"])
    d.ellipse([3, 3, sz - 4, sz - 4], fill=PAL["pap_lt"])
    for p in ((7, 2), (7, 13), (2, 7), (13, 7)):
        put(img, p[0], p[1], PAL["wood_dk"], False)
    for y in range(4, 9):
        put(img, 7, y, PAL["ink"], False)
    for x in range(8, 12):
        put(img, x, 8, PAL["ink"], False)
    return img


def icon_seed(sz=ISZ):
    """种子袋（星露谷里最标志性的物品之一）。"""
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([2, 3, sz - 3, sz - 1], fill=PAL["outline"])
    d.rectangle([3, 4, sz - 4, sz - 2], fill=PAL["pap"])
    d.rectangle([3, 4, sz - 4, 6], fill=PAL["pap_dk"])
    d.rectangle([5, 0, sz - 6, 3], fill=PAL["outline"])
    d.rectangle([6, 1, sz - 7, 2], fill=PAL["wood_mid"])
    # 嫩芽
    d.rectangle([7, 8, 8, 13], fill=PAL["grass_dk"])
    d.rectangle([4, 9, 7, 11], fill=PAL["grass"])
    d.rectangle([8, 7, 11, 9], fill=PAL["grass"])
    put(img, 5, 9, PAL["grass_lt"], False)
    return img


def icon_eye(sz=ISZ):
    """护眼主题的眼睛图标（应用 Logo / 托盘用）。"""
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon([(0, 8), (4, 3), (11, 3), (15, 8), (11, 12), (4, 12)],
              fill=PAL["outline"])
    d.polygon([(1, 8), (5, 4), (10, 4), (14, 8), (10, 11), (5, 11)],
              fill=PAL["pap_lt"])
    d.ellipse([5, 5, 10, 10], fill=PAL["ink"])
    d.ellipse([6, 6, 9, 9], fill=PAL["grass"])
    put(img, 7, 6, PAL["white"], False)
    put(img, 6, 7, PAL["white"], False)
    return img


def icon_check(sz=ISZ):
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.line([(2, 8), (7, 13)], fill=PAL["outline"], width=4)
    d.line([(7, 13), (14, 3)], fill=PAL["outline"], width=4)
    d.line([(3, 8), (7, 12)], fill=PAL["grass"], width=2)
    d.line([(7, 12), (13, 4)], fill=PAL["grass"], width=2)
    return img


def icon_cross(sz=ISZ):
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.line([(2, 3), (13, 12)], fill=PAL["outline"], width=4)
    d.line([(13, 3), (2, 12)], fill=PAL["outline"], width=4)
    d.line([(3, 4), (12, 11)], fill=PAL["red"], width=2)
    d.line([(12, 4), (3, 11)], fill=PAL["red"], width=2)
    return img


def icon_gear(sz=ISZ):
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([2, 2, sz - 3, sz - 3], fill=PAL["outline"])
    for (cx, cy) in ((6, 0), (9, 0), (6, 13), (9, 13),
                     (0, 6), (0, 9), (13, 6), (13, 9)):
        d.rectangle([cx, cy, cx + 2, cy + 2], fill=PAL["outline"])
    d.ellipse([3, 3, sz - 4, sz - 4], fill=PAL["wood_mid"])
    d.ellipse([5, 5, sz - 6, sz - 6], fill=PAL["wood_lt"])
    d.ellipse([6, 6, sz - 7, sz - 7], fill=PAL["outline"])
    put(img, 4, 4, PAL["wood_hi"], False)
    return img


ICONS = [
    ("金币", icon_coin), ("爱心", icon_heart), ("时钟", icon_clock),
    ("种子袋", icon_seed), ("眼睛", icon_eye), ("勾选", icon_check),
    ("叉号", icon_cross), ("齿轮", icon_gear),
]


# ============ 组装：控件总览图 ============
SF = 4            # 放大倍数
GAP = 14          # 原生像素间距
LABEL_H = 26      # 标签行高（放大后）


def build_overview():
    # ---- 第 1 行：木质卡片面板（大小两种） ----
    card_big = add_nails(add_grain(pixel_box(150, 90, r=5, border="wood",
                                             face="pap", band=2,
                                             border_hi="wood_lt", border_lo="wood_dk",
                                             face_hi="pap_lt", face_lo="pap_dk"),
                                   seed=3, n=5))
    card_small = add_nails(pixel_box(70, 44, r=4, border="wood", face="pap", band=2,
                                     border_hi="wood_lt", border_lo="wood_dk",
                                     face_hi="pap_lt", face_lo="pap_dk"))
    banner = add_nails(add_grain(pixel_box(150, 40, r=4, border="wood_dk",
                                           face="wood_mid", band=2,
                                           border_hi="wood_lt", border_lo="wood_dk"),
                                 seed=11, n=5, only_hi=True), color="gold")

    # ---- 第 2 行：按钮三态 ----
    def btn(state):
        if state == "normal":
            return pixel_box(64, 22, r=3, border="grass_dk", face="grass", band=1,
                             border_hi="grass_lt", border_lo="grass_dk",
                             face_hi="grass_lt", face_lo="grass_dk")
        if state == "hover":
            return pixel_box(64, 22, r=3, border="grass_dk", face="grass_mid", band=1,
                             border_hi="grass_lt", border_lo="grass_dk",
                             face_hi="grass_lt", face_lo="grass_dk")
        return pixel_box(64, 22, r=3, border="grass_dk", face="grass_dk", band=1,
                         border_hi="grass", border_lo="outline",
                         face_hi="grass", face_lo="outline")

    def btn2(state):
        c = {"normal": "wood_lt", "hover": "wood_hi", "pressed": "wood_mid"}[state]
        return pixel_box(64, 22, r=3, border="wood_dk", face=c, band=1,
                         border_hi="wood_hi", border_lo="wood_dk",
                         face_hi="wood_hi", face_lo="wood_dk")

    # ---- 第 3 行：标签栏 ----
    def tab(active):
        return pixel_box(58, 20, r=3,
                         border="wood_dk" if active else "wood",
                         face="wood_dk" if active else "wood_lt", band=1,
                         border_hi="wood_mid" if active else "wood_hi",
                         border_lo="outline" if active else "wood_dk",
                         face_hi="wood_mid" if active else "wood_hi",
                         face_lo="outline" if active else "wood_dk")

    # ---- 第 4 行：输入框 / 复选 ----
    inp = pixel_box(96, 20, r=3, border="wood_dk", face="pap_lt", band=1,
                    border_hi="outline", border_lo="pap_lt",
                    face_hi="outline", face_lo="pap_lt")   # 内凹：明暗反转
    chk_on = pixel_box(16, 16, r=2, border="wood_dk", face="grass", band=1,
                       border_hi="grass_lt", border_lo="grass_dk")
    chk_off = pixel_box(16, 16, r=2, border="wood_dk", face="pap_lt", band=1,
                        border_hi="outline", border_lo="pap_lt")
    # 把勾画进勾选框
    ck = icon_check(16)
    for x in range(16):
        for y in range(16):
            p = ck.getpixel((x, y))
            if p[3] and p[:3] == PAL["grass"]:
                put(chk_on, x, y, PAL["grass_lt"], False)
    chk_on = pixel_box(16, 16, r=2, border="wood_dk", face="grass", band=1,
                       border_hi="grass_lt", border_lo="grass_dk")
    d = ImageDraw.Draw(chk_on)
    d.line([(3, 8), (6, 12)], fill=PAL["outline"], width=3)
    d.line([(6, 12), (12, 3)], fill=PAL["outline"], width=3)
    d.line([(4, 8), (6, 11)], fill=PAL["pap_lt"], width=1)
    d.line([(6, 11), (11, 4)], fill=PAL["pap_lt"], width=1)

    # ---- 逐行布局 ----
    rows = []
    rows.append((["大卡片 / 面板", "小卡片", "木质招牌"], [card_big, card_small, banner]))
    rows.append((["主按钮 常态", "悬停", "按下"], [btn("normal"), btn("hover"), btn("pressed")]))
    rows.append((["次按钮 常态", "悬停", "按下"], [btn2("normal"), btn2("hover"), btn2("pressed")]))
    rows.append((["标签 选中", "标签 未选"], [tab(True), tab(False)]))
    rows.append((["输入框（内凹）", "勾选框 选中", "未选"], [inp, chk_on, chk_off]))

    # 图标行单独处理
    icon_row = [f(ISZ) for _, f in ICONS]
    icon_labels = [n for n, _ in ICONS]

    # ---- 全部尺寸先按"原生像素"算，最后统一 ×SF ----
    PAD = 18          # 画布内边距
    TITLE_H = 30      # 顶部标题band
    LAB_GAP = 9       # 每个控件上方的文字标签高度

    heights = [max(im.height for im in imgs) for _, imgs in rows]
    widths = [sum(im.width for im in imgs) + GAP * (len(imgs) - 1) for _, imgs in rows]
    icon_w = ISZ * len(icon_row) + GAP * (len(icon_row) - 1)
    content_w = max(max(widths), icon_w)

    content_h = TITLE_H + sum(h + LAB_GAP for h in heights) + ISZ + LAB_GAP

    W = (content_w + PAD * 2) * SF
    H = (content_h + PAD * 2) * SF

    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    frame = pixel_box(W - 4, H - 4, r=6, border="wood_dk", face="wood",
                      band=3, border_hi="wood_lt", border_lo="wood_dk")
    add_nails(frame, color="gold", off=5)
    canvas.paste(frame, (2, 2), frame)

    y = PAD + TITLE_H
    texts = []
    for (labels, imgs), rh in zip(rows, heights):
        x = PAD
        for lab, im in zip(labels, imgs):
            up = scale(im, SF)
            canvas.paste(up, (x * SF, y * SF), up)
            texts.append((lab, x * SF, y * SF - 22))
            x += im.width + GAP
        y += rh + LAB_GAP

    x = PAD
    for lab, im in zip(icon_labels, icon_row):
        up = scale(im, SF)
        canvas.paste(up, (x * SF, y * SF), up)
        texts.append((lab, x * SF, (y + ISZ) * SF + 4))
        x += ISZ + GAP

    # ---- 文字标注 ----
    d = ImageDraw.Draw(canvas)
    f_small = load_font(15)
    f_big = load_font(22, bold=True)
    d.text((PAD * SF, PAD * SF - 4),
           "星露谷像素风 · 控件总览（原生 16px 绘制，4× 最近邻放大）",
           font=f_big, fill=PAL["pap_lt"])
    for lab, tx, ty in texts:
        d.text((tx, ty), lab, font=f_small, fill=PAL["wood_hi"])

    return canvas, texts


# ============ 组装：整窗预览图 ============
def wood_bg(w, h, plank=24):
    """木板背景：横向板条 + 错位竖缝，纯像素绘制。"""
    img = Image.new("RGBA", (w, h), PAL["wood_dk"] + (255,))
    d = ImageDraw.Draw(img)
    tones = ["wood", "wood_mid", "wood", "wood_dk"]
    rows = list(range(0, h, plank))
    for i, y in enumerate(rows):
        d.rectangle([0, y, w - 1, min(y + plank - 1, h - 1)], fill=PAL[tones[i % 4]])
        if y + 1 < h:
            d.line([(0, y), (w - 1, y)], fill=PAL["wood_lt"])
            d.line([(0, y + 1), (w - 1, y + 1)], fill=PAL["wood_dk"])
        seam = (i * 137) % w
        d.line([(seam, y + 1), (seam, min(y + plank - 1, h - 1))],
               fill=PAL["wood_dk"])
    return img


def _tc(d, cx, cy, s, font, fill):
    b = d.textbbox((0, 0), s, font=font)
    d.text((cx - (b[2] + b[0]) / 2, cy - (b[3] + b[1]) / 2), s, font=font, fill=fill)


def _tl(d, x, y, s, font, fill):
    d.text((x, y), s, font=font, fill=fill)


def _tr(d, rx, cy, s, font, fill):
    b = d.textbbox((0, 0), s, font=font)
    d.text((rx - (b[2] - b[0]), cy - (b[3] + b[1]) / 2), s, font=font, fill=fill)


def build_window(WU=470, HU=504, sf=3):
    """整窗预览：全部控件用像素原语绘制，文字用系统字体叠加。

    WU/HU 是"原生像素"尺寸（等同真实窗口的逻辑像素），内部所有像素图形
    按 sf 倍放大，保证像素颗粒清晰可见。
    """
    S = sf
    # 外层：厚木框 + 深色木底
    frame = pixel_box(WU, HU, r=8, border="wood_dk", face="wood_dk", band=4,
                      border_hi="wood_lt", border_lo="outline")
    canvas = Image.new("RGBA", (WU * S, HU * S), PAL["wood_dk"] + (255,))
    canvas.paste(scale(frame, S), (0, 0), scale(frame, S))
    inner = pixel_box(WU - 12, HU - 12, r=6, border="wood", face="wood_dk", band=2,
                      border_hi="wood_mid", border_lo="outline")
    canvas.paste(scale(inner, S), (6 * S, 6 * S), scale(inner, S))

    texts = []      # (x, y, 文本, 逻辑字号, 颜色, 对齐, 粗体)

    def paste_box(im, x, y):
        up = scale(im, S)
        canvas.paste(up, (int(x * S), int(y * S)), up)

    def T(x, y, s, size, color, align="left", bold=False):
        texts.append((x, y, s, size, color, align, bold))

    # ================= 木质招牌 =================
    banner = add_nails(add_grain(pixel_box(WU - 26, 42, r=5, border="wood_dk",
                                           face="wood_mid", band=3,
                                           border_hi="wood_lt", border_lo="wood_dk"),
                                 seed=5, n=7, avoid_y=(8, 34), only_hi=True),
                       color="gold")
    paste_box(banner, 13, 13)
    T(WU / 2, 30, "护眼助手", 17, PAL["pap_lt"], "center", True)
    T(WU / 2, 45, "定时提醒，爱护眼睛", 9, PAL["wood_hi"], "center")

    # ================= 标签栏 =================
    tabs = ["主功能", "打卡提醒", "设置"]
    tw, tgap = 140, 8
    tx0 = (WU - (tw * 3 + tgap * 2)) / 2
    for i, name in enumerate(tabs):
        act = (i == 0)
        paste_box(pixel_box(tw, 26, r=4,
                            border="wood_dk" if act else "wood",
                            face="wood_dk" if act else "wood_lt", band=2,
                            border_hi="wood" if act else "wood_hi",
                            border_lo="outline" if act else "wood_dk",
                            face_hi="wood" if act else "wood_hi",
                            face_lo="outline" if act else "wood_dk"),
                  tx0 + i * (tw + tgap), 61)
        T(tx0 + i * (tw + tgap) + tw / 2, 74, name, 11,
          PAL["pap_lt"] if act else PAL["ink"], "center", True)

    # ================= 卡片 1：提醒间隔 =================
    CY = 96
    paste_box(add_nails(pixel_box(WU - 26, 94, r=5, border="wood", face="pap",
                                  band=3, border_hi="wood_lt", border_lo="wood_dk",
                                  face_hi="pap_lt", face_lo="pap_dk"),
                        color="wood_dk"), 13, CY)
    T(25, CY + 11, "提醒间隔", 12, PAL["ink"], bold=True)
    paste_box(pixel_box(56, 26, r=3, border="wood_dk", face="pap_lt", band=2,
                        border_hi="outline", border_lo="pap_lt"), 25, CY + 30)
    T(53, CY + 43, "45", 12, PAL["ink"], "center")
    T(88, CY + 43, "分钟", 10, PAL["ink_sub"])
    T(WU - 26, CY + 43, "（1 ~ 180）", 9, PAL["ink_sub"], "right")
    T(25, CY + 66, "快捷设置", 10, PAL["ink_sub"])
    for i, v in enumerate(("20", "25", "45", "60")):
        on = (v == "45")
        qx = 86 + i * 52
        paste_box(pixel_box(46, 24, r=3, border="wood_dk",
                            face="grass" if on else "wood_lt", band=1,
                            border_hi="grass_lt" if on else "wood_hi",
                            border_lo="grass_dk" if on else "wood_dk"),
                  qx, CY + 62)
        T(qx + 23, CY + 74, v, 10,
          PAL["pap_lt"] if on else PAL["ink"], "center", True)

    # ================= 卡片 2：提醒文案 =================
    CY2 = 198
    paste_box(add_nails(pixel_box(WU - 26, 124, r=5, border="wood", face="pap",
                                  band=3, border_hi="wood_lt", border_lo="wood_dk",
                                  face_hi="pap_lt", face_lo="pap_dk"),
                        color="wood_dk"), 13, CY2)
    T(25, CY2 + 11, "提醒文案（每行一条，轮流展示）", 12, PAL["ink"], bold=True)
    paste_box(pixel_box(WU - 50, 78, r=3, border="wood_dk", face="pap_lt", band=2,
                        border_hi="outline", border_lo="pap_lt"), 25, CY2 + 32)
    for i, ln in enumerate(["眼睛累了，看看远处 20 秒吧～",
                            "连续用眼时间不短了，闭眼休息 30 秒。",
                            "护眼小贴士：看屏幕每 20 分钟看向 6 米外。"]):
        T(33, CY2 + 41 + i * 21, ln, 9, PAL["ink"])
    T(25, CY2 + 114, "顺序轮换", 9, PAL["ink_sub"])
    T(WU - 26, CY2 + 114, "共 3 条", 9, PAL["ink_sub"], "right")

    # ================= 卡片 3：今日打卡 =================
    CY3 = 330
    paste_box(add_nails(pixel_box(WU - 26, 76, r=5, border="wood", face="pap",
                                  band=3, border_hi="wood_lt", border_lo="wood_dk",
                                  face_hi="pap_lt", face_lo="pap_dk"),
                        color="wood_dk"), 13, CY3)
    T(25, CY3 + 10, "今日打卡（上下班共 4 次）", 12, PAL["ink"], bold=True)
    tags = [("上班", "09:00", True), ("午休", "12:00", False),
            ("午休结束", "13:30", False), ("下班", "18:00", False)]
    for i, (nm, tm, done) in enumerate(tags):
        gx = 25 + i * 106
        paste_box(pixel_box(100, 32, r=3, border="wood_dk",
                            face="grass" if done else "wood_lt", band=1,
                            border_hi="grass_lt" if done else "wood_hi",
                            border_lo="grass_dk" if done else "wood_dk"),
                  gx, CY3 + 32)
        fg = PAL["pap_lt"] if done else PAL["ink_sub"]
        T(gx + 9, CY3 + 40, nm, 9, fg)
        T(gx + 9, CY3 + 52, tm, 11, PAL["pap_lt"] if done else PAL["ink"], bold=True)
        head = scale(pixel_box(16, 16, r=2, border="wood_dk",
                               face="grass" if done else "pap_lt", band=1,
                               border_hi="grass_lt" if done else "outline",
                               border_lo="grass_dk" if done else "pap_lt"), 1)
        if done:
            dd = ImageDraw.Draw(head)
            dd.line([(3, 8), (6, 12)], fill=PAL["outline"], width=3)
            dd.line([(6, 12), (12, 3)], fill=PAL["outline"], width=3)
            dd.line([(4, 8), (6, 11)], fill=PAL["pap_lt"], width=1)
            dd.line([(6, 11), (11, 4)], fill=PAL["pap_lt"], width=1)
        else:
            dd = ImageDraw.Draw(head)
            dd.line([(4, 4), (11, 11)], fill=PAL["wood_dk"], width=1)
            dd.line([(11, 4), (4, 11)], fill=PAL["wood_dk"], width=1)
        canvas.paste(scale(head, S), (int((gx + 76) * S), int((CY3 + 40) * S)),
                     scale(head, S))

    # ================= 底部操作行 =================
    BY = 422
    paste_box(pixel_box(100, 32, r=4, border="wood_dk", face="wood_lt", band=2,
                        border_hi="wood_hi", border_lo="wood_dk",
                        face_hi="wood_hi", face_lo="wood_dk"), 13, BY)
    T(63, BY + 16, "预览弹窗", 12, PAL["ink"], "center", True)
    paste_box(pixel_box(112, 32, r=4, border="grass_dk", face="grass", band=2,
                        border_hi="grass_lt", border_lo="grass_dk",
                        face_hi="grass_lt", face_lo="grass_dk"), 345, BY)
    T(401, BY + 16, "暂停提醒", 12, PAL["pap_lt"], "center", True)
    T(229, BY + 11, "休息 44 分 12 秒后", 10, PAL["grass_lt"], "center", True)
    T(229, BY + 26, "下班打卡 4 时 05 分后", 9, PAL["wood_hi"], "center")

    # ================= 状态行 =================
    T(WU / 2, 468, "提醒运行中", 10, PAL["grass_lt"], "center", True)
    T(WU / 2, 485, "所有修改即时生效并自动保存", 9, PAL["wood_hi"], "center")

    # ================= 叠加文字 =================
    d = ImageDraw.Draw(canvas)
    cache = {}

    def fnt(size, bold):
        key = (int(round(size * S / 2)), bold)
        if key not in cache:
            cache[key] = load_font(max(10, key[0]), bold)
        return cache[key]

    for (x, y, s, size, color, align, bold) in texts:
        f = fnt(size, bold)
        px, py = x * S, y * S
        if align == "center":
            _tc(d, px, py, s, f, color)
        elif align == "right":
            _tr(d, px, py, s, f, color)
        else:
            _tl(d, px, py - f.size * 0.62, s, f, color)
    return canvas


if __name__ == "__main__":
    os.makedirs(PREVIEW_DIR, exist_ok=True)

    img, texts = build_overview()
    out1 = os.path.join(PREVIEW_DIR, "像素风-PoC-控件总览.png")
    img.save(out1)
    print("已生成：", out1, img.size)

    win = build_window()
    out2 = os.path.join(PREVIEW_DIR, "像素风-PoC-整窗预览.png")
    win.save(out2)
    print("已生成：", out2, win.size)
