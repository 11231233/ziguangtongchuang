#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_bilin_vectors.py — 生成 bilinear_2x2 的测试向量（含边界情况）"""
import os
import random

OUT = os.path.join(os.path.dirname(__file__), "..", "sim", "out")
os.makedirs(OUT, exist_ok=True)
random.seed(1234)


def rnd565():
    return random.randint(0, 0xFFFF)


def blend(p00, p01, p10, p11, fu, fv):
    w00 = (256 - fu) * (256 - fv)
    w01 = fu * (256 - fv)
    w10 = (256 - fu) * fv
    w11 = fu * fv

    def ch(v, sh, m):
        return (v >> sh) & m

    def mix(sh, m):
        s = (ch(p00, sh, m) * w00 + ch(p01, sh, m) * w01 +
             ch(p10, sh, m) * w10 + ch(p11, sh, m) * w11)
        return (s >> 16) & m

    return (mix(11, 0x1F) << 11) | (mix(5, 0x3F) << 5) | mix(0, 0x1F)


cases = []
# 边界：全 0 / 全 1 权重 / 同色
for fu, fv in [(0, 0), (255, 255), (0, 255), (255, 0), (128, 128), (1, 0), (0, 1)]:
    cases.append((0x0000, 0xFFFF, 0xF800, 0x07E0, fu, fv))
    cases.append((0x1234, 0x1234, 0x1234, 0x1234, fu, fv))
# 随机
for _ in range(200):
    cases.append((rnd565(), rnd565(), rnd565(), rnd565(),
                  random.randint(0, 255), random.randint(0, 255)))

lines = []
for (p00, p01, p10, p11, fu, fv) in cases:
    exp = blend(p00, p01, p10, p11, fu, fv)
    lines.append("%04x %04x %04x %04x %02x %02x %04x" % (p00, p01, p10, p11, fu, fv, exp))

with open(os.path.join(OUT, "bilin_vec.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print("wrote", len(lines), "vectors")
