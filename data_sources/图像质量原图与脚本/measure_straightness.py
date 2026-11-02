"""从同一对 RAW/COR 帧测格线直线度，结果落盘作为报告引用。

方法：棋盘格的内角点在物理上排成直线。对每一行、每一列角点各拟合一条直线，
取该行/列所有角点到直线的垂距 RMS；最后对各行各列取中位数。
这个量与棋盘在画面里的朝向无关，所以不需要先把棋盘摆正。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

OUT = Path(r"F:\ziguang_jibian\mtf")
FRAMES = {"raw": Path(r"F:\ziguang_jibian\A_first.png"),
          "cor": Path(r"F:\ziguang_jibian\B_second.png")}
PATTERN = (6, 9)


def grid(path: Path):
    gray = np.fromfile(str(path), dtype=np.uint8)
    gray = cv2.imdecode(gray, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise SystemExit(f"读不到 {path}")
    for pat in (PATTERN, PATTERN[::-1]):
        ok, c = cv2.findChessboardCorners(
            gray, pat, cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE)
        if not ok:
            continue
        c = cv2.cornerSubPix(gray, c, (5, 5), (-1, -1),
                             (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.01))
        return c.reshape(pat[1], pat[0], 2), pat
    raise SystemExit(f"{path} 检不到棋盘格")


def deviations(g: np.ndarray):
    """返回每一行、每一列的垂距 RMS 与最大垂距。"""
    rows, cols = [], []
    for r in g:                                   # 每个"行"是一组共线角点
        p = r.astype(np.float64)
        direction = p[-1] - p[0]
        n = np.array([-direction[1], direction[0]])
        n /= np.linalg.norm(n)
        d = np.abs((p - p[0]) @ n)
        rows.append((float(np.sqrt((d ** 2).mean())), float(d.max())))
    for c in g.transpose(1, 0, 2):
        p = c.astype(np.float64)
        direction = p[-1] - p[0]
        n = np.array([-direction[1], direction[0]])
        n /= np.linalg.norm(n)
        d = np.abs((p - p[0]) @ n)
        cols.append((float(np.sqrt((d ** 2).mean())), float(d.max())))
    return rows, cols


def main() -> int:
    result = {}
    for name, path in FRAMES.items():
        g, pat = grid(path)
        rows, cols = deviations(g)
        allr = [v[0] for v in rows + cols]
        result[name] = dict(
            frame=str(path),
            pattern=list(pat),
            line_rms_median_px=round(float(np.median(allr)), 3),
            line_rms_max_px=round(float(np.max(allr)), 3),
            point_dev_max_px=round(float(max(v[1] for v in rows + cols)), 3),
            per_line_rms_px=[round(v[0], 3) for v in rows + cols],
        )
        print(f"{name:<4} 格线偏离直线：中位 {result[name]['line_rms_median_px']:.3f} px，"
              f"最大 {result[name]['line_rms_max_px']:.3f} px，"
              f"单点最大 {result[name]['point_dev_max_px']:.3f} px  ({pat[1]}×{pat[0]} 角点)")

    a = result["raw"]["line_rms_median_px"]
    b = result["cor"]["line_rms_median_px"]
    result["improvement"] = dict(
        raw=a, cor=b,
        ratio=round(a / b, 2) if b else None,
        note="同一对帧、同一组格线，仅 KEY0 切换 RAW/COR",
    )
    print(f"\n直线度 {a:.3f} → {b:.3f} px，改善 {a / b:.1f} 倍" if b else "")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "straightness.json").write_text(json.dumps(result, indent=2, ensure_ascii=False),
                                           encoding="utf-8")
    print(f"已写入 {OUT / 'straightness.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())