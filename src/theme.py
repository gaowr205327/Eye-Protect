# -*- coding: utf-8 -*-
"""界面配色（单一固定样式）：星露谷（Stardew Valley）田园像素风。

- window：设置主界面 + 像素绘制引擎（pixelart.py）共用的**唯一调色板**
- popup：提醒弹窗配色

像素风对调色板的要求是「少而稳」：整套界面只从下面这些色值里取，
其中 ink（描边）与 gold（点缀）是全屏共用的两个锚点色。

调用方统一用 get() 取配色；为保证兼容仍保留 get(name) 接口，
任意名称均返回这一套固定配色（config.py 的合法性校验依赖 SKINS/DEFAULT）。
"""
DEFAULT = "classic"

SKINS = {
    # ---------------- 星露谷（唯一固定样式） ----------------
    "classic": {
        "name": "星露谷",
        "window": {
            # ---- 基础层 ----
            "bg": "#e4cfa3",            # 窗口底色（暖木棕）
            "bg_lt": "#eddcb6",         # 底色亮部（抖动渐变用）
            "bg_dk": "#d2b985",         # 底色暗部（抖动渐变用）
            "card_bg": "#fff6df",       # 卡片内胆（奶油白）
            "border": "#8a5a2b",        # 卡片描边（深木棕）
            "bevel": "#d9b87c",         # 内嵌斜面（浅木高光）
            "shadow": "#5a4028",        # 硬偏移投影（无模糊，实心深褐）
            "wood": "#a9783f",          # 木质面（招牌/标签）
            "wood_dark": "#7a4e24",     # 木质描边
            "wood_hi": "#c89a5b",       # 木质高光
            "on_wood": "#fff6df",       # 木面上的文字（奶油）
            "ink": "#3d2b1f",           # 最深层描边（像素画的"墨线"）
            # ---- 强调色 ----
            "accent": "#5e9e3d",        # 主强调色（草地绿）
            "accent_hover": "#4e8631",  # 悬停
            "accent_fg": "#fffdf4",     # 主按钮文字
            "grass": "#5e9e3d",         # 草绿中间调（装饰草丛用）
            "grass_dk": "#2b5f1c",      # 草绿暗部（按钮描边）
            "grass_lt": "#a6d66c",      # 草绿亮部（按钮高光）
            # ---- 文字 ----
            "text": "#4a3620",          # 正文（可可棕）
            "sub": "#8a7147",           # 次要文字
            # ---- 次级控件 ----
            "soft_bg": "#f0ddb0",       # 次级按钮底（浅木色）
            "soft_hover": "#e6ce94",    # 次级按钮悬停
            "soft_fg": "#7a5a28",       # 次级按钮文字
            "input_bg": "#fffbe9",      # 输入框底
            # ---- 状态 ----
            "status_ok": "#5e9e3d",     # 运行中（草地绿）
            "status_pause": "#d9962e",  # 暂停（麦穗金）
            # ---- 装饰件用色 ----
            "gold": "#f2c14e",          # 铆钉/星星
            "gold_dk": "#b8862b",
            "gold_lt": "#ffe08a",
            "red": "#cc3e3e",           # 小花/爱心
            "red_dk": "#8c222a",
            "red_lt": "#f07e76",
            "sky": "#89c4f4",           # 花瓣/瞳孔
            "pap": "#f5deb3",           # 羊皮纸
            "pap_lt": "#fff8e0",
            "pap_dk": "#d6b784",
            "soil": "#8a5a34",          # 泥土（底部草地条）
            "soil_dk": "#5e3a1e",
            "white": "#ffffff",
        },
        "popup": {
            "accent": "#a8743a",        # 顶部木框色带
            "accent_hover": "#96652f",  # 色带悬停（备用）
            "btn": "#5e9e3d",           # 按钮底（草地绿）
            "btn_hover": "#4e8631",     # 按钮悬停
            "btn_fg": "#fffdf4",        # 按钮文字
            "top": "#fff8e8",           # 卡片渐变顶（奶油）
            "bottom": "#f2e0bb",        # 卡片渐变底（浅木）
            "text": "#4a3620",          # 标题/正文
            "sub": "#8a7147",           # 底部小字
        },
    },
}


def get(name=None):
    """取配色定义（单一固定样式，忽略传入名称）。"""
    return SKINS[DEFAULT]
