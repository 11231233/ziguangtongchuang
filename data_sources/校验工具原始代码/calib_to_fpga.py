#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""calib_to_fpga.py — 把标定 JSON 变成 FPGA 可用的系数、Verilog 与 UART 包。

一条命令完成：
    python tools/calib_to_fpga.py --calib calib/result.json --out-dir calib/coeff_01

输出：
    coeff.json    有符号/无符号/十六进制系数、输入哈希、几何检查
    coeff.vh      coord_map 可直接 include 的 localparam
    packet.bin    62 字节 UART 包（A5 5A | 01 | seq | 14×int32 LE | CRC16）
    report.md     人读报告：标定来源、RMS、系数、量化误差、窗口检查、限制

安全门禁：
    - 默认只接受 source_kind=ov5640_raw_digital 的标定；
    - monitor_rectified（手机拍屏间接估计）必须显式 --allow-indirect；
    - synthetic 必须显式 --allow-synthetic；
    - phone_direct 是手机内参，默认拒绝（--allow-phone 仅用于生成手机模型报告）。
"""
from __future__ import annotations

import argparse
import binascii
import hashlib
import json
import math
import struct
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from warp_model import CamParams, OutGeom, WarpParams, from_q16, s32  # noqa: E402
from validate_coefficients import validate  # noqa: E402

FIELDS = ("A", "B", "C", "D", "E", "F", "k1", "k2", "p1", "p2", "fx", "fy", "cx", "cy")
COEFF_18BIT = ("A", "B", "D", "E", "k1", "k2", "p1", "p2")


def die(msg: str) -> None:
    raise SystemExit(msg)


def scope_of(calib: dict) -> str:
    kind = str(calib.get("source_kind_operator_declared", ""))
    scope = str(calib.get("calibration_scope", ""))
    if kind == "ov5640_raw_digital":
        return "raw_digital"
    if kind == "monitor_rectified" or scope == "ov5640_indirect_monitor_estimate":
        return "indirect"
    if kind == "synthetic":
        return "synthetic"
    if kind == "phone_direct":
        return "phone"
    return "unknown"


def load_calib(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    calib = json.loads(raw.decode("utf-8-sig"))
    for key in ("fx", "fy", "cx", "cy", "k1", "k2", "p1", "p2"):
        if key not in calib:
            die(f"标定文件缺少 {key}: {path}")
        try:
            calib[key] = float(calib[key])
        except (TypeError, ValueError):
            die(f"标定字段 {key} 不是数字: {calib[key]!r}")
    if not all(math.isfinite(calib[k]) for k in ("fx", "fy", "cx", "cy", "k1", "k2", "p1", "p2")):
        die("标定字段含 NaN/Inf")
    if calib["fx"] <= 0 or calib["fy"] <= 0:
        die("fx/fy 必须为正")
    if abs(float(calib.get("k3", 0.0))) > 1e-9:
        die("FPGA 只实现 k3=0；请用 CALIB_FIX_K3 重新标定，不能把 k3 直接丢掉")
    calib["_sha256"] = hashlib.sha256(raw).hexdigest()
    return calib, calib["_sha256"]


def check_scope(calib: dict, allow_indirect: bool, allow_synthetic: bool, allow_phone: bool) -> str:
    scope = scope_of(calib)
    if scope == "raw_digital":
        return scope
    if scope == "indirect":
        if not allow_indirect:
            die("这是手机拍屏的间接估计（monitor_rectified），必须显式 --allow-indirect；"
                "它不能当作 OV5640 原始数字标定。")
        return scope
    if scope == "synthetic":
        if not allow_synthetic:
            die("合成数据只用于工具自检，必须显式 --allow-synthetic；不能写入比赛固件。")
        return scope
    if scope == "phone":
        if not allow_phone:
            die("phone_direct 是手机内参，不是 OV5640 系数；"
                "请先完成 monitor_rectified 第二阶段，或使用原始数字帧。")
        return scope
    die("标定文件没有可识别的来源声明（source_kind_operator_declared）；"
        "拒绝把来源不明的参数写入 FPGA。")


def quantized_error(calib: dict, coeff: dict, out: OutGeom, step: int = 32, *,
                    roll: float = 0, yaw: float = 0, pitch: float = 0,
                    zoom: float = 1, H=None) -> dict:
    """Compare quantized coefficients with the same unquantized affine model.

    The reference includes the requested transform and output principal point;
    it must not reuse quantized A..F or omit a nonzero roll/tilt/zoom.
    This measures coefficient quantization, not subsequent RTL rounding.
    """
    if not isinstance(step, (int, np.integer)) or step <= 0:
        raise ValueError('quantization grid step must be a positive integer')
    A, B, C, D, E, F = (from_q16(coeff[k]) for k in "ABCDEF")
    k1, k2, p1, p2 = (from_q16(coeff[k]) for k in ("k1", "k2", "p1", "p2"))
    fx, fy, cx, cy = (from_q16(coeff[k]) for k in ("fx", "fy", "cx", "cy"))
    wp = WarpParams(
        cam=CamParams(fx=calib["fx"], fy=calib["fy"], cx=calib["cx"], cy=calib["cy"],
                      k1=calib["k1"], k2=calib["k2"], p1=calib["p1"], p2=calib["p2"]),
        out=out, roll_deg=roll, yaw_deg=yaw, pitch_deg=pitch, zoom=zoom, H=H,
    )
    # Include the far edges, where affine slope quantization accumulates most.
    xs = np.unique(np.append(np.arange(0, out.width, step, dtype=np.float64), out.width - 1))
    ys = np.unique(np.append(np.arange(0, out.height, step, dtype=np.float64), out.height - 1))
    gx, gy = np.meshgrid(xs, ys)
    ux = A * gx + B * gy + C
    uy = D * gx + E * gy + F
    r2 = ux * ux + uy * uy
    rad = 1.0 + k1 * r2 + k2 * r2 * r2
    dx = 2 * p1 * ux * uy + p2 * (r2 + 2 * ux * ux)
    dy = p1 * (r2 + 2 * uy * uy) + 2 * p2 * ux * uy
    uq = fx * (ux * rad + dx) + cx
    vq = fy * (uy * rad + dy) + cy
    ue, ve = wp.map_pixels_ideal(gx, gy)
    err = np.hypot(uq - ue, vq - ve)
    return {
        "grid_points": int(err.size),
        "max_px": float(err.max()),
        "mean_px": float(err.mean()),
        "p95_px": float(np.percentile(err, 95)),
        "threshold_px": 0.25,
        "passed": bool(err.max() <= 0.25),
        "reference": "unquantized_affine_and_camera_model",
        "includes_affine_quantization": True,
        "includes_rtl_intermediate_rounding": False,
    }


def write_outputs(calib: dict, coeff: dict, signed: dict, out_dir: Path,
                  scope: str, geo: dict, qerr: dict, out: OutGeom,
                  roll: float, yaw: float, pitch: float, zoom: float) -> dict:
    # main() has already created the directory after checking overwrite policy.
    coeff_json = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "input_calibration_sha256": calib["_sha256"],
        "source_kind": calib.get("source_kind_operator_declared"),
        "calibration_scope": calib.get("calibration_scope"),
        "accepted_scope": scope,
        "image_size": calib.get("image_size"),
        "frames_used": calib.get("frames_used"),
        "rms": calib.get("rms"),
        "k3": calib.get("k3", 0.0),
        "out_geometry": {"width": out.width, "height": out.height,
                         "fx": out.fx, "fy": out.fy, "cx": out.cx, "cy": out.cy},
        "roll_deg": roll, "yaw_deg": yaw, "pitch_deg": pitch, "zoom": zoom,
        "coeff": coeff,
        "coeff_signed": signed,
        "coeff_hex": {k: "0x%08x" % v for k, v in coeff.items()},
        "geometry_guard": geo,
        "quantization_error": qerr,
        "real_ov5640_calibration": scope == "raw_digital",
        "indirect_estimate": scope == "indirect",
        "synthetic": scope == "synthetic",
    }
    (out_dir / "coeff.json").write_text(
        json.dumps(coeff_json, indent=2, ensure_ascii=False), encoding="utf-8")

    names = {"A": "A", "B": "B", "C": "C", "D": "D", "E": "E", "F": "F",
             "k1": "K1", "k2": "K2", "p1": "P1", "p2": "P2",
             "fx": "FX", "fy": "FY", "cx": "CX", "cy": "CY"}
    vh = ["// Generated by calib_to_fpga.py — include inside coord_map testbench or top",
          "// input_sha256=%s" % calib["_sha256"]]
    for key, name in names.items():
        v = signed[key]
        lit = ("-32'sd%d" % (-v)) if v < 0 else ("32'sd%d" % v)
        vh.append("localparam signed [31:0] %s = %s;" % (name, lit))
    (out_dir / "coeff.vh").write_text("\n".join(vh) + "\n", encoding="utf-8")

    seq = int(calib.get("_sequence", 1)) & 0xFF or 1
    body = bytes((1, seq)) + struct.pack("<14i", *[signed[k] for k in FIELDS])
    packet = b"\xa5\x5a" + body + struct.pack(">H", binascii.crc_hqx(body, 0xFFFF))
    (out_dir / "packet.bin").write_bytes(packet)
    (out_dir / "packet.hex").write_text(packet.hex() + "\n", encoding="ascii")

    limit = []
    if scope == "indirect":
        limit.append("这是手机拍屏展开后的**间接估计**，混合手机模型、屏幕缩放、摩尔纹与手动四角误差；"
                     "不能声明为 OV5640 原始像素高精度标定。")
    if scope == "synthetic":
        limit.append("这是合成数据，仅用于工具自检；不能写入比赛固件或写进报告当实测。")
    if scope == "phone":
        limit.append("这是手机内参，不是 OV5640 系数；只能用于拍屏展开。")
    if scope == "raw_digital":
        limit.append("这是原始数字帧标定；仍需检查采集分辨率、镜头/对焦是否一致，以及重投影 RMS 是否可信。")

    md = [
        "# 标定 → FPGA 系数报告",
        "",
        f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 输入标定：`{calib.get('_path', '')}`",
        f"- 输入 SHA-256：`{calib['_sha256']}`",
        f"- 来源声明：`{calib.get('source_kind_operator_declared')}`（工具未认证，仅记录）",
        f"- 接受范围：`{scope}`",
        f"- 图像尺寸：`{calib.get('image_size')}`，使用帧数：`{calib.get('frames_used')}`",
        f"- 重投影 RMS：`{calib.get('rms')}` px",
        "",
        "## 系数（Q16.16，有符号）",
        "",
        "| 名称 | 十进制 | 十六进制 |",
        "|---|---|---|",
    ]
    for key in FIELDS:
        md.append(f"| {key} | {signed[key]} | 0x{coeff[key]:08x} |")
    md += [
        "",
        "## 检查",
        "",
        f"- 64×64 窗口覆盖：`{'PASS' if geo.get('passed') else 'FAIL'}`，"
        f"valid={geo.get('valid_pixels')}，window_misses={geo.get('window_misses')}",
        f"- Q16 量化误差：max={qerr['max_px']:.4f}px，mean={qerr['mean_px']:.4f}px，"
        f"p95={qerr['p95_px']:.4f}px，阈值 {qerr['threshold_px']}px → "
        f"`{'PASS' if qerr['passed'] else 'WARN'}`",
        f"- UART 包：{len(packet)} 字节，seq={seq}，CRC16=0x{int.from_bytes(packet[-2:], 'big'):04x}",
        "",
        "## 限制",
        "",
    ]
    md += [f"- {x}" for x in limit]
    md += [
        "- 量化误差只说明 Q16 系数与浮点模型的差，不等于 RTL 全部算术误差；RTL 逐点比对见 `sim/results/`。",
        "- 若 `geometry_guard` 失败，先增大 zoom 或减小畸变/倾斜，不能强行下载。",
        "",
        "## 复现",
        "",
        "```powershell",
        f"python tools/calib_to_fpga.py --calib \"{calib.get('_path', '')}\" --out-dir \"{out_dir}\""
        + (" --allow-indirect" if scope == "indirect" else "")
        + (" --allow-synthetic" if scope == "synthetic" else "")
        + "```",
        "",
    ]
    (out_dir / "report.md").write_text("\n".join(md), encoding="utf-8")
    return coeff_json


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--calib", required=True, type=Path)
    ap.add_argument("--out-dir", type=Path, help="new output directory; default=calib_coeff_<timestamp>")
    ap.add_argument("--roll", type=float, default=0.0)
    ap.add_argument("--yaw", type=float, default=0.0, help="affine tilt approximation, not a homography")
    ap.add_argument("--pitch", type=float, default=0.0, help="affine tilt approximation")
    ap.add_argument("--zoom", type=float, default=1.0)
    ap.add_argument("--out-fx", type=float)
    ap.add_argument("--out-fy", type=float)
    ap.add_argument("--out-cx", type=float)
    ap.add_argument("--out-cy", type=float)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--sequence", type=int, default=1, help="UART sequence 1..255; 0 is reserved")
    ap.add_argument("--allow-indirect", action="store_true")
    ap.add_argument("--allow-synthetic", action="store_true")
    ap.add_argument("--allow-phone", action="store_true")
    ap.add_argument("--force", action="store_true", help="allow writing into an existing empty directory")
    args = ap.parse_args()

    if not (1 <= args.sequence <= 255):
        die("--sequence 必须在 1..255；0 与本地模式遥测冲突")
    if not all(math.isfinite(v) for v in (args.roll, args.yaw, args.pitch, args.zoom)) or args.zoom <= 0:
        die("角度必须有限，zoom 必须为正")

    calib, digest = load_calib(args.calib)
    calib["_path"] = str(args.calib)
    calib["_sequence"] = args.sequence
    scope = check_scope(calib, args.allow_indirect, args.allow_synthetic, args.allow_phone)
    if scope in ("raw_digital", "indirect") and list(calib.get("image_size", [])) != [args.width, args.height]:
        die(f"原始/间接标定必须是 {args.width}x{args.height}，当前 {calib.get('image_size')}")

    out = OutGeom(
        width=args.width, height=args.height,
        fx=calib["fx"] if args.out_fx is None else args.out_fx,
        fy=calib["fy"] if args.out_fy is None else args.out_fy,
        cx=calib["cx"] if args.out_cx is None else args.out_cx,
        cy=calib["cy"] if args.out_cy is None else args.out_cy,
    )
    wp = WarpParams(
        cam=CamParams(fx=calib["fx"], fy=calib["fy"], cx=calib["cx"], cy=calib["cy"],
                      k1=calib["k1"], k2=calib["k2"], p1=calib["p1"], p2=calib["p2"]),
        out=out, roll_deg=args.roll, yaw_deg=args.yaw, pitch_deg=args.pitch, zoom=args.zoom,
    )
    coeff = wp.coeffs()
    signed = {k: s32(v) for k, v in coeff.items()}

    for key in COEFF_18BIT:
        if not -131072 <= signed[key] < 131072:
            die(f"{key}={signed[key]} 超出 RTL 18bit 系数范围")
    for key in ("fx", "fy", "cx", "cy"):
        if not -(1 << 31) <= signed[key] < (1 << 31):
            die(f"{key} 超出 signed 32bit")

    try:
        geo = validate(signed, width=args.width, height=args.height)
    except ValueError as exc:
        die(f"几何窗口检查失败：{exc}")
    qerr = quantized_error(calib, coeff, out, roll=args.roll, yaw=args.yaw,
                           pitch=args.pitch, zoom=args.zoom)
    if not qerr["passed"]:
        print(f"WARNING: 量化误差 max={qerr['max_px']:.3f}px 超过 {qerr['threshold_px']}px", file=sys.stderr)

    out_dir = args.out_dir or Path(f"calib_coeff_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    if out_dir.exists():
        if not args.force or any(out_dir.iterdir()):
            die(f"输出目录已存在且非空：{out_dir}；换新目录或先清理")
    else:
        out_dir.mkdir(parents=True)

    write_outputs(calib, coeff, signed, out_dir, scope, geo, qerr, out,
                  args.roll, args.yaw, args.pitch, args.zoom)
    print(f"OK: {out_dir}")
    print("coeff:", {k: signed[k] for k in FIELDS})
    print("geometry:", geo)
    print("quantization:", qerr)
    print("packet:", (out_dir / "packet.hex").read_text(encoding="ascii").strip())


if __name__ == "__main__":
    main()
