# -*- coding: utf-8 -*-
"""生成应用图标 assets/icon.ico（胖次蓝圆底 + 👍），供 exe 使用。

与托盘/窗口图标同源（icons.thumb_icon），保证外观一致。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from icons import thumb_icon  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "..", "assets", "icon.ico")
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    # 用 256px 主图，保存时自动缩放出各尺寸
    thumb_icon(256).save(OUT, sizes=SIZES)
    print("图标已生成:", os.path.abspath(OUT))


if __name__ == "__main__":
    main()
