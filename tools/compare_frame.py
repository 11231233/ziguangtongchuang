#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""compare_frame.py — 比对 RTL 矫正结果与 Python 模型，并输出对比图"""
import os
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "sim", "out")


def load(path, w, h):
    a = np.zeros((h, w), np.uint16)
    with open(path) as f:
        rows = [r.split() for r in f if r.strip()]
    for y in range(min(h, len(rows))):
        for x in range(min(w, len(rows[y]))):
            a[y, x] = int(rows[y][x], 16)
    return a


def to_rgb(a):
    r = ((a >> 11) & 0x1F) * 255 // 31
    g = ((a >> 5) & 0x3F) * 255 // 63
    b = (a & 0x1F) * 255 // 31
    return np.dstack([r, g, b]).astype(np.uint8)


W, H = 128, 64
rtl = load(os.path.join(OUT, "frame_out.txt"), W, H)
exp = load(os.path.join(OUT, "frame_expect.txt"), W, H)

dr = np.abs(((rtl >> 11) & 0x1F).astype(int) - ((exp >> 11) & 0x1F).astype(int))
dg = np.abs(((rtl >> 5) & 0x3F).astype(int) - ((exp >> 5) & 0x3F).astype(int))
db = np.abs((rtl & 0x1F).astype(int) - (exp & 0x1F).astype(int))
bad = (dr > 2) | (dg > 3) | (db > 2)
print("pixels:", W * H, "mismatch(>2 LSB):", int(bad.sum()),
      "max dR=%d dG=%d dB=%d" % (dr.max(), dg.max(), db.max()))

img = np.concatenate([to_rgb(exp), np.full((H, 4, 3), 255, np.uint8), to_rgb(rtl)], axis=1)
Image.fromarray(img).resize((img.shape[1] * 4, img.shape[0] * 4), Image.NEAREST).save(
    os.path.join(OUT, "frame_compare.png"))
print("wrote", os.path.join(OUT, "frame_compare.png"))
