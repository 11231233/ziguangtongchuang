#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
warp_model.py — 畸变矫正的“黄金模型” + RTL 定点系数导出

坐标定义（与 RTL 完全一致）
--------------------------
输出像素 (x, y)，x∈[0,W), y∈[0,H)。

1) 先把输出像素送到“归一化平面”：
      nx = (x - ox) * sx
      ny = (y - oy) * sy
   其中 sx = 1/fx_out，sy = 1/fy_out，ox/oy 是输出主点。整条线性映射被折叠进
   仿射系数 A..F，所以 RTL 里只需要算：
      ux = A*x + B*y + C          (Q4.16, 单位=焦距归一化)
      uy = D*x + E*y + F

2) 归一化平面上的畸变（OpenCV 模型，k1 k2 p1 p2）：
      r2  = ux² + uy²
      rad = 1 + k1*r2 + k2*r2²
      dx  = 2*p1*ux*uy + p2*(r2 + 2*ux²)
      dy  = p1*(r2 + 2*uy²) + 2*p2*ux*uy
      xd  = ux*rad + dx
      yd  = uy*rad + dy

3) 回到源图像素坐标：
      u = fx*Xd + cx
      v = fy*Yd + cy

注意：这是“输出→源”的反向映射（inverse mapping），双线性插值在源图上取样，
      因此不会产生空洞。正向映射只用于离线生成测试数据。

定点格式（RTL）
---------------
  A..F        : 32 bit, Q16.16（有符号）
  k1,k2,p1,p2 : 32 bit, Q2.16（有符号，即 ±2.0）
  fx,fy,cx,cy : 32 bit, Q16.16
  u,v         : 32 bit, Q16.16（像素坐标）
  双线性权重   : 8 bit（小数部分 >>8）
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict

import numpy as np

Q16 = 1 << 16
MASK32 = 0xFFFFFFFF


def f32(v: float) -> int:
    """浮点 → 32bit 补码（Q16.16）"""
    return int(round(v * Q16)) & MASK32


def s32(v: int) -> int:
    v &= MASK32
    return v - (1 << 32) if v & 0x80000000 else v


def from_q16(v: int) -> float:
    return s32(v) / Q16


@dataclass
class CamParams:
    """源相机内参 + 畸变（OpenCV 约定）"""
    fx: float = 480.0
    fy: float = 480.0
    cx: float = 640.0
    cy: float = 360.0
    k1: float = -0.28
    k2: float = 0.08
    p1: float = 0.0
    p2: float = 0.0


@dataclass
class OutGeom:
    """输出（显示）几何：把像素坐标归一化的虚拟相机"""
    width: int = 1280
    height: int = 720
    fx: float = 640.0
    fy: float = 640.0
    cx: float = 640.0
    cy: float = 360.0


@dataclass
class WarpParams:
    cam: CamParams = None
    out: OutGeom = None
    # 3x3 变换：输出归一化坐标 → 源归一化坐标（上 2x3 有效；仿射）
    H: list = None
    zoom: float = 1.0
    roll_deg: float = 0.0
    yaw_deg: float = 0.0
    pitch_deg: float = 0.0
    tx: float = 0.0   # 归一化平移
    ty: float = 0.0

    def __post_init__(self):
        if self.cam is None:
            self.cam = CamParams()
        if self.out is None:
            self.out = OutGeom()
        if self.H is None:
            self.H = self.build_H()

    # ------------------------------------------------------------------
    def build_H(self) -> list:
        """由 欧拉角/缩放/平移 构造 3x3（旋转 + 平移 + 缩放）"""
        r = math.radians(self.roll_deg)
        y = math.radians(self.yaw_deg)
        p = math.radians(self.pitch_deg)

        # 绕光轴 roll（图像平面内旋转）
        Rz = np.array([[math.cos(r), -math.sin(r), 0.0],
                       [math.sin(r),  math.cos(r), 0.0],
                       [0.0, 0.0, 1.0]])
        # 绕 Y 轴（yaw，水平摆头）、绕 X 轴（pitch，俯仰）产生的透视项
        Ry = np.array([[math.cos(y), 0.0, math.sin(y)],
                       [0.0, 1.0, 0.0],
                       [-math.sin(y), 0.0, math.cos(y)]])
        Rx = np.array([[1.0, 0.0, 0.0],
                       [0.0, math.cos(p), -math.sin(p)],
                       [0.0, math.sin(p),  math.cos(p)]])
        R = Rz @ Ry @ Rx
        S = np.diag([1.0 / max(self.zoom, 1e-6), 1.0 / max(self.zoom, 1e-6), 1.0])
        T = np.array([[1.0, 0.0, self.tx],
                      [0.0, 1.0, self.ty],
                      [0.0, 0.0, 1.0]])
        return (T @ S @ R).tolist()

    # ------------------------------------------------------------------
    def coeffs(self) -> dict:
        """把 3x3 变换和输出几何折叠成 RTL 需要的 6 个系数（Q16.16 整数）"""
        H = np.array(self.H, dtype=float)
        o = self.out
        # 归一化：nx = (x-cx)/fx
        sx, sy = 1.0 / o.fx, 1.0 / o.fy
        # u = H00*(x-cx)/fx + H01*(y-cy)/fy + H02
        A = H[0, 0] * sx
        B = H[0, 1] * sy
        C = H[0, 2] - H[0, 0] * o.cx / o.fx - H[0, 1] * o.cy / o.fy
        D = H[1, 0] * sx
        E = H[1, 1] * sy
        F = H[1, 2] - H[1, 0] * o.cx / o.fx - H[1, 1] * o.cy / o.fy
        return {
            "A": f32(A), "B": f32(B), "C": f32(C),
            "D": f32(D), "E": f32(E), "F": f32(F),
            "k1": f32(self.cam.k1), "k2": f32(self.cam.k2),
            "p1": f32(self.cam.p1), "p2": f32(self.cam.p2),
            "fx": f32(self.cam.fx), "fy": f32(self.cam.fy),
            "cx": f32(self.cam.cx), "cy": f32(self.cam.cy),
        }

    # ------------------------------------------------------------------
    def map_pixels_ideal(self, x: np.ndarray, y: np.ndarray):
        """Unquantized affine/camera reference; no Q16 coefficient round trip.

        Like the RTL, H contributes only its first two rows (affine mapping),
        with no perspective division. map_pixels retains its existing Q16
        affine semantics for the RTL regression vectors.
        """
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        H = np.asarray(self.H, dtype=np.float64)
        nx = (x - self.out.cx) / self.out.fx
        ny = (y - self.out.cy) / self.out.fy
        ux = H[0, 0] * nx + H[0, 1] * ny + H[0, 2]
        uy = H[1, 0] * nx + H[1, 1] * ny + H[1, 2]
        k1, k2, p1, p2 = self.cam.k1, self.cam.k2, self.cam.p1, self.cam.p2
        r2 = ux * ux + uy * uy
        radial = 1.0 + k1 * r2 + k2 * r2 * r2
        xd = ux * radial + 2 * p1 * ux * uy + p2 * (r2 + 2 * ux * ux)
        yd = uy * radial + p1 * (r2 + 2 * uy * uy) + 2 * p2 * ux * uy
        return self.cam.fx * xd + self.cam.cx, self.cam.fy * yd + self.cam.cy

    # ------------------------------------------------------------------
    def map_pixels(self, x: np.ndarray, y: np.ndarray):
        """浮点参考：输出像素坐标 → 源像素坐标（u, v）"""
        c = self.coeffs()
        A, B, C, D, E, F = (from_q16(c[k]) for k in "ABCDEF")
        ux = A * x + B * y + C
        uy = D * x + E * y + F
        k1, k2, p1, p2 = self.cam.k1, self.cam.k2, self.cam.p1, self.cam.p2
        r2 = ux * ux + uy * uy
        rad = 1.0 + k1 * r2 + k2 * r2 * r2
        dx = 2 * p1 * ux * uy + p2 * (r2 + 2 * ux * ux)
        dy = p1 * (r2 + 2 * uy * uy) + 2 * p2 * ux * uy
        xd = ux * rad + dx
        yd = uy * rad + dy
        # 像素中心约定：连续坐标 +0.5 再取样，避免整数边界抖动
        return self.cam.fx * xd + self.cam.cx, self.cam.fy * yd + self.cam.cy

    # ------------------------------------------------------------------
    def render(self, src: np.ndarray, out_hw=None) -> np.ndarray:
        """用双线性插值把 src 反向映射成校正图（src: HxWx3 uint8）"""
        o = self.out
        h, w = (out_hw if out_hw else (o.height, o.width))
        xs, ys = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
        u, v = self.map_pixels(xs, ys)
        sh, sw = src.shape[:2]
        valid = (u >= 0) & (u <= sw - 1.001) & (v >= 0) & (v <= sh - 1.001)
        u0 = np.floor(u).astype(np.int32)
        v0 = np.floor(v).astype(np.int32)
        u0 = np.clip(u0, 0, sw - 2)
        v0 = np.clip(v0, 0, sh - 2)
        fu = (u - u0)[..., None]
        fv = (v - v0)[..., None]
        p00 = src[v0, u0].astype(np.float32)
        p01 = src[v0, u0 + 1].astype(np.float32)
        p10 = src[v0 + 1, u0].astype(np.float32)
        p11 = src[v0 + 1, u0 + 1].astype(np.float32)
        out = (p00 * (1 - fu) * (1 - fv) + p01 * fu * (1 - fv) +
               p10 * (1 - fu) * fv + p11 * fu * fv)
        out[~valid] = 0
        return np.clip(out + 0.5, 0, 255).astype(np.uint8)


