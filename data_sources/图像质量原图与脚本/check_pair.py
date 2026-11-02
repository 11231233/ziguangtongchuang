"""校验 RAW/COR 两张是不是同一姿态，能不能做 MTF 对比。

两张图里棋盘的大小、倾斜、位置只要有一个变了，MTF 的差别就来自摆位而不是校正，
对比就作废。这个脚本把三条都量出来并给结论。

    python check_pair.py --a raw.png --b cor.png
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import cv2
import numpy as np

TOL_SQUARE_PX = 6.5   # ~10%；放大倍率差由 pair_mtf 归一化掉，但距离变化仍会改变离焦
TOL_TILT_DEG = 3.0
TOL_BBOX_PX = 45.0  # 位置允许漂移，ROI 跟着棋盘走


def read_image(path: Path):
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_GRAYSCALE) if data.size else None


def board(gray: np.ndarray, pattern: str):
    for pat in (pattern, "x".join(pattern.split("x")[::-1])):
        cols, rows = [int(v) for v in pat.split("x")]
        ok, corners = cv2.findChessboardCorners(
            gray, (cols, rows),
            cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE)
        if not ok:
            continue
        corners = cv2.cornerSubPix(gray, corners, (5, 5), (-1, -1),
                                   (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.01))
        grid = corners.reshape(rows, cols, 2)
        dx = np.linalg.norm(np.diff(grid, axis=1), axis=2)
        dy = np.linalg.norm(np.diff(grid, axis=0), axis=2)
        vec = grid[0, -1] - grid[0, 0]
        tilt = ((math.degrees(math.atan2(vec[1], vec[0])) + 45.0) % 90.0) - 45.0
        xs, ys = grid[:, :, 0].ravel(), grid[:, :, 1].ravel()
        return dict(square=float(np.median(np.concatenate([dx.ravel(), dy.ravel()]))),
                    tilt=float(tilt),
                    bbox=(xs.min(), ys.min(), xs.max(), ys.max()),
                    grid=grid)
    raise SystemExit(f"没检出棋盘格（{pattern}）")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--a", type=Path, required=True, help="第一张（通常 RAW）")
    ap.add_argument("--b", type=Path, required=True, help="第二张（通常 COR）")
    ap.add_argument("--pattern", default="6x9")
    a = ap.parse_args(argv)

    ga, gb = read_image(a.a), read_image(a.b)
    if ga is None or gb is None:
        raise SystemExit("读图失败")
    A = board(ga, a.pattern)
    B = board(gb, a.pattern)

    print(f"{'':<10}{'A':>22}{'B':>14}{'差':>10}")
    print(f"{'格子 px':<10}{A['square']:>22.2f}{B['square']:>14.2f}"
          f"{abs(A['square']-B['square']):>10.2f}")
    print(f"{'倾斜 °':<10}{A['tilt']:>22.2f}{B['tilt']:>14.2f}"
          f"{abs(A['tilt']-B['tilt']):>10.2f}")
    for i, nm in enumerate(("x0", "y0", "x1", "y1")):
        print(f"{nm:<10}{A['bbox'][i]:>22.1f}{B['bbox'][i]:>14.1f}"
              f"{abs(A['bbox'][i]-B['bbox'][i]):>10.1f}")

    d_sq = abs(A["square"] - B["square"])
    d_ti = abs(A["tilt"] - B["tilt"])
    d_bb = max(abs(A["bbox"][i] - B["bbox"][i]) for i in range(4))
    # sub-pixel corner shift between the two shots: the grid itself is the best witness
    d_grid = float(np.median(np.linalg.norm(A["grid"] - B["grid"], axis=2)))
    print(f"\n角点平均位移 {d_grid:.2f} px")

    ok = d_sq <= TOL_SQUARE_PX and d_ti <= TOL_TILT_DEG and d_bb <= TOL_BBOX_PX
    print(f"\n判据  格子 <= {TOL_SQUARE_PX} px（可用 pair_mtf 归一化）, 倾斜 <= {TOL_TILT_DEG}°, 范围 <= {TOL_BBOX_PX} px")
    print("结论:", "两张姿态一致，可以做 MTF 对比" if ok
          else "两张姿态不一致，MTF 对比无效；固定棋盘后重拍")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())