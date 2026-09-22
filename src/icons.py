# -*- coding: utf-8 -*-
"""图标生成：像素风"眼睛"图标（草地绿圆底 + 木质描边 + 眼睛）。

配色与界面共用同一调色板（theme.get()["window"]），
供托盘、窗口标题栏、exe 图标（ico 生成脚本）统一复用。
图形由 pixelart 在 16×16 原生像素上绘制，再整数倍放大 —— 边缘锐利，
不会出现平滑插值造成的糊边。
"""
import pixelart

try:  # 与主题保持单一来源；取色失败时回退同色值
    import theme
    _a = theme.get()["window"]["accent"].lstrip("#")
    GREEN = (int(_a[0:2], 16), int(_a[2:4], 16), int(_a[4:6], 16), 255)
except Exception:                                  # pragma: no cover
    GREEN = (94, 158, 61, 255)                     # #5E9E3D 草地绿


def thumb_icon(size=64):
    """生成像素眼睛图标（RGBA）。

    名称沿用旧接口名，调用方（托盘 / 窗口 / ico 脚本）无需改动。
    """
    return pixelart.app_icon(size)


def pixel_icon(size=64):
    """语义化别名。"""
    return pixelart.app_icon(size)
