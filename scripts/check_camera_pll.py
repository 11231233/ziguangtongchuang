#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_camera_pll.py — parse reg_config.v and verify the OV5640 PLL/PCLK math.

This guard exists because a previous 30fps trial edited the wrong register line:
it set 0x3035=0x69 instead of keeping 0x3035=0x21 and changing 0x3036=0x69.
The resulting PCLK was ~13.9MHz, not 84MHz, and the board showed a black screen.

Usage:
    python scripts/check_camera_pll.py
    python scripts/check_camera_pll.py --expect-pclk 84 --tolerance 1.0
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RTL = ROOT / "rtl/cam/reg_config.v"


def parse_regs(text: str) -> dict[int, int]:
    regs: dict[int, int] = {}
    for m in re.finditer(r"24'h([0-9a-fA-F]{4})([0-9a-fA-F]{2})", text):
        addr = int(m.group(1), 16)
        data = int(m.group(2), 16)
        # First write wins for PLL/HTS/VTS; later duplicates are mode switches.
        regs.setdefault(addr, data)
    return regs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", type=Path, default=RTL, help="register table to check")
    ap.add_argument("--expect-pclk", type=float, help="expected PCLK in MHz")
    ap.add_argument("--tolerance", type=float, default=1.0, help="MHz tolerance")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    regs = parse_regs(args.file.read_text(encoding="utf-8", errors="replace"))
    need = [0x3034, 0x3035, 0x3036, 0x3037, 0x3108, 0x380C, 0x380D, 0x380E, 0x380F]
    missing = [hex(x) for x in need if x not in regs]
    if missing:
        raise SystemExit("missing registers: " + ", ".join(missing))

    bit = regs[0x3034] & 0x0F
    bit_div2x = bit // 2 if bit in (8, 10) else 1
    sys_div = regs[0x3035] >> 4 or 16
    mult = regs[0x3036]
    prediv = regs[0x3037] & 0x0F
    pll_rdiv = ((regs[0x3037] >> 4) & 1) + 1
    sclk_div = [1, 2, 4, 8][regs[0x3108] & 0x03]
    hts = (regs[0x380C] << 8) | regs[0x380D]
    vts = (regs[0x380E] << 8) | regs[0x380F]

    errors = []
    if prediv not in (1, 2, 3, 4, 6, 8):
        errors.append("invalid PLL pre-divider %d" % prediv)
    if not 4 <= mult <= 252:
        errors.append("PLL multiplier %d out of 4..252" % mult)
    if hts <= 0 or vts <= 0:
        errors.append("invalid HTS/VTS")

    vco = 24.0 * mult / prediv
    # OV5640_get_sysclk() returns the internal sysclk; the DVP PCLK is 2x that
    # value for this mode. The 41.6MHz measured on the stable build confirms it.
    sysclk = vco / sys_div / pll_rdiv * 2 / bit_div2x / sclk_div
    pclk = sysclk * 2
    fps = pclk * 1e6 / (2 * hts * vts) if hts and vts else 0.0

    result = {
        "bit_div2x": bit_div2x,
        "sys_div": sys_div,
        "multiplier": mult,
        "pre_divider": prediv,
        "pll_rdiv": pll_rdiv,
        "sclk_div": sclk_div,
        "hts": hts,
        "vts": vts,
        "vco_mhz": round(vco, 3),
        "pclk_mhz": round(pclk, 3),
        "fps": round(fps, 3),
        "expected_pclk_mhz": args.expect_pclk,
        "errors": errors,
    }

    if args.expect_pclk is not None and abs(pclk - args.expect_pclk) > args.tolerance:
        errors.append("PCLK %.3fMHz != expected %.3f+/-%.3f" %
                      (pclk, args.expect_pclk, args.tolerance))
    # A black-screen guard: PCLK must be a plausible DVP clock and the frame rate positive.
    if not 8.0 <= pclk <= 96.0:
        errors.append("PCLK %.3fMHz outside plausible DVP range 8..96MHz" % pclk)
    if not 1.0 <= fps <= 120.0:
        errors.append("frame rate %.3f outside 1..120fps" % fps)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("0x3035=0x%02x 0x3036=0x%02x 0x3037=0x%02x 0x3108=0x%02x 0x3034=0x%02x" %
              (regs[0x3035], regs[0x3036], regs[0x3037], regs[0x3108], regs[0x3034]))
        print("HTS=%d VTS=%d  PCLK=%.3fMHz  fps=%.3f" % (hts, vts, pclk, fps))
    if errors:
        print("CAMERA_PLL FAIL: " + "; ".join(errors))
        raise SystemExit(1)
    print("CAMERA_PLL PASS: PCLK=%.1fMHz, fps=%.1f" % (pclk, fps))


if __name__ == "__main__":
    main()
