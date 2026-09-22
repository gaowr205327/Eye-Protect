# -*- coding: utf-8 -*-
"""像素字体渲染验证：各字号渲染到画布 → 截图 → 再 3 倍放大便于逐像素检查。

用法: python -u scripts/font_check.py
产物: build/_font_test.png（原图）、build/_font_zoom.png（3 倍放大）
"""
import os
import sys
import tkinter as tk

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import fonts  # noqa: E402

TEXT_CN = "护眼助手 提醒间隔 25 分钟"
TEXT_EN = "ABCdef 0123456789"

SAMPLES = [
    ("正文 12px", fonts.spec(12)),
    ("标题 24px", fonts.spec(24)),
    ("36px", fonts.spec(36)),
    ("16px 非栅格", fonts.spec(16)),
    ("13px 非栅格", fonts.spec(13)),
    ("系统 10pt", ("Microsoft YaHei UI", 10)),
]

W, H = 900, 330
r = tk.Tk()
r.title("像素字体渲染验证")
r.geometry("%dx%d+40+40" % (W, H))
cv = tk.Canvas(r, width=W, height=H, bg="#fff6df", highlightthickness=0)
cv.pack()

y = 14
for label, ft in SAMPLES:
    cv.create_text(10, y, text=label, anchor="nw",
                   font=("Microsoft YaHei UI", 9), fill="#8a7147")
    cv.create_text(120, y, text=TEXT_CN, anchor="nw", font=ft, fill="#4a3620")
    cv.create_text(470, y, text=TEXT_EN, anchor="nw", font=ft, fill="#5e9e3d")
    y += 30
    if "-24" in str(ft) or "-36" in str(ft):
        y += 8

cv.create_text(10, H - 20, anchor="nw", font=("Microsoft YaHei UI", 9),
               fill="#8a7147",
               text="家族 = %s ｜ 像素字体已加载 = %s" % (fonts.FAMILY, fonts.is_pixel()))

r.update()


def shoot():
    from PIL import Image, ImageGrab
    x, yy = r.winfo_rootx(), r.winfo_rooty()
    im = ImageGrab.grab(bbox=(x, yy, x + W, yy + H))
    im.save(os.path.join(ROOT, "build", "_font_test.png"))
    # 3 倍放大（NEAREST）便于逐像素看锐利度
    im.resize((im.width * 2, im.height * 2), Image.NEAREST).save(
        os.path.join(ROOT, "build", "_font_zoom.png"))
    print("saved _font_test.png / _font_zoom.png", flush=True)
    print("family =", fonts.FAMILY, "| pixel =", fonts.is_pixel(), flush=True)
    r.destroy()


r.after(700, shoot)
r.mainloop()
