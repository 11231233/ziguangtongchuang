"""RAW/COR 两张图的 MTF 对比，用"每格多少周期"归一化掉放大倍率差异。

为什么归一化
    畸变校正本身就改变局部放大率，手举靶纸也难免前后移动几厘米，于是同一块棋盘在
    两张图里的像素尺寸会差几个百分点。直接比 cycles/pixel 会把这点放大率差算进去。
    棋盘每格的物理尺寸是恒定的，所以

        每格周期数 = MTF50(cycles/pixel) x 格子像素数

    与放大率无关，才是可以横向比较的量。

    python pair_mtf.py --a RAW.png --b COR.png
"""
from __future__ import annotations

import argparse
import statistics as st
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mtf_edge import analyze, board_edge_rois, imread_unicode  # noqa: E402


def square_px(gray: np.ndarray, pattern: str) -> float | None:
    for pat in (pattern, "x".join(pattern.split("x")[::-1])):
        cols, rows = [int(v) for v in pat.split("x")]
        ok, c = cv2.findChessboardCorners(
            gray, (cols, rows), cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE)
        if ok:
            c = cv2.cornerSubPix(gray, c, (5, 5), (-1, -1),
                                 (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.01))
            g = c.reshape(rows, cols, 2)
            d = np.concatenate([np.linalg.norm(np.diff(g, axis=1), axis=2).ravel(),
                                np.linalg.norm(np.diff(g, axis=0), axis=2).ravel()])
            return float(np.median(d))
    return None


def measure(path: Path, pattern: str, size: int) -> dict:
    gray = imread_unicode(path)
    if gray is None:
        raise SystemExit(f"读图失败: {path}")
    sq = square_px(gray, pattern)
    rois = board_edge_rois(gray, pattern, size=size)
    vals, per_square = [], []
    for roi in rois:
        try:
            res, *_ = analyze(gray, roi)
        except ValueError:
            continue
        if not (res["mtf50_resolved"] and res.get("edge_line_rms_px", 99) <= 0.5
                and res.get("esf_monotonicity", 0) >= 0.85):
            continue
        vals.append(res["mtf50"])
        if sq:
            per_square.append(res["mtf50"] * sq)
    return dict(path=path, square=sq, rois=len(rois), good=len(vals),
                mtf50=vals, per_square=per_square)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--a", type=Path, required=True)
    ap.add_argument("--b", type=Path, required=True)
    ap.add_argument("--pattern", default="6x9")
    ap.add_argument("--size", type=int, default=40)
    a = ap.parse_args(argv)

    A = measure(a.a, a.pattern, a.size)
    B = measure(a.b, a.pattern, a.size)

    print(f"{'':<16}{'A':>18}{'B':>18}")
    print(f"{'文件':<16}{A['path'].name:>18}{B['path'].name:>18}")
    print(f"{'格子 px':<16}{(A['square'] or 0):>18.2f}{(B['square'] or 0):>18.2f}")
    print(f"{'可信样本':<16}{A['good']:>14}/{A['rois']}{B['good']:>14}/{B['rois']}")
    if not A["mtf50"] or not B["mtf50"]:
        print("\n至少一张没有可信样本，无法对比")
        return 1
    print(f"{'MTF50 中位':<16}{st.median(A['mtf50']):>18.3f}{st.median(B['mtf50']):>18.3f}")
    print(f"{'MTF50 范围':<16}{min(A['mtf50']):>8.3f}~{max(A['mtf50']):<9.3f}"
          f"{min(B['mtf50']):>8.3f}~{max(B['mtf50']):<9.3f}")
    if A["per_square"] and B["per_square"]:
        ma, mb = st.median(A["per_square"]), st.median(B["per_square"])
        print(f"{'每格周期数':<16}{ma:>18.3f}{mb:>18.3f}")
        print(f"\n归一化后变化 {(mb - ma) / ma * 100:+.1f}%")
    d = (st.median(B["mtf50"]) - st.median(A["mtf50"])) / st.median(A["mtf50"]) * 100
    print(f"未归一化变化 {d:+.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())