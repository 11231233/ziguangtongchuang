#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_coord_vectors.py — 生成 coord_map 的系数与黄金向量（供 iverilog TB 使用）。

默认写 base 用例（兼容原回归）：
    sim/out/coord_coef.vh / coord_coef.txt / coord_vec.txt

--all 额外写多组系数/向量，供 scripts/test_coord_cases.py 做 RTL-vs-浮点多用例检查。
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from warp_model import CamParams, OutGeom, WarpParams, Q16

OUT = os.path.join(os.path.dirname(__file__), "..", "sim", "out")
os.makedirs(OUT, exist_ok=True)

NAMES = {
    "A": "A", "B": "B", "C": "C", "D": "D", "E": "E", "F": "F",
    "k1": "K1", "k2": "K2", "p1": "P1", "p2": "P2",
    "fx": "FX", "fy": "FY", "cx": "CX", "cy": "CY",
}


def cases():
    """返回 {case: WarpParams}。覆盖经验档、强畸变、大角度、倾斜、真实标定形参。"""
    base_cam = CamParams(fx=480.0, fy=480.0, cx=640.0, cy=360.0,
                         k1=-0.28, k2=0.08, p1=0.001, p2=-0.001)
    return {
        "base": WarpParams(cam=base_cam,
                           out=OutGeom(width=1280, height=720, fx=640.0, fy=640.0,
                                       cx=640.0, cy=360.0),
                           H=[[1, 0, 0], [0, 1, 0], [0, 0, 1]]),
        "s2z1": WarpParams(
            cam=CamParams(fx=520.0, fy=520.0, cx=640.0, cy=360.0,
                          k1=-0.40, k2=0.12, p1=0.0, p2=0.0),
            out=OutGeom(width=1280, height=720, fx=520.0, fy=520.0, cx=640.0, cy=360.0),
            zoom=1.25),
        "roll31p5": WarpParams(
            cam=CamParams(fx=520.0, fy=520.0, cx=640.0, cy=360.0,
                          k1=-0.28, k2=0.08, p1=0.001, p2=-0.0005),
            out=OutGeom(width=1280, height=720, fx=520.0, fy=520.0, cx=640.0, cy=360.0),
            roll_deg=31.5),
        "tilt": WarpParams(
            cam=CamParams(fx=520.0, fy=520.0, cx=640.0, cy=360.0,
                          k1=-0.28, k2=0.08, p1=0.001, p2=-0.0005),
            out=OutGeom(width=1280, height=720, fx=520.0, fy=520.0, cx=640.0, cy=360.0),
            roll_deg=12.25, yaw_deg=5.0, pitch_deg=-5.0),
        "realish": WarpParams(
            cam=CamParams(fx=802.832, fy=813.319, cx=642.271, cy=360.553,
                          k1=-0.157558, k2=0.125404, p1=0.002063, p2=-0.000216),
            out=OutGeom(width=1280, height=720, fx=802.832, fy=813.319,
                        cx=642.271, cy=360.553)),
    }


def points():
    pts = []
    for y in range(0, 720, 90):
        for x in range(0, 1280, 80):
            pts.append((x, y))
    for y in (0, 1, 719):
        for x in (0, 1, 1279):
            pts.append((x, y))
    return pts


def signed32(v):
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v & 0x80000000 else v


def write_case(name, wp, default=False):
    c = wp.coeffs()
    with open(os.path.join(OUT, "coord_coef_%s.txt" % name), "w", encoding="ascii") as f:
        for k in NAMES:
            f.write("%08x\n" % (c[k] & 0xFFFFFFFF))
    with open(os.path.join(OUT, "coord_coef_%s.vh" % name), "w", encoding="utf-8") as f:
        for k, vname in NAMES.items():
            sv = signed32(c[k])
            lit = ("-32'sd%d" % (-sv)) if sv < 0 else ("32'sd%d" % sv)
            f.write("localparam signed [31:0] %s = %s;\n" % (vname, lit))
    lines = []
    for (x, y) in points():
        u, v = wp.map_pixels(np.array([[float(x)]]), np.array([[float(y)]]))
        uq = int(round(float(u[0, 0]) * Q16)) & 0xFFFFFFFF
        vq = int(round(float(v[0, 0]) * Q16)) & 0xFFFFFFFF
        lines.append("%04x %04x %08x %08x" % (x, y, uq, vq))
    with open(os.path.join(OUT, "coord_vec_%s.txt" % name), "w", encoding="ascii") as f:
        f.write("\n".join(lines) + "\n")
    if default:
        with open(os.path.join(OUT, "coord_coef.txt"), "w", encoding="ascii") as f:
            for k in NAMES:
                f.write("%08x\n" % (c[k] & 0xFFFFFFFF))
        with open(os.path.join(OUT, "coord_vec.txt"), "w", encoding="ascii") as f:
            f.write("\n".join(lines) + "\n")
        with open(os.path.join(OUT, "coord_coef.vh"), "w", encoding="utf-8") as f:
            for k, vname in NAMES.items():
                sv = signed32(c[k])
                lit = ("-32'sd%d" % (-sv)) if sv < 0 else ("32'sd%d" % sv)
                f.write("localparam signed [31:0] %s = %s;\n" % (vname, lit))
    print("wrote case %-9s A=%d C=%d FX=%d CX=%d" % (name, signed32(c["A"]), signed32(c["C"]),
                                                     signed32(c["fx"]), signed32(c["cx"])))


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="write all cases, not only base")
    args = ap.parse_args()
    all_cases = cases()
    for name, wp in all_cases.items():
        if name == "base" or args.all:
            write_case(name, wp, default=(name == "base"))
    print("wrote %d vectors per case" % len(points()))


if __name__ == "__main__":
    main()
