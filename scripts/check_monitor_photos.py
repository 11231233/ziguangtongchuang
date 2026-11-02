#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Preflight checker for stage-2 monitor RAW photos.

Checks:
  - every image has the same size as the phone calibration (default 1280x1707);
  - a 6x9 checkerboard is detected.

It cannot verify that all four monitor corners are visible; that is a manual check.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, type=Path)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=1707)
    ap.add_argument("--cols", type=int, default=6)
    ap.add_argument("--rows", type=int, default=9)
    a = ap.parse_args()

    files = sorted([p for p in a.dir.iterdir()
                    if p.suffix.lower() in (".jpg", ".jpeg", ".png")])
    if not files:
        raise SystemExit("no images in " + str(a.dir))

    ok = True
    for f in files:
        img = cv2.imdecode(np.fromfile(str(f), dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            print(f"FAIL  {f.name}: unreadable")
            ok = False
            continue
        h, w = img.shape[:2]
        size_ok = (w == a.width and h == a.height)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        found, corners = cv2.findChessboardCorners(
            gray, (a.cols, a.rows),
            cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE)
        detail = []
        if not size_ok:
            detail.append(f"size {w}x{h} != {a.width}x{a.height}")
        if not found:
            detail.append(f"no {a.cols}x{a.rows} board")
        print(("PASS  " if size_ok and found else "FAIL  ") + f.name + "  " + "; ".join(detail))
        if not (size_ok and found):
            ok = False

    print()
    print("RESULT:", "PASS" if ok else "FAIL")
    print("Manual check still required: all four monitor screen corners must be visible.")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
