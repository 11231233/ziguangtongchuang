#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_frame_test.py — 生成整帧矫正的联合仿真输入（源图 / 系数 / tile 包围盒 / 期望输出）"""
import os
import numpy as np

from warp_model import CamParams, OutGeom, WarpParams, Q16

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "sim", "out")
os.makedirs(OUT, exist_ok=True)

OUT_W, OUT_H = 128, 64          # 输出图
SRC_W, SRC_H = 192, 96          # 源图
TILE = 32

cam = CamParams(fx=60.0, fy=60.0, cx=96.0, cy=48.0, k1=-0.25, k2=0.06, p1=0.0005, p2=-0.0005)
out = OutGeom(width=OUT_W, height=OUT_H, fx=90.0, fy=90.0, cx=OUT_W/2, cy=OUT_H/2)
wp = WarpParams(cam=cam, out=out, H=[[1, 0, 0], [0, 1, 0], [0, 0, 1]])
c = wp.coeffs()

# ---- 源图：横向渐变 + 网格（便于肉眼判断几何）----
src = np.zeros((SRC_H, SRC_W, 3), np.uint8)
for y in range(SRC_H):
    for x in range(SRC_W):
        r = (x * 255 // (SRC_W - 1)) & 0xF8
        g = (y * 255 // (SRC_H - 1)) & 0xFC
        b = 0x20 if (x % 16 == 0 or y % 16 == 0) else 0x80
        src[y, x] = (r, g, b)

def pack(p):
    return ((p[0] >> 3) << 11) | ((p[1] >> 2) << 5) | (p[2] >> 3)

with open(os.path.join(OUT, "frame_src.txt"), "w") as f:
    for y in range(SRC_H):
        f.write(" ".join("%04x" % pack(src[y, x]) for x in range(SRC_W)) + "\n")

# ---- 系数 ----
names = {"A":"A","B":"B","C":"C","D":"D","E":"E","F":"F",
         "k1":"K1","k2":"K2","p1":"P1","p2":"P2",
         "fx":"FX","fy":"FY","cx":"CX","cy":"CY"}
with open(os.path.join(OUT, "frame_coef.vh"), "w") as f:
    for k, v in names.items():
        val = c[k]; sv = val - (1 << 32) if val & 0x80000000 else val
        lit = ("-32'sd%d" % (-sv)) if sv < 0 else ("32'sd%d" % sv)
        f.write("localparam signed [31:0] %s = %s;\n" % (v, lit))

# ---- 每个 tile 的包围盒（9 点采样 + 8px 余量，与设计一致）----
tiles = []
for ty in range(0, OUT_H, TILE):
    for tx in range(0, OUT_W, TILE):
        pts = []
        for sy in (0, TILE//2, TILE-1):
            for sx in (0, TILE//2, TILE-1):
                u, v = wp.map_pixels(np.array([[float(tx+sx)]]), np.array([[float(ty+sy)]]))
                pts.append((float(u[0,0]), float(v[0,0])))
        us = [p[0] for p in pts]; vs = [p[1] for p in pts]
        u0 = max(0, int(np.floor(min(us))) - 8)
        v0 = max(0, int(np.floor(min(vs))) - 8)
        u1 = min(SRC_W-1, int(np.ceil(max(us))) + 8)
        v1 = min(SRC_H-1, int(np.ceil(max(vs))) + 8)
        bw = min(64, u1 - u0 + 2); bh = min(64, v1 - v0 + 2)
        tiles.append((tx, ty, u0, v0, bw, bh))

with open(os.path.join(OUT, "frame_tiles.vh"), "w") as f:
    f.write("localparam integer N_TILES = %d;\n" % len(tiles))
    for i, t in enumerate(tiles):
        f.write("localparam [15:0] T%d_TX=%d, T%d_TY=%d, T%d_U0=%d, T%d_V0=%d, T%d_BW=%d, T%d_BH=%d;\n"
                % (i, t[0], i, t[1], i, t[2], i, t[3], i, t[4], i, t[5]))

# ---- 期望输出（浮点模型，双线性）----
dst = wp.render(src, (OUT_H, OUT_W))
with open(os.path.join(OUT, "frame_expect.txt"), "w") as f:
    for y in range(OUT_H):
        f.write(" ".join("%04x" % pack(dst[y, x]) for x in range(OUT_W)) + "\n")

print("tiles:", len(tiles), "max bbox:", max(t[4] for t in tiles), "x", max(t[5] for t in tiles))