# ----------------------------------------------------------------------
def gen_checkerboard(w=1280, h=720, sq=64, cols=13, rows=8) -> np.ndarray:
    """生成一张用于仿真的棋盘格（白底黑格）"""
    img = np.full((h, w, 3), 255, np.uint8)
    y0 = (h - (rows - 1) * sq) // 2
    x0 = (w - (cols - 1) * sq) // 2
    for r in range(rows):
        for c in range(cols):
            if (r + c) % 2 == 0:
                y, x = y0 + r * sq, x0 + c * sq
                img[y:y + sq, x:x + sq] = 0
    return img


def main():
    import argparse
    ap = argparse.ArgumentParser(description="畸变矫正黄金模型 / 系数导出")
    ap.add_argument("--out-json", default="coeff.json")
    ap.add_argument("--in-png")
    ap.add_argument("--out-png", default="warped.png")
    ap.add_argument("--roll", type=float, default=0.0)
    ap.add_argument("--zoom", type=float, default=1.0)
    ap.add_argument("--k1", type=float, default=-0.28)
    ap.add_argument("--k2", type=float, default=0.08)
    ap.add_argument("--calib", help="calib_ov5640.py output JSON; exact four-term model")
    ap.add_argument("--out-fx", type=float, help="virtual output focal length; default=camera fx")
    ap.add_argument("--out-fy", type=float, help="virtual output focal length; default=camera fy")
    ap.add_argument("--out-cx", type=float, help="virtual output principal point; default=camera cx")
    ap.add_argument("--out-cy", type=float, help="virtual output principal point; default=camera cy")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--vh", help="optional Verilog localparam output for coord_map")
    args = ap.parse_args()

    wp = WarpParams(roll_deg=args.roll, zoom=args.zoom)
    wp.cam.k1, wp.cam.k2 = args.k1, args.k2
    if args.calib:
        with open(args.calib,encoding='utf-8') as f:calib=json.load(f)
        if abs(calib.get('k3',0))>1e-9:ap.error('k3 is unsupported; recalibrate with k3 fixed to zero')
        wp.cam=CamParams(**{k:calib[k] for k in ('fx','fy','cx','cy','k1','k2','p1','p2')})
    # 默认让输出虚拟相机与源相机同焦距、同主点：roll=0、zoom=1 时系数应给出 1:1 映射。
    # 旧版固定 OutGeom(fx=640) 会让 fx=520 的标定得到 A=102/C=-65536，映射成 0.8125x+120。
    wp.out = OutGeom(
        width=args.width, height=args.height,
        fx=wp.cam.fx if args.out_fx is None else args.out_fx,
        fy=wp.cam.fy if args.out_fy is None else args.out_fy,
        cx=wp.cam.cx if args.out_cx is None else args.out_cx,
        cy=wp.cam.cy if args.out_cy is None else args.out_cy,
    )
    wp.H = wp.build_H()
    coeff = wp.coeffs()
    coeff_signed = {k: s32(v) for k, v in coeff.items()}

    data = {
        "cam": asdict(wp.cam),
        "out": asdict(wp.out),
        "H": wp.H,
        "roll_deg": wp.roll_deg,
        "zoom": wp.zoom,
        "coeff": coeff,
        "coeff_signed": coeff_signed,
        "coeff_hex": {k: "0x%08x" % v for k, v in coeff.items()},
    }
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("wrote", args.out_json)
    print("coeff:", {k: hex(v) for k, v in coeff.items()})

    if args.vh:
        names = {"A":"A","B":"B","C":"C","D":"D","E":"E","F":"F",
                 "k1":"K1","k2":"K2","p1":"P1","p2":"P2",
                 "fx":"FX","fy":"FY","cx":"CX","cy":"CY"}
        with open(args.vh, "w", encoding="utf-8") as f:
            for key, name in names.items():
                v = coeff_signed[key]
                lit = ("-32'sd%d" % (-v)) if v < 0 else ("32'sd%d" % v)
                f.write("localparam signed [31:0] %s = %s;\n" % (name, lit))
        print("wrote", args.vh)

    if args.in_png:
        from PIL import Image
        src = np.array(Image.open(args.in_png).convert("RGB"))
        dst = wp.render(src)
        Image.fromarray(dst).save(args.out_png)
        print("wrote", args.out_png)


if __name__ == "__main__":
    main()
