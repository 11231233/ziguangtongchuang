#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_targets.py — 生成可直接打印的标定/畸变测试靶标

输出（默认到 targets\）：
  checkerboard_9x6_25mm_A4.png   棋盘格标定板（9×6 内角点，25mm 方格，A4 300dpi）
  grid_40mm_A4.png               方格纸（40mm 方格 + 中心十字），用来看直线弯曲
  lines_A4.png                   横竖直线靶（等间距细线），畸变最直观

打印要求：A4、实际大小(100%)、不要"适应页面"，打印后量一下方格边长是否为标称值。
"""
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "targets")
os.makedirs(OUT, exist_ok=True)

DPI = 300
A4_MM = (210, 297)


def px(mm):
    return int(round(mm / 25.4 * DPI))


def a4_canvas(landscape=False):
    w, h = px(A4_MM[0]), px(A4_MM[1])
    if landscape:
        w, h = h, w
    return np.full((h, w), 255, np.uint8)


def save(img, name):
    Image.fromarray(img).save(os.path.join(OUT, name), dpi=(DPI, DPI))
    print("wrote", os.path.join(OUT, name), img.shape[1], "x", img.shape[0])


def checkerboard():
    img = a4_canvas(landscape=True)   # 250×175mm 的棋盘格需要横向 A4
    sq = px(25.0)                    # 25mm 方格
    cols, rows = 10, 7               # 10×7 格 → 9×6 内角点
    bw, bh = cols * sq, rows * sq
    x0 = (img.shape[1] - bw) // 2
    y0 = (img.shape[0] - bh) // 2
    for r in range(rows):
        for c in range(cols):
            if (r + c) % 2 == 0:
                img[y0 + r * sq:y0 + (r + 1) * sq, x0 + c * sq:x0 + (c + 1) * sq] = 0
    # 四角定位标记（便于自动检测打印缩放）
    m = px(4)
    for (yy, xx) in ((y0, x0), (y0, x0 + bw - m), (y0 + bh - m, x0), (y0 + bh - m, x0 + bw - m)):
        img[yy:yy + m, xx:xx + m] = 128
    save(img, "checkerboard_9x6_25mm_A4.png")


def grid():
    img = a4_canvas()
    step = px(40.0)                  # 40mm 方格
    h, w = img.shape
    for x in range(px(10), w - px(10), step):
        img[:, x:x + 2] = 0
    for y in range(px(10), h - px(10), step):
        img[y:y + 2, :] = 0
    cx, cy = w // 2, h // 2
    img[cy - 3:cy + 3, :] = 0
    img[:, cx - 3:cx + 3] = 0
    save(img, "grid_40mm_A4.png")


def lines():
    img = a4_canvas()
    step = px(10.0)                  # 10mm 细线
    h, w = img.shape
    for x in range(px(15), w - px(15), step):
        img[px(15):h - px(15), x:x + 1] = 0
    for y in range(px(15), h - px(15), step):
        img[y:y + 1, px(15):w - px(15)] = 0
    save(img, "lines_A4.png")


if __name__ == "__main__":
    checkerboard()
    grid()
    lines()
    print("\n打印提示：A4 / 实际大小 / 不缩放；棋盘格打印后用尺子量方格应为 25.0mm")
    print("标定拍 15~20 张：正对、左右倾斜、上下倾斜、远近各来几张，棋盘占画面 1/3~2/3")
