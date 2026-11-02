"""斜边法测 MTF50 / SFR（ISO 12233），用于评估畸变矫正前后的清晰度。

原理
    一条倾斜 5～10° 的黑白边界，在每一行上的亚像素位置都不同。把整条边界上的
    像素按"到边界的垂距"重采样，就得到比 1 像素更细的阶梯响应 ESF；对 ESF 求导得
    线扩散函数 LSF；对 LSF 做 FFT 得 MTF 曲线；MTF 降到 0.5 的频率就是 MTF50。

为什么必须斜
    正对着拍，边界只落在整数像素上，采样率就是 1 px，分辨率太粗。倾斜后同一条边
    在每行的亚像素相位不同，等于用整条边界换来 4～8 倍过采样——这是斜边法的核心。

参数单位
    MTF50 单位是 cycles/pixel。0.5 是奈奎斯特上限；1.0 表示在奈奎斯特处仍有全对比度，
    数值越大越锐。换算成 lp/mm 需要传感器像元尺寸，本脚本不猜，只给可复现的归一化值。

用法
    python mtf_edge.py --image a.png --auto --label RAW_center
    python mtf_edge.py --image b.png --roi 560,300,660,400 --label COR_center
    python mtf_edge.py --selftest
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np

OUT_DEFAULT = Path(r"F:\ziguang_jibian\mtf")


def imread_unicode(path: Path):
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)


def structure_angle(patch: np.ndarray) -> tuple[float, float]:
    """Return (nx, ny) unit normal of the dominant edge, from the gradient tensor."""
    gx = cv2.Sobel(patch, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(patch, cv2.CV_64F, 0, 1, ksize=3)
    sxx, syy, sxy = float((gx * gx).sum()), float((gy * gy).sum()), float((gx * gy).sum())
    theta = 0.5 * math.atan2(2.0 * sxy, sxx - syy)      # principal gradient direction
    return math.cos(theta), math.sin(theta)


def build_esf(patch: np.ndarray, nx: float, ny: float, oversample: int):
    h, w = patch.shape
    yy, xx = np.mgrid[0:h, 0:w]
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    d = (xx - cx) * nx + (yy - cy) * ny
    lo, hi = np.percentile(d, [1, 99])
    span = hi - lo
    if span < 6.0:
        raise ValueError("edge span too small; widen the ROI")
    nbins = max(16, int(round(span * oversample)))
    idx = np.clip(((d - lo) / span * (nbins - 1)).astype(int), 0, nbins - 1)
    ssum = np.bincount(idx.ravel(), weights=patch.ravel(), minlength=nbins)
    cnt = np.bincount(idx.ravel(), minlength=nbins).astype(float)
    good = cnt > 0
    if good.sum() < nbins * 0.8:
        raise ValueError("too few samples per bin; enlarge the ROI")
    esf = np.interp(np.arange(nbins), np.where(good)[0], ssum[good] / cnt[good])
    bin_px = span / (nbins - 1)          # pixel distance between bins
    return esf, bin_px, nbins


def mtf_from_esf(esf: np.ndarray, bin_px: float, half_px: float = 12.0, pad: int = 1024):
    lsf = np.diff(esf)
    w = np.maximum(lsf, 0)
    if w.sum() <= 1e-9:
        raise ValueError("degenerate edge (no contrast)")
    c = int(round((np.arange(lsf.size) * w).sum() / w.sum()))
    # Keep the DC of the LSF: that is the edge contrast, and it is the reference that
    # makes MTF(0)=1. Subtracting the mean (an earlier version did) throws the reference
    # away and inflates every MTF50 by roughly 1.5x — verified against analytic Gaussians.
    # The window must be wide enough not to truncate the diffusion: 12 px covers sigma up
    # to ~3 px, which is already outside what this camera produces.
    half = max(6, int(round(half_px / bin_px)))
    lo, hi = max(0, c - half), min(lsf.size, c + half)
    seg = lsf[lo:hi].astype(np.float64)
    seg = seg * np.hamming(seg.size)
    n = max(pad, seg.size)
    spec = np.abs(np.fft.rfft(seg, n=n))
    if spec[0] <= 0:
        raise ValueError("degenerate edge (no contrast)")
    mtf = spec / spec[0]
    freq = np.fft.rfftfreq(n, d=bin_px)              # cycles / pixel
    return freq, mtf


def cross(freq: np.ndarray, mtf: np.ndarray, level: float) -> float | None:
    below = np.where(mtf <= level)[0]
    if below.size == 0:
        return None
    i = int(below[0])
    if i == 0:
        return float(freq[0])
    f0, f1 = freq[i - 1], freq[i]
    m0, m1 = mtf[i - 1], mtf[i]
    if m0 == m1:
        return float(f1)
    return float(f0 + (m0 - level) * (f1 - f0) / (m0 - m1))


def draw(name: str, patch: np.ndarray, nx: float, ny: float, esf, bin_px, freq, mtf, res, out: Path):
    h, w = patch.shape
    canvas = np.zeros((260, max(760, w * 2 + 20), 3), np.uint8)
    p = cv2.cvtColor(patch.astype(np.uint8), cv2.COLOR_GRAY2BGR)
    canvas[0:h, 0:w] = p
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    t = 200
    cv2.line(canvas, (int(cx - nx * t), int(cy - ny * t)), (int(cx + nx * t), int(cy + ny * t)),
             (0, 255, 0), 1)
    # ESF (normalised)
    ex0, ey0, ew, eh = w + 20, 10, canvas.shape[1] - w - 40, 110
    e = (esf - esf.min()) / max(esf.max() - esf.min(), 1e-9)
    for i in range(1, e.size):
        cv2.line(canvas, (int(ex0 + (i - 1) / e.size * ew), int(ey0 + eh - e[i - 1] * eh)),
                 (int(ex0 + i / e.size * ew), int(ey0 + eh - e[i] * eh)), (255, 200, 0), 1)
    cv2.putText(canvas, "ESF", (ex0, ey0 - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 200, 0), 1)
    # MTF vs freq
    mx0, my0, mw, mh = w + 20, 140, ew, 110
    cv2.rectangle(canvas, (mx0, my0), (mx0 + mw, my0 + mh), (60, 60, 60), 1)
    fmax = 0.55
    for i in range(1, mtf.size):
        if freq[i] > fmax:
            break
        cv2.line(canvas,
                 (int(mx0 + freq[i - 1] / fmax * mw), int(my0 + mh - min(mtf[i - 1], 1) * mh)),
                 (int(mx0 + freq[i] / fmax * mw), int(my0 + mh - min(mtf[i], 1) * mh)),
                 (0, 255, 255), 1)
    cv2.line(canvas, (mx0, int(my0 + mh * 0.5)), (mx0 + mw, int(my0 + mh * 0.5)), (90, 90, 90), 1)
    if res.get("mtf50") is not None:
        x = int(mx0 + min(res["mtf50"], fmax) / fmax * mw)
        cv2.line(canvas, (x, my0), (x, my0 + mh), (0, 160, 255), 1)
    cv2.putText(canvas, f"MTF50 {res['mtf50']:.3f} cyc/px" if res.get("mtf50") is not None else "MTF50 n/a",
                (mx0, my0 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 255), 1)
    cv2.putText(canvas, name, (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
    ok, buf = cv2.imencode(".png", canvas)
    out.write_bytes(buf.tobytes())


def refine_edge(patch: np.ndarray, nx: float, ny: float) -> tuple[float, float, float]:
    """Sub-pixel refine the edge line: centroid the gradient inside each row, then fit.

    The structure tensor alone localises the edge to about 0.3 px, which is coarse
    enough to smear the ESF of a near-Nyquist edge. Centroiding the gradient per row is
    sub-pixel and drops that error by an order of magnitude.
    """
    gx = cv2.Sobel(patch, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(patch, cv2.CV_64F, 0, 1, ksize=3)
    gm = np.hypot(gx, gy)
    h, w = gm.shape
    xs = np.arange(w, dtype=np.float64)
    rows, cols = [], []
    for r in range(2, h - 2):
        prof = gm[r]
        s = prof.sum()
        if s <= 1e-9 or prof.max() < gm.max() * 0.25:
            continue
        rows.append(r)
        cols.append(float((xs * prof).sum() / s))
    if len(rows) < max(8, h // 5):
        return nx, ny, 0.0
    rows = np.asarray(rows)
    cols = np.asarray(cols)
    a, b = np.polyfit(rows, cols, 1)
    resid = cols - (a * rows + b)
    rms = float(np.sqrt(np.mean(resid ** 2)))
    # The fitted line is x = a*y + b, i.e. x - a*y - b = 0, so the normal in (x, y) is
    # (1, -a). Writing it as (-a, 1) swaps the axes and produces a smeared ESF.
    n = np.array([1.0, -a])
    n /= np.hypot(*n)
    # keep the same hemisphere as the coarse estimate so the ESF does not invert
    if n[0] * nx + n[1] * ny < 0:
        n = -n
    return float(n[0]), float(n[1]), rms


def esf_monotonicity(esf: np.ndarray) -> float:
    """Fraction of significant ESF steps that move the same way as the overall edge.

    A clean slanted edge gives a monotone step. If the ROI also contains a second edge
    (a checkerboard corner instead of the middle of one side), the ESF wiggles back and
    forth and the MTF is meaningless even though the fitted edge line still looks good.
    """
    span = esf.max() - esf.min()
    if span <= 0:
        return 0.0
    sgn = 1.0 if esf[-1] > esf[0] else -1.0
    dd = np.diff(esf) * sgn
    core = dd[np.abs(dd) > 0.02 * span]
    if core.size == 0:
        return 0.0
    return float((core > 0).mean())


def analyze(gray: np.ndarray, roi, oversample=4):
    x0, y0, x1, y1 = roi
    patch = gray[y0:y1, x0:x1].astype(np.float64)
    if patch.size < 32 * 32:
        raise ValueError("ROI too small; use at least 48x48 px")
    nx, ny = structure_angle(patch)
    nx, ny, straight = refine_edge(patch, nx, ny)
    esf, bin_px, nbins = build_esf(patch, nx, ny, oversample)
    freq, mtf = mtf_from_esf(esf, bin_px)
    f50 = cross(freq, mtf, 0.5)
    # 4x oversampling resolves down to about sigma=0.6 px. A sharper edge never reaches
    # MTF=0.5 below Nyquist; reporting the extrapolated crossing would be a fabricated
    # number, so say "not resolvable" instead.
    resolved = f50 is not None and f50 <= 0.5
    res = dict(
        roi=[int(x0), int(y0), int(x1), int(y1)],
        edge_normal=[round(nx, 4), round(ny, 4)],
        edge_angle_deg=round(math.degrees(math.atan2(ny, nx)), 2),
        contrast=float(esf.max() - esf.min()),
        mtf50=round(f50, 4) if resolved else None,
        mtf30=cross(freq, mtf, 0.3) if resolved else None,
        mtf10=cross(freq, mtf, 0.1) if resolved else None,
        mtf50_resolved=bool(resolved),
        mtf50_note="" if resolved else "边缘比 4x 斜边法可分辨的更锐（低于约 0.6 px），本方法给不出可信值",
        esf_bins=int(nbins),
        esf_monotonicity=round(esf_monotonicity(esf), 3),
        bin_px=round(bin_px, 4),
        nyquist=0.5,
        edge_line_rms_px=round(straight, 3),
    )
    return res, patch, nx, ny, esf, bin_px, freq, mtf


def board_edge_rois(gray: np.ndarray, pattern: str, size: int = 40) -> list:
    """ROIs centred on the midpoint of real checkerboard square edges.

    In a checkerboard every inner corner is shared by four squares, so the segment
    between two neighbouring inner corners IS one square edge, one square long. Its
    midpoint is the ideal place for a slanted-edge window: the edge runs through the
    centre and the window stays inside the segment, away from the corners that would
    otherwise put a second edge in the window.
    """
    found = None
    for pat in (pattern, "x".join(pattern.split("x")[::-1])):
        cols, rows = [int(v) for v in pat.split("x")]
        ok, corners = cv2.findChessboardCorners(
            gray, (cols, rows),
            cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE)
        if ok:
            corners = cv2.cornerSubPix(gray, corners, (5, 5), (-1, -1),
                                       (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.01))
            found = (cols, rows, corners.reshape(rows, cols, 2))
            break
    if found is None:
        return []
    cols, rows, grid = found
    h, w = gray.shape
    half = size // 2
    mids = []
    for i in range(rows):
        for j in range(cols - 1):                       # horizontal neighbours
            m = (grid[i, j] + grid[i, j + 1]) / 2.0
            mids.append((m[0], m[1]))
    for i in range(rows - 1):
        for j in range(cols):                            # vertical neighbours
            m = (grid[i, j] + grid[i + 1, j]) / 2.0
            mids.append((m[0], m[1]))
    rois = []
    for mx, my in mids:
        x0, y0 = int(round(mx)) - half, int(round(my)) - half
        x1, y1 = x0 + size, y0 + size
        if x0 < 0 or y0 < 0 or x1 > w or y1 > h:
            continue
        rois.append((x0, y0, x1, y1))
    return rois


def auto_roi(gray: np.ndarray, size: int = 48, want: int = 6) -> list:
    """Rank small blocks by edge strength x anisotropy.

    The window is deliberately small. On a wide-angle source the straight world lines are
    curved in the image, so a large ROI averages several edge angles and the ESF smears;
    a 48 px window keeps the curvature inside the block below a pixel.
    """
    h, w = gray.shape
    cands = []
    step = max(8, size // 4)
    for y in range(0, h - size, step):
        for x in range(0, w - size, step):
            blk = gray[y:y + size, x:x + size].astype(np.float32)
            gx = cv2.Sobel(blk, cv2.CV_32F, 1, 0, ksize=3)
            gy = cv2.Sobel(blk, cv2.CV_32F, 0, 1, ksize=3)
            sxx, syy, sxy = (gx * gx).sum(), (gy * gy).sum(), (gx * gy).sum()
            tr = sxx + syy
            if tr <= 0:
                continue
            aniso = math.hypot(sxx - syy, 2 * sxy) / tr      # 1.0 = perfectly straight edge
            if float(aniso) > 0.55:
                cands.append((float(aniso) * math.sqrt(float(tr)), x, y))
    cands.sort(reverse=True)
    picked, used = [], []
    for score, x, y in cands:
        if any(abs(x - px) < size and abs(y - py) < size for px, py in used):
            continue
        used.append((x, y))
        picked.append((x, y, x + size, y + size))
        if len(picked) >= want:
            break
    return picked


def selftest() -> int:
    """Validate against analytic Gaussians: MTF50 = sqrt(ln2/(2*pi^2*sigma^2)).

    The method is specified for sigma >= 0.6 px; below that the 4x slanted-edge
    reconstruction cannot resolve the edge and the script reports "not resolved"
    rather than inventing a number, so a sharper case is checked for that behaviour.
    """
    ok_all = True
    for sigma in (0.7, 1.0, 1.6):
        h, w = 200, 200
        yy, xx = np.mgrid[0:h, 0:w]
        ang = math.radians(7.0)
        d = (xx - w / 2) * math.cos(ang) + (yy - h / 2) * math.sin(ang)
        img = np.where(d < 0, 30.0, 220.0)
        img = cv2.GaussianBlur(img, (0, 0), sigma)
        img = np.clip(img, 0, 255).astype(np.uint8)
        res, *_ = analyze(img, (40, 40, 160, 160))
        expect = math.sqrt(math.log(2.0) / (2 * math.pi ** 2 * sigma ** 2))
        got = res["mtf50"]
        err = abs(got - expect) / expect * 100 if got else 999.0
        ok = res["mtf50_resolved"] and err < 8.0
        ok_all &= ok
        print(f"  sigma={sigma:.1f}px  期望 MTF50={expect:.3f}  实测 {got if got else float('nan'):.3f}"
              f"  误差 {err:.1f}%  {'OK' if ok else 'FAIL'}  直边度 {res.get('edge_line_rms_px')} px")
    # beyond the resolvable limit the script must refuse, not fabricate
    h, w = 200, 200
    yy, xx = np.mgrid[0:h, 0:w]
    ang = math.radians(7.0)
    d = (xx - w / 2) * math.cos(ang) + (yy - h / 2) * math.sin(ang)
    img = cv2.GaussianBlur(np.where(d < 0, 30.0, 220.0), (0, 0), 0.5)
    res, *_ = analyze(np.clip(img, 0, 255).astype(np.uint8), (40, 40, 160, 160))
    refuse_ok = res["mtf50"] is None and not res["mtf50_resolved"]
    ok_all &= refuse_ok
    print(f"  sigma=0.5px  超出可分辨范围 -> {res['mtf50_note']}  {'OK' if refuse_ok else 'FAIL'}")
    print("selftest:", "PASS" if ok_all else "FAIL")
    return 0 if ok_all else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", type=Path)
    ap.add_argument("--roi", action="append",
                    help="x0,y0,x1,y1  (repeatable)")
    ap.add_argument("--auto", action="store_true", help="auto-pick the strongest straight edge")
    ap.add_argument("--pattern", default="6x9", help="checkerboard inner corners, e.g. 6x9")
    ap.add_argument("--size", type=int, default=40,
                    help="ROI side in px when locating edges from the checkerboard")
    ap.add_argument("--label", default="")
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)

    if a.selftest:
        return selftest()
    if not a.image:
        raise SystemExit("--image required (or --selftest)")

    gray = imread_unicode(a.image)
    if gray is None:
        raise SystemExit(f"cannot read {a.image}")
    rois = []
    for r in (a.roi or []):
        x0, y0, x1, y1 = [int(v) for v in r.split(",")]
        rois.append((x0, y0, x1, y1))
    if a.auto or not rois:
        # Prefer edges located from the checkerboard itself; blind scanning lands on
        # corners too often when the squares are only ~70 px.
        rois = board_edge_rois(gray, a.pattern, size=a.size)
        if rois:
            print(f"从棋盘格定位到 {len(rois)} 处格子边中点（每处 {a.size}x{a.size}）")
        else:
            print("没检出棋盘格，退回按边缘强度盲扫")
            rois = auto_roi(gray)
        if not rois:
            raise SystemExit("no straight edge found; pass --roi manually")

    a.out.mkdir(parents=True, exist_ok=True)
    label = a.label or a.image.stem
    results = []
    print(f"{'roi':<24}{'MTF50':>8}{'angle':>8}{'straight':>9}{'contrast':>9}   可信")
    for i, roi in enumerate(rois):
        try:
            res, patch, nx, ny, esf, bin_px, freq, mtf = analyze(gray, roi)
        except ValueError as exc:
            print(f"  {str(roi):<22} skipped: {exc}")
            continue
        # A curved edge smears the ESF; a second edge in the window makes it wiggle.
        # Both must be ruled out before the number means anything.
        trustworthy = (res["mtf50_resolved"]
                       and res.get("edge_line_rms_px", 99) <= 0.5
                       and res.get("esf_monotonicity", 0) >= 0.85)
        res["trustworthy"] = bool(trustworthy)
        results.append(res)
        draw(f"{label} #{i}", patch, nx, ny, esf, bin_px, freq, mtf, res,
             a.out / f"{label}_roi{i}.png")
        v = res["mtf50"]
        print(f"{str(roi):<24}{v if v is not None else float('nan'):8.3f}"
              f"{res['edge_angle_deg']:8.1f}{res.get('edge_line_rms_px', float('nan')):9.2f}"
              f"{res['contrast']:9.0f}   {'是' if trustworthy else '否'}")

    if not results:
        raise SystemExit("no ROI could be analysed")
    payload = dict(image=str(a.image), label=label, unit="cycles/pixel",
                   nyquist=0.5, results=results)
    (a.out / f"{label}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                                         encoding="utf-8")
    print(f"\n报告: {a.out / (label + '.json')}   图: {a.out}\\{label}_roi*.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())