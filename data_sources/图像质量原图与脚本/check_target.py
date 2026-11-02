"""量一下靶纸在画面里够不够大、够不够斜。

MTF 斜边法要 48x48 的 ROI，所以每个格子至少要 60 px，边界还要斜 5~10°。
这个脚本直接给数，不靠估。

    python check_target.py --image shot.png
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import cv2
import numpy as np


def read_image(path: Path):
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_GRAYSCALE) if data.size else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", type=Path, required=True)
    ap.add_argument("--pattern", default="6x9", help="inner corners, e.g. 6x9 or 9x6")
    ap.add_argument("--need", type=float, default=60.0, help="minimum square size in px")
    a = ap.parse_args(argv)

    gray = read_image(a.image)
    if gray is None:
        raise SystemExit(f"cannot read {a.image}")
    h, w = gray.shape
    print(f"图像 {w}x{h}")

    found = None
    for pat in (a.pattern, "x".join(a.pattern.split("x")[::-1])):
        cols, rows = [int(v) for v in pat.split("x")]
        ok, corners = cv2.findChessboardCorners(
            gray, (cols, rows),
            cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE | cv2.CALIB_CB_FAST_CHECK)
        if ok:
            corners = cv2.cornerSubPix(
                gray, corners, (5, 5), (-1, -1),
                (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.01))
            found = (pat, cols, rows, corners.reshape(rows, cols, 2))
            break
    if found is None:
        raise SystemExit("没找到棋盘格；确认整块棋盘都在画面里、对焦清楚")

    pat, cols, rows, grid = found
    print(f"检出内角点 {pat}  ({cols} 列 x {rows} 行)")

    # square size in px along each axis
    dx = np.linalg.norm(np.diff(grid, axis=1), axis=2)
    dy = np.linalg.norm(np.diff(grid, axis=0), axis=2)
    sx, sy = float(np.median(dx)), float(np.median(dy))
    print(f"格子尺寸  横向 {sx:.1f} px   纵向 {sy:.1f} px")

    # tilt of the grid, from the top row of corners
    vec = grid[0, -1] - grid[0, 0]
    raw_tilt = math.degrees(math.atan2(vec[1], vec[0]))
    # The board is often held rotated by 90 degrees, so the corner "row" can follow the
    # board's long axis and report ~+-90. Only the deviation from axis-aligned matters
    # for a slanted edge, so fold it into [-45, 45).
    tilt = ((raw_tilt + 45.0) % 90.0) - 45.0
    print(f"棋盘倾斜  {tilt:+.1f}°  （相对水平，已折算 90° 基准；原始量测 {raw_tilt:+.1f}°）")

    xs, ys = grid[:, :, 0].ravel(), grid[:, :, 1].ravel()
    bx0, bx1, by0, by1 = xs.min(), xs.max(), ys.min(), ys.max()
    print(f"棋盘范围  x {bx0:.0f}..{bx1:.0f}   y {by0:.0f}..{by1:.0f}   "
          f"({(bx1-bx0)/(w-1)*100:.0f}% x {(by1-by0)/(h-1)*100:.0f}% 画面)")

    print()
    ok_size = min(sx, sy) >= a.need
    # slanted-edge needs roughly 5..12 degrees; too much and the ESF spans too many rows
    ok_tilt = 5.0 <= abs(tilt) <= 12.0
    print(f"格子大小  {min(sx, sy):.1f} px  需要 >= {a.need:.0f} px   "
          f"{'够' if ok_size else '不够'}")
    print(f"倾斜角    {abs(tilt):.1f}°  需要 5~12°             {'够' if ok_tilt else '不够'}")
    if not ok_size:
        print(f"\n建议靠近约 {a.need / max(min(sx, sy), 1e-6):.1f} 倍，"
              f"让格子到 {a.need:.0f} px 以上")
    if not ok_tilt:
        print("\n建议把棋盘再转一点（目标 7° 左右）")
    print("\n结论:", "可以拍" if (ok_size and ok_tilt) else "先按上面的建议调整再拍")
    return 0 if (ok_size and ok_tilt) else 1


if __name__ == "__main__":
    raise SystemExit(main())