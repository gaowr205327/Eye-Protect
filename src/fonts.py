# -*- coding: utf-8 -*-
"""像素字体：加载 + 字号表（全项目唯一字体出口）。

设计要点
--------
1. **字号一律用负数（Tk 语义 = 像素）**
   像素字体必须按设计栅格（12px）整数倍渲染才锐利。磅值会随 DPI 缩放成
   12.5px / 13.3px 这类非整数，把像素格子糊掉，所以全项目统一用像素单位。

2. **只注册到本进程**
   用 AddFontResourceEx(FR_PRIVATE) 加载，不写注册表、不装进系统字体目录，
   程序删掉即无残留；也不会影响用户其他软件。

3. **静默回落**
   字体文件缺失、系统 API 不可用、家族名对不上时，自动回落到系统字体，
   界面功能与布局完全不受影响（只是丢掉像素味）。

对外接口：FAMILY / spec() / apply_defaults() / is_pixel()
"""
import os
import sys

# 像素字体的设计栅格（Fusion Pixel 12px）：所有字号取它的整数倍
PX = 12
SIZE_SMALL = 12     # 次要文字
SIZE_BODY = 12      # 正文（像素字体下 12 已是舒适下限，再小会缺笔画）
SIZE_TITLE = 24     # 标题（12 的 2 倍，正好 2×2 像素块，保持锐利）

_FONT_FILE = "fusion-pixel-12px-zh_hans.ttf"
_FALLBACK_FAMILY = "Microsoft YaHei UI"
_GUESS_FAMILY = "Fusion Pixel 12px Prop zh_hans"

FAMILY = _FALLBACK_FAMILY      # 由 load() 在导入时改写
_loaded_path = None
_registered = False


def _search_dirs():
    """按优先级给出可能的字体目录（打包形态优先，其次开发形态）。"""
    dirs = []
    # 1) PyInstaller 单文件：解包到临时目录
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        dirs.append(os.path.join(meipass, "assets", "fonts"))
    # 2) 打包后 exe 同级目录（单文件/目录版通用）
    if getattr(sys, "frozen", False):
        dirs.append(os.path.join(os.path.dirname(sys.executable),
                                 "assets", "fonts"))
    # 3) 源码运行：本文件在 src/ 下，资源在上一层 assets/
    src_dir = os.path.dirname(os.path.abspath(__file__))
    dirs.append(os.path.join(os.path.dirname(src_dir), "assets", "fonts"))
    return dirs


def _family_of(path):
    """用 Pillow 读字体真实家族名（PIL 无需 Tk 即可工作，最稳）。"""
    try:
        from PIL import ImageFont
        return ImageFont.truetype(path, PX).getname()[0] or _GUESS_FAMILY
    except Exception:
        return _GUESS_FAMILY


def _usable(path):
    """判断字体是否真能用 —— 必须**同时**能渲染小号与大号。

    这一步专治「纯位图字体」：Fusion Pixel 的 `*.ms.bitmap.ttf` 只内嵌了
    12px 一档点阵、没有字形轮廓，PIL 在 12px 下看着正常，但 24px 直接
    画不出东西；更糟的是 Tk 连度量都会返回乱码，导致整窗文字全部消失。
    这里主动挡住它，宁可回落系统字体也不要出现空白界面。
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
        for size in (SIZE_SMALL, SIZE_TITLE):
            f = ImageFont.truetype(path, size)
            im = Image.new("L", (size * 8, size * 2), 255)
            ImageDraw.Draw(im).text((1, 1), "护眼助手Aa", font=f, fill=0)
            box = im.point(lambda v: 255 - v).getbbox()
            if not box:
                return False
        return True
    except Exception:
        return False


def load():
    """定位并私有注册像素字体；返回是否成功。幂等，可重复调用。"""
    global FAMILY, _loaded_path, _registered
    if _registered:
        return True

    for d in _search_dirs():
        path = os.path.join(d, _FONT_FILE)
        if not os.path.isfile(path):
            continue
        if not _usable(path):
            continue        # 位图变体等不可用字体：直接跳过，走回落
        # FR_PRIVATE = 0x10：仅本进程可见，不污染系统
        try:
            import ctypes
            n = ctypes.windll.gdi32.AddFontResourceExW(
                os.path.abspath(path), 0x10, 0)
        except Exception:
            n = 0
        if n:
            FAMILY = _family_of(path)
            _loaded_path = path
            _registered = True
            return True
    return False


def is_pixel():
    """当前是否用上了像素字体（否则是回落状态）。"""
    return _registered


def spec(size=SIZE_BODY, bold=False):
    """构造 Tk 字体元组：(家族, 负像素尺寸[, 'bold'])。

    像素字体只有 Regular 一个字重，GDI 合成粗体是「横向涂抹」，
    会把像素格子糊掉，所以用上像素字体时**忽略 bold**，
    强调改用字号 + 颜色 + 描边来表达。
    """
    if _registered:
        return (FAMILY, -size)
    return (FAMILY, size, "bold") if bold else (FAMILY, size)


def apply_defaults(root):
    """把 Tk 内置命名字体也换成像素字体。

    这样没有显式指定 font= 的原生控件（Spinbox 下拉、Entry 光标、
    Text 选区、Checkbutton 文字、消息框等）也会跟着变像素风。
    """
    if not _registered:
        return
    try:
        import tkinter.font as tkfont
        names = ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont",
                 "TkCaptionFont", "TkSmallCaptionFont", "TkIconFont",
                 "TkTooltipFont")
        for name in names:
            try:
                tkfont.nametofont(name).configure(family=FAMILY,
                                                  size=-SIZE_BODY)
            except Exception:
                pass
        # 兜底：未指定字体的控件走 *Font
        root.option_add("*Font", (FAMILY, -SIZE_BODY))
    except Exception:
        pass


load()
