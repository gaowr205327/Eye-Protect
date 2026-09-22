# -*- coding: utf-8 -*-
"""像素绘制引擎：用 Pillow 在**低分辨率原生像素**上作画，再整数倍放大。

为什么不用 Canvas 画弧线？
    现有实现用 create_arc 拼圆角，得到的是抗锯齿的平滑弧线；
    像素风要的恰恰相反 —— 硬边、台阶角、没有过渡像素。
    所以这里所有图形都在原生网格（1/SF 尺寸）上逐像素绘制，
    最后用 NEAREST 整数倍放大，边缘绝对锐利。

设计约束（像素风惯例）：
- 阶梯圆角：像素画的"圆角"是台阶，不是弧线（见 _insets）
- 硬偏移投影：实心、无模糊、无透明度渐变
- 限定调色板：全部颜色取自 theme.get()["window"]，不额外造色
- 抖动代替渐变：需要渐变处用 Bayer 有序抖动，绝不线性插值

所有组件都是**程序化生成**，不引用任何外部图片素材。
"""
from PIL import Image, ImageDraw

import theme

# ==================== 基础 ====================

SF = 2                      # 像素放大倍数：1 原生像素 = SF 个屏幕像素
SHADOW_N = 2                # 卡片硬投影偏移（原生像素）


def _rgb(key):
    """从主题取色 → (r,g,b)。"""
    v = theme.get()["window"][key].lstrip("#")
    return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))


PAL = {k: _rgb(k) for k in theme.get()["window"]}

# Bayer 4×4 有序抖动矩阵（阈值 =(m+0.5)/16）
BAYER4 = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))


def _insets(h, r):
    """阶梯圆角每行的内缩量：像素画的圆角是台阶序列，不是弧线。"""
    r = max(0, min(int(r), h // 2))
    if r == 0:
        return [0] * h
    return list(range(r, 0, -1)) + [0] * (h - 2 * r) + list(range(1, r + 1))


def shape(d, x, y, w, h, r, color):
    """阶梯圆角实心块（也可画进 L 图当遮罩，此时 color=255）。"""
    if w <= 0 or h <= 0:
        return
    for i, ins in enumerate(_insets(h, r)):
        x0, x1 = x + ins, x + w - 1 - ins
        if x1 >= x0:
            d.line([(x0, y + i), (x1, y + i)], fill=color)


def put(img, x, y, color, skip=()):
    """单像素写入；透明区与 skip 中的颜色都跳过。"""
    if not (0 <= x < img.width and 0 <= y < img.height):
        return
    px = img.getpixel((x, y))
    if px[-1] == 0 or (skip and tuple(px[:3]) in skip):
        return
    img.putpixel((x, y), tuple(color) + (255,) if len(color) == 3 else tuple(color))


def fit_pixel(img, W, H):
    """按 SF 整数倍放大到 (W,H)：不足处复制边缘像素补齐，绝不插值。

    保持整数倍是为了让每个像素块都恰好是 SF×SF，图像不会有宽窄不一的列。
    """
    nw, nh = max(1, img.width * SF), max(1, img.height * SF)
    out = img.resize((nw, nh), Image.NEAREST)
    cw, ch = max(W, nw), max(H, nh)
    canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    canvas.paste(out, (0, 0))
    if nw < cw:
        col = out.crop((nw - 1, 0, nw, nh))
        canvas.paste(col.resize((cw - nw, nh), Image.NEAREST), (nw, 0))
    if nh < ch:
        row = canvas.crop((0, nh - 1, cw, nh))
        canvas.paste(row.resize((cw, ch - nh), Image.NEAREST), (0, nh))
    return canvas if (cw, ch) == (W, H) else canvas.crop((0, 0, W, H))


def _nat(W, H):
    """屏幕尺寸 → 原生网格尺寸。"""
    return max(3, W // SF), max(3, H // SF)


# ==================== 抖动渐变 ====================

def dither_pattern(w, h, stops):
    """Bayer 有序抖动渐变。stops=[(t, color_key), ...]，t 升序。

    像素风里渐变必须靠抖动实现（点阵疏密），不能用线性插值 ——
    那会产生过渡像素，破坏像素感。
    """
    img = Image.new("RGB", (w, h), PAL[stops[0][1]])
    px = img.load()
    segs = [(stops[i][0], stops[i + 1][0], stops[i][1], stops[i + 1][1])
            for i in range(len(stops) - 1)]
    last = len(segs) - 1
    for y in range(h):
        t = y / max(1, h - 1)
        th = 0.0
        for x in range(w):
            th = (BAYER4[y & 3][x & 3] + 0.5) / 16.0
            for idx, (t0, t1, c0, c1) in enumerate(segs):
                if t <= t1 or idx == last:
                    local = min(1.0, max(0.0, (t - t0) / max(1e-6, t1 - t0)))
                    px[x, y] = PAL[c0] if local < th else PAL[c1]
                    break
    return img


def dither_shape(w, h, r, stops, x=0, y=0):
    """把抖动渐变裁进阶梯圆角形状。"""
    mask = Image.new("L", (w, h), 0)
    shape(ImageDraw.Draw(mask), x, y, w, h, r, 255)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(dither_pattern(w, h, stops), (x, y), mask)
    return out


# ==================== 色环方框（全界面基元） ====================

def ring_box(w, h, rings, r=2):
    """由外向内逐环绘制色带；最后一环填充剩余内胆。

    rings = [(颜色键, 厚度), ...]。整套界面的卡片/按钮/输入框/标签
    全由它派生 —— 只改 rings 与 r 就能得到完全不同的质感，
    边框厚度也因此是像素级的精确控制（不靠描边宽度近似）。

    像素画的立体感只来自两处：方向光（上左亮/下右暗）+ 硬边投影，
    绝不使用模糊阴影或渐变过渡。
    """
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    inset = 0
    for i, (color, th) in enumerate(rings):
        if i == len(rings) - 1:
            shape(d, inset, inset, w - 2 * inset, h - 2 * inset,
                  max(0, r - inset), PAL[color])
            break
        for k in range(th):
            o = inset + k
            shape(d, o, o, w - 2 * o, h - 2 * o, max(0, r - o), PAL[color])
        inset += th
    return img


def _inner_inset(rings):
    return sum(th for _, th in rings[:-1])


def _box(W, H, rings, r=2, hi=None, lo=None, fhi=None, flo=None, key=None):
    """按屏幕尺寸生成色环方框 PNG（带缓存），并叠加方向光。"""
    ck = key or ("box", W, H, tuple(rings), r, hi, lo, fhi, flo)
    if ck in _CACHE:
        return _CACHE[ck]
    nw, nh = _nat(W, H)
    img = ring_box(nw, nh, rings, r)
    ins = _inner_inset(rings)
    if hi:                                  # 边框上的方向光
        for x in range(2, nw - 2):
            put(img, x, 1, PAL[hi])
            put(img, x, nh - 2, PAL[lo or hi])
        for y in range(2, nh - 2):
            put(img, 1, y, PAL[hi])
            put(img, w_ := nw - 2, y, PAL[lo or hi])
    if fhi:                                 # 内胆首行提亮
        for x in range(ins + 1, nw - ins - 1):
            put(img, x, ins, PAL[fhi])
    if flo:                                 # 内胆末行压暗
        for x in range(ins + 1, nw - ins - 1):
            put(img, x, nh - 1 - ins, PAL[flo])
    out = fit_pixel(img, W, H)
    _CACHE[ck] = out
    return out


_CACHE = {}


# ==================== 木纹 / 铆钉 / 装饰件 ====================

def _grain(img, seed=7, n=6, avoid_y=None, inset=4):
    """木纹短横线：确定性伪随机（不引 random），保证每次构建完全一致。"""
    w, h = img.size
    if h <= 2 * inset + 3:
        return img
    span = max(1, w - 2 * inset)
    for i in range(n):
        sx = (seed * 37 + i * 91) % span
        ln = 3 + (seed * 13 + i * 29) % 6
        yy = inset + (i * (h - 2 * inset)) // max(1, n)
        if avoid_y and avoid_y[0] <= yy <= avoid_y[1]:
            continue
        col = PAL["wood_hi"] if i % 2 else PAL["wood_dark"]
        for k in range(ln):
            put(img, inset + sx + k, yy, col, skip=(PAL["ink"],))
    return img


def _nails(img, off=4, color="gold"):
    """四角铆钉：像素画的标志性细节，也是"手工木牌"的暗示。"""
    w, h = img.size
    for (x, y) in ((off, off - 1), (w - 1 - off, off - 1),
                   (off, h - off), (w - 1 - off, h - off)):
        put(img, x, y, PAL[color], skip=(PAL["ink"],))
    return img


def _spr_grass(h=9):
    """草簇。"""
    w = h + 1
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = w // 2
    for dx, top in ((-3, h - 4), (-1, h - 7), (1, h - 8), (3, h - 5)):
        x = cx + dx
        bend = 1 if dx > 0 else (-1 if dx < 0 else 0)
        d.line([(x, h - 1), (x + bend, top)],
               fill=PAL["grass_lt"] if abs(dx) <= 1 else PAL["grass"])
    d.line([(cx - 3, h - 1), (cx + 3, h - 1)], fill=PAL["grass_dk"])
    return img


def _spr_flower(h=6, petal="red_lt"):
    """小花：四瓣 + 金色花心 + 四角补圆。

    刻意用 2×2 方块拼花瓣（而不是细线）—— 小尺寸下只有方块
    才能在整数倍放大后仍然"读得出是一朵花"。
    """
    img = Image.new("RGBA", (h, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for box in ((2, 0, 3, 1), (2, 4, 3, 5), (0, 2, 1, 3), (4, 2, 5, 3)):
        d.rectangle(box, fill=PAL[petal])
    for (x, y) in ((1, 1), (4, 1), (1, 4), (4, 4)):
        d.point((x, y), fill=PAL[petal])
    d.rectangle((2, 2, 3, 3), fill=PAL["gold"])
    return img


def _spr_leaf(h=8):
    """叶片：斜置叶身 + 中脉。"""
    img = Image.new("RGBA", (h, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i in range(h):
        d.line([(i, h - 1 - i), (min(h - 1, i + 1), h - 1 - i)], fill=PAL["grass"])
        d.line([(min(h - 1, i + 2), h - 1 - i),
                (min(h - 1, i + 3), h - 1 - i)], fill=PAL["grass_dk"])
    d.line([(0, h - 1), (h - 1, 0)], fill=PAL["grass_lt"])
    return img


def _spr_sprout(h=9):
    """嫩芽：一小段茎 + 两片新叶（"生长"意象）。"""
    img = Image.new("RGBA", (h, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = h // 2
    d.line([(c, h - 1), (c, h - 4)], fill=PAL["grass_dk"])
    d.rectangle((c - 3, h - 6, c - 1, h - 5), fill=PAL["grass"])
    d.rectangle((c + 1, h - 6, c + 3, h - 5), fill=PAL["grass"])
    d.rectangle((c - 1, h - 8, c + 1, h - 6), fill=PAL["grass_lt"])
    return img


def _spr_mushroom(h=9):
    """小蘑菇：红帽白点。"""
    img = Image.new("RGBA", (h, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = h // 2
    d.rectangle((c - 1, c, c, h - 2), fill=PAL["pap_lt"])
    d.rectangle((c - 3, c - 4, c + 3, c - 2), fill=PAL["red_dk"])
    d.rectangle((c - 3, c - 4, c + 3, c - 3), fill=PAL["red"])
    put(img, c - 2, c - 3, PAL["pap_lt"])
    put(img, c + 1, c - 3, PAL["pap_lt"])
    return img


def _spr_star(size=7):
    """四角星光（状态提示闪烁用）。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = size // 2
    d.line([(c, 0), (c, size - 1)], fill=PAL["gold_lt"])
    d.line([(0, c), (size - 1, c)], fill=PAL["gold_lt"])
    d.rectangle((c - 1, c - 1, c + 1, c + 1), fill=PAL["gold"])
    return img


def _spr_coin(size=7):
    """金币。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((0, 0, size - 1, size - 1), fill=PAL["gold_dk"])
    d.ellipse((1, 1, size - 2, size - 2), fill=PAL["gold"])
    if size >= 6:
        d.ellipse((2, 2, size - 3, size - 3), fill=PAL["gold_lt"])
    return img


# ==================== 图标集 ====================

def _ico_eye(sz=16):
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon([(0, 8), (4, 3), (11, 3), (15, 8), (11, 12), (4, 12)], fill=PAL["ink"])
    d.polygon([(1, 8), (5, 4), (10, 4), (14, 8), (10, 11), (5, 11)], fill=PAL["pap_lt"])
    d.ellipse((5, 5, 10, 10), fill=PAL["ink"])
    d.ellipse((6, 6, 9, 9), fill=PAL["grass"])
    put(img, 7, 6, PAL["white"])
    put(img, 6, 7, PAL["white"])
    return img


def _ico_clock(sz=16):
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((0, 0, sz - 1, sz - 1), fill=PAL["ink"])
    d.ellipse((1, 1, sz - 2, sz - 2), fill=PAL["wood"])
    d.ellipse((3, 3, sz - 4, sz - 4), fill=PAL["pap_lt"])
    for p in ((7, 2), (7, 13), (2, 7), (13, 7)):
        put(img, p[0], p[1], PAL["wood_dark"])
    for y in range(4, 9):
        put(img, 7, y, PAL["ink"])
    for x in range(8, 12):
        put(img, x, 8, PAL["ink"])
    return img


def _ico_gear(sz=16):
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, sz - 3, sz - 3), fill=PAL["ink"])
    for (cx, cy) in ((6, 0), (9, 0), (6, 13), (9, 13),
                     (0, 6), (0, 9), (13, 6), (13, 9)):
        d.rectangle((cx, cy, cx + 2, cy + 2), fill=PAL["ink"])
    d.ellipse((3, 3, sz - 4, sz - 4), fill=PAL["wood"])
    d.ellipse((5, 5, sz - 6, sz - 6), fill=PAL["wood_hi"])
    d.ellipse((6, 6, sz - 7, sz - 7), fill=PAL["ink"])
    return img


def _ico_scroll(sz=16):
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((1, 2, sz - 2, sz - 3), fill=PAL["ink"])
    d.rectangle((2, 3, sz - 3, sz - 4), fill=PAL["pap_lt"])
    d.rectangle((4, 6, sz - 5, 7), fill=PAL["sub"])
    d.rectangle((4, 9, sz - 5, 10), fill=PAL["sub"])
    d.rectangle((1, 1, sz - 2, 2), fill=PAL["wood"])
    d.rectangle((1, sz - 4, sz - 2, sz - 3), fill=PAL["wood"])
    return img


def _ico_checklist(sz=16):
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((1, 2, sz - 2, sz - 3), fill=PAL["ink"])
    d.rectangle((2, 3, sz - 3, sz - 4), fill=PAL["pap_lt"])
    d.line([(4, 6), (6, 9)], fill=PAL["grass_dk"], width=2)
    d.line([(6, 9), (11, 3)], fill=PAL["grass_dk"], width=2)
    d.rectangle((4, 11, sz - 4, 12), fill=PAL["sub"])
    return img


def _ico_check(sz=16):
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.line([(2, 8), (7, 13)], fill=PAL["ink"], width=4)
    d.line([(7, 13), (14, 3)], fill=PAL["ink"], width=4)
    d.line([(3, 8), (7, 12)], fill=PAL["grass"], width=2)
    d.line([(7, 12), (13, 4)], fill=PAL["grass"], width=2)
    return img


def _ico_cross(sz=16):
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.line([(2, 3), (13, 12)], fill=PAL["ink"], width=4)
    d.line([(13, 3), (2, 12)], fill=PAL["ink"], width=4)
    d.line([(3, 4), (12, 11)], fill=PAL["red"], width=2)
    d.line([(12, 4), (3, 11)], fill=PAL["red"], width=2)
    return img


def _ico_heart(sz=16):
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((0, 1, 7, 8), fill=PAL["red_dk"])
    d.ellipse((8, 1, 15, 8), fill=PAL["red_dk"])
    d.polygon([(0, 6), (15, 6), (7, 15)], fill=PAL["red_dk"])
    d.ellipse((1, 2, 7, 8), fill=PAL["red"])
    d.ellipse((8, 2, 14, 8), fill=PAL["red"])
    d.polygon([(1, 6), (14, 6), (7, 14)], fill=PAL["red"])
    put(img, 3, 3, PAL["red_lt"])
    put(img, 4, 3, PAL["red_lt"])
    return img


def _ico_info(sz=16):
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((0, 0, sz - 1, sz - 1), fill=PAL["ink"])
    d.ellipse((1, 1, sz - 2, sz - 2), fill=PAL["sky"])
    d.rectangle((7, 4, 8, 5), fill=PAL["ink"])
    d.rectangle((7, 7, 8, 11), fill=PAL["ink"])
    return img


_ICONS = {
    "eye": _ico_eye, "clock": _ico_clock, "gear": _ico_gear,
    "scroll": _ico_scroll, "checklist": _ico_checklist,
    "check": _ico_check, "cross": _ico_cross, "heart": _ico_heart,
    "info": _ico_info,
    "grass": _spr_grass, "flower": _spr_flower, "leaf": _spr_leaf,
    "sprout": _spr_sprout, "mushroom": _spr_mushroom, "star": _spr_star,
    "coin": _spr_coin,
}


def icon(name, px=None):
    """取图标 PNG：原生手绘 → 最近邻放大到 px 见方。

    非整数倍缩放也用 NEAREST，绝不产生插值模糊 —— 只会有少量
    "宽一格"的像素列，观感仍然是像素。
    """
    key = ("icon", name, px)
    if key in _CACHE:
        return _CACHE[key]
    native = _ICONS[name]()
    if px is None:
        out = native.resize((native.width * SF, native.height * SF), Image.NEAREST)
    else:
        out = native.resize((px, px), Image.NEAREST)
    _CACHE[key] = out
    return out


# ==================== 组件：卡片 ====================

_CARD_RINGS = [("ink", 1), ("border", 1), ("wood", 2), ("card_bg", 1)]


def card(W, H):
    """木质卡片：硬偏移投影 + 三层木框 + 铆钉 + 角花装饰。"""
    key = ("card", W, H)
    if key in _CACHE:
        return _CACHE[key]
    off = SHADOW_N
    nw = max(8, W // SF - off)
    nh = max(8, H // SF - off)
    img = Image.new("RGBA", (nw + off, nh + off), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # ① 硬投影：实心、偏移、无模糊
    shape(d, off, off, nw, nh, 3, PAL["shadow"])
    # ② 三层木框
    shape(d, 0, 0, nw, nh, 3, PAL["ink"])
    shape(d, 1, 1, nw - 2, nh - 2, 3, PAL["border"])
    shape(d, 2, 2, nw - 4, nh - 4, 2, PAL["wood"])
    shape(d, 3, 3, nw - 6, nh - 6, 2, PAL["wood"])
    shape(d, 4, 4, nw - 8, nh - 8, 1, PAL["card_bg"])
    for x in range(2, nw - 2):
        put(img, x, 1, PAL["wood_hi"], skip=(PAL["ink"],))
        put(img, x, nh - 2, PAL["wood_dark"], skip=(PAL["ink"],))
    for y in range(2, nh - 2):
        put(img, 1, y, PAL["wood_hi"], skip=(PAL["ink"],))
        put(img, nw - 2, y, PAL["wood_dark"], skip=(PAL["ink"],))
    for x in range(5, nw - 5):                      # 内胆上亮下暗
        put(img, x, 4, PAL["pap_lt"], skip=(PAL["ink"],))
        put(img, x, nh - 5, PAL["bevel"], skip=(PAL["ink"],))
    for (x, y) in ((4, 2), (nw - 5, 2), (4, nh - 3), (nw - 5, nh - 3)):
        put(img, x, y, PAL["gold"], skip=(PAL["ink"],))
    fl, gr = _spr_flower(6, "red_lt"), _spr_grass(7)     # 角花不占内容区
    img.paste(fl, (6, nh - 11), fl)
    img.paste(gr, (nw - 14, nh - 12), gr)
    out = fit_pixel(img, W, H)
    _CACHE[key] = out
    return out


def card_inner_pad():
    """卡片内胆相对卡片边缘的内缩量（屏幕像素），供内容 Frame 定位。"""
    return (4 + 1) * SF + 2


# ==================== 组件：招牌 ====================

def banner(W, H):
    """木质招牌：木纹（避让文字区）+ 金铆钉 + 两端叶片装饰。"""
    key = ("banner", W, H)
    if key in _CACHE:
        return _CACHE[key]
    nw, nh = _nat(W, H)
    img = Image.new("RGBA", (nw, nh), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    shape(d, 0, 0, nw, nh, 3, PAL["ink"])
    shape(d, 1, 1, nw - 2, nh - 2, 3, PAL["border"])
    shape(d, 2, 2, nw - 4, nh - 4, 2, PAL["wood"])
    for x in range(2, nw - 2):
        put(img, x, 1, PAL["wood_hi"], skip=(PAL["ink"],))
        put(img, x, nh - 2, PAL["wood_dark"], skip=(PAL["ink"],))
    for y in range(2, nh - 2):
        put(img, 1, y, PAL["wood_hi"], skip=(PAL["ink"],))
        put(img, nw - 2, y, PAL["wood_dark"], skip=(PAL["ink"],))
    # 木纹避开中间 50% 高度：那里要放标题（否则木纹会像删除线穿过文字）
    _grain(img, seed=5, n=9, inset=4,
           avoid_y=(nh // 2 - nh // 4, nh // 2 + nh // 4))
    _nails(img, off=4, color="gold")
    lf = _spr_leaf(8)
    img.paste(lf, (6, max(2, nh - 11)), lf)
    lf2 = lf.transpose(Image.FLIP_LEFT_RIGHT)
    img.paste(lf2, (nw - 14, max(2, nh - 11)), lf2)
    out = fit_pixel(img, W, H)
    _CACHE[key] = out
    return out


# ==================== 组件：标签 / 按钮 / 输入框 / 勾选 ====================

_TAB_ACTIVE = dict(rings=[("ink", 1), ("wood", 1), ("wood_dark", 2)],
                   r=2, hi="wood_hi", lo="ink")
_TAB_IDLE = dict(rings=[("ink", 1), ("wood_dark", 1), ("soft_bg", 1)],
                 r=2, hi="wood_hi", lo="wood_dark", fhi="pap_lt", flo="bevel")


def tab(W, H, active):
    """木质标签页：选中 = 深木面（凹进），未选 = 浅木面（凸起）。"""
    cfg = _TAB_ACTIVE if active else _TAB_IDLE
    return _box(W, H, key=("tab", W, H, active), **cfg)


_BTN = {
    "primary": dict(rings=[("ink", 1), ("grass_dk", 1), ("accent", 1)],
                    r=2, hi="grass_lt", lo="grass_dk",
                    fhi="grass_lt", flo="grass_dk"),
    "primary_hover": dict(rings=[("ink", 1), ("grass_dk", 1), ("grass_lt", 1)],
                          r=2, hi="pap_lt", lo="grass_dk",
                          fhi="pap_lt", flo="grass_dk"),
    "primary_press": dict(rings=[("ink", 1), ("grass_dk", 2)],
                          r=2, hi="accent", lo="ink"),
    "soft": dict(rings=[("ink", 1), ("wood_dark", 1), ("soft_bg", 1)],
                 r=2, hi="wood_hi", lo="wood_dark", fhi="pap_lt", flo="bevel"),
    "soft_hover": dict(rings=[("ink", 1), ("wood_dark", 1), ("soft_hover", 1)],
                       r=2, hi="pap_lt", lo="wood_dark", fhi="pap_lt", flo="bevel"),
    "soft_press": dict(rings=[("ink", 1), ("wood_dark", 2)],
                       r=2, hi="bevel", lo="ink"),
    "warn": dict(rings=[("ink", 1), ("wood_dark", 1), ("status_pause", 1)],
                 r=2, hi="gold_lt", lo="gold_dk", fhi="gold_lt", flo="gold_dk"),
    "warn_hover": dict(rings=[("ink", 1), ("wood_dark", 1), ("gold", 1)],
                       r=2, hi="gold_lt", lo="gold_dk", fhi="gold_lt", flo="gold_dk"),
    "warn_press": dict(rings=[("ink", 1), ("wood_dark", 2)],
                       r=2, hi="gold", lo="ink"),
}


def button(W, H, variant):
    return _box(W, H, key=("btn", W, H, variant), **_BTN[variant])


def field(W, H):
    """输入框外壳：内胆上暗下亮 → 视觉上"凹进去"。

    像素风里凹/凸只靠方向光反转区分，不用阴影。
    """
    return _box(W, H, rings=[("ink", 1), ("wood_dark", 1), ("input_bg", 1)],
                r=2, hi=None, fhi="bevel", flo="pap_lt",
                key=("field", W, H))


def checkbox(px, checked):
    """像素勾选框（外观自绘，变量绑定与原生 Checkbutton 完全一致）。"""
    key = ("checkbox", px, checked)
    if key in _CACHE:
        return _CACHE[key]
    n = max(8, px // SF)
    rings = ([("ink", 1), ("grass_dk", 1), ("accent", 1)] if checked
             else [("ink", 1), ("wood_dark", 1), ("input_bg", 1)])
    img = ring_box(n, n, rings, 1)
    d = ImageDraw.Draw(img)
    if checked:
        d.line([(n // 4, n // 2), (n // 2 - 1, n * 3 // 4)], fill=PAL["ink"], width=2)
        d.line([(n // 2 - 1, n * 3 // 4), (n * 5 // 6, n // 4)],
               fill=PAL["ink"], width=2)
        d.line([(n // 4 + 1, n // 2), (n // 2 - 1, n * 3 // 4 - 1)],
               fill=PAL["pap_lt"])
    else:
        for x in range(2, n - 2):
            put(img, x, 2, PAL["bevel"])
    out = fit_pixel(img, px, px)
    _CACHE[key] = out
    return out


def radio(px, checked):
    """像素单选框：用同心方块模拟圆，保持"方块像素"的语汇。"""
    key = ("radio", px, checked)
    if key in _CACHE:
        return _CACHE[key]
    n = max(9, px // SF)
    # 半径取 n//2-1：留出平底，否则台阶从 n/2 直接降到 0 会退化成菱形
    r = max(1, n // 2 - 1)
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    shape(d, 0, 0, n, n, r, PAL["ink"])
    shape(d, 1, 1, n - 2, n - 2, max(1, r - 1), PAL["wood_dark"])
    shape(d, 2, 2, n - 4, n - 4, max(1, r - 2), PAL["pap_lt"])
    if checked:
        shape(d, n // 4, n // 4, n - n // 2, n - n // 2, max(1, r - 3), PAL["accent"])
        put(img, n // 2 - 1, n // 2 - 2, PAL["grass_lt"])
    out = fit_pixel(img, px, px)
    _CACHE[key] = out
    return out


# ==================== 组件：装饰带 ====================

def divider(W, H):
    """卡片区之间的装饰分隔条：木线 + 中央嫩芽 + 两侧草簇/小花。"""
    key = ("divider", W, H)
    if key in _CACHE:
        return _CACHE[key]
    nw, nh = _nat(W, H)
    img = Image.new("RGBA", (nw, nh), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    mid = nh // 2
    for x in range(8, nw - 8):
        put(img, x, mid, PAL["wood_dark"])
        put(img, x, mid + 1, PAL["bevel"])
    sp = _spr_sprout(9)
    img.paste(sp, (nw // 2 - 5, max(0, mid - 7)), sp)
    for i, x in enumerate(range(18, nw - 24, 48)):
        s = _spr_grass(7) if i % 2 else _spr_flower(6, "red_lt")
        img.paste(s, (x, max(0, mid - 6)), s)
    for i, x in enumerate(range(nw - 44, 24, -48)):
        s = _spr_flower(6, "sky") if i % 2 else _spr_flower(6, "gold_lt")
        img.paste(s, (x, max(0, mid - 6)), s)
    out = fit_pixel(img, W, H)
    _CACHE[key] = out
    return out


def footer(W, H):
    """底部装饰带：Bayer 抖动暖色渐变 + 泥土 + 草丛 + 小花 + 金币点缀。

    （Tk 的 Frame 是不透明矩形，无法给整个窗口铺带图案的底；
      所以装饰集中放在这条专用色带里，效果反而更集中。）
    """
    key = ("footer", W, H)
    if key in _CACHE:
        return _CACHE[key]
    nw, nh = _nat(W, H)
    img = dither_shape(nw, nh, 0, [(0.0, "bg_lt"), (0.45, "bg"), (1.0, "bg_dk")])
    d = ImageDraw.Draw(img)
    shape(d, 0, nh - 5, nw, 5, 0, PAL["soil"])
    for x in range(0, nw):
        put(img, x, nh - 5, PAL["soil_dk"])
    for i in range(9, nw, 24):
        g = _spr_grass(9)
        img.paste(g, (i, nh - 11), g)
    for i in range(21, nw, 43):
        f = _spr_flower(6, "red_lt" if (i // 43) % 2 else "sky")
        img.paste(f, (i, nh - 16), f)
    for i in range(35, nw, 101):
        c = _spr_coin(6)
        img.paste(c, (i, nh - 14), c)
    out = fit_pixel(img, W, H)
    _CACHE[key] = out
    return out


# ==================== 组件：弹窗外框 ====================

def popup_frame(W, H, strip=9):
    """弹窗外框：阶梯圆角木牌 + 顶部草绿色带 + 抖动羊皮纸内胆 + 角落装饰。

    角外保持完全透明（配合 -transparentcolor 让圆角真正镂空）。
    """
    key = ("popup", W, H, strip)
    if key in _CACHE:
        return _CACHE[key]
    nw = max(20, W // SF)
    nh = max(20, H // SF)
    ns = max(2, strip // SF)
    # 抖动羊皮纸内胆（只在顶部做轻度抖动：中下部要放正文，保持浅净）
    img = dither_shape(nw, nh, 4, [(0.0, "pap_lt"), (0.45, "pap"), (1.0, "pap")])
    d = ImageDraw.Draw(img)
    # 木框环
    ring = Image.new("RGBA", (nw, nh), (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    shape(rd, 0, 0, nw, nh, 4, PAL["ink"])
    shape(rd, 1, 1, nw - 2, nh - 2, 4, PAL["wood_dark"])
    shape(rd, 2, 2, nw - 4, nh - 4, 3, PAL["wood"])
    hole = Image.new("L", (nw, nh), 0)
    shape(ImageDraw.Draw(hole), 3, 3, nw - 6, nh - 6, 3, 255)
    # 只在"洞"之外保留木框：mask=255 处取 0（透明），其余取木框自身 alpha
    ring.putalpha(Image.composite(Image.new("L", (nw, nh), 0),
                                  ring.getchannel("A"), hole))
    img.alpha_composite(ring)
    # 顶部草地绿色带
    shape(d, 2, 2, nw - 4, ns, 3, PAL["grass_dk"])
    shape(d, 2, 3, nw - 4, ns - 1, 2, PAL["accent"])
    for x in range(5, nw - 5):
        put(img, x, 2, PAL["grass_lt"], skip=(PAL["ink"],))
    for x in range(2, nw - 2):
        put(img, x, nh - 2, PAL["wood_dark"], skip=(PAL["ink"],))
    for y in range(2, nh - 2):
        put(img, 1, y, PAL["wood_hi"], skip=(PAL["ink"],))
        put(img, nw - 2, y, PAL["wood_dark"], skip=(PAL["ink"],))
    for (x, y) in ((4, ns + 3), (nw - 5, ns + 3), (4, nh - 5), (nw - 5, nh - 5)):
        put(img, x, y, PAL["gold"], skip=(PAL["ink"],))
    gr, fl, lf = _spr_grass(8), _spr_flower(6, "red_lt"), _spr_leaf(6)
    img.paste(gr, (6, nh - 13), gr)
    img.paste(fl, (nw - 13, nh - 12), fl)
    img.paste(lf, (7, ns + 4), lf)
    img.paste(lf.transpose(Image.FLIP_LEFT_RIGHT), (nw - 13, ns + 4), lf)
    out = fit_pixel(img, W, H)
    _CACHE[key] = out
    return out


# ==================== 应用 / 托盘图标 ====================

def app_icon(size=64):
    """像素眼睛图标：草地绿圆底 + 木质描边 + 眼睛。托盘/窗口/exe 共用。"""
    n = 16
    r = n // 2 - 1          # 同上：留平底，避免圆底变成菱形
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    shape(d, 0, 0, n, n, r, PAL["ink"])
    shape(d, 1, 1, n - 2, n - 2, max(1, r - 1), PAL["grass_dk"])
    shape(d, 2, 2, n - 4, n - 4, max(1, r - 2), PAL["accent"])
    eye = _ico_eye(10)
    img.paste(eye, (3, 3), eye)
    return img.resize((size, size), Image.NEAREST)
