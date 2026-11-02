"""Measure the optical effective imaging area from real captured frames.

Why this exists: the coverage gate demanded checkerboard corners in all four 25% corner
boxes and on all four 15% edge bands of the full 1296x972 rectangle. On this C1 assembly
the outermost band carries no usable signal (measured 7-37 against 80-100 at the centre),
so corners there cannot be observed at all; a board pushed into that corner is also
clipped, which the dataset format rejects ("No complete board in reconstructed frame").
The gate was therefore unsatisfiable for reasons unrelated to calibration accuracy.

This script fixes the *domain*, not the thresholds: it measures where the optics deliver
signal and stores that region as a versioned artifact. RMS <= 1 px, per-view <= 1.5 px and
P95 <= 2 px are unchanged.

Method
  * radial coordinate r, normalised so r = 1 at the edge midpoint and r = sqrt(2) at a
    corner:  r = hypot((x-cx)/(W/2), (y-cy)/(H/2))
  * per frame and radius bin, take the 95th percentile brightness, divided by the same
    frame's central 95th percentile. Using p95 instead of the mean keeps the result about
    the optics rather than about where the board happened to be or how the scene was lit.
  * median across frames -> relative illumination profile
  * r_cut = largest r whose relative illumination is still >= --min-relative
  * effective rectangle = centred, aspect-preserving, with its corner on r = r_cut
  * the last 32 rows are the page footer (tags/CRC) and are always excluded

Read-only with respect to the datasets.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FOOTER_ROWS = 32


def imread_unicode(path: Path):
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_GRAYSCALE) if data.size else None


def frame_paths(datasets: list[Path]) -> list[Path]:
    out: list[Path] = []
    for ds in datasets:
        for split in ("train", "validation"):
            folder = ds / split
            if folder.is_dir():
                out.extend(sorted(folder.glob("*.png")))
    return out


def radial_profile(gray: np.ndarray, bins: np.ndarray) -> tuple[np.ndarray, float]:
    h, w = gray.shape
    hh = h - FOOTER_ROWS
    scene = gray[:hh, :].astype(np.float64)
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    xs = np.arange(w)
    ys = np.arange(hh)
    gx, gy = np.meshgrid((xs - cx) / (w / 2.0), (ys - cy) / (h / 2.0))
    r = np.hypot(gx, gy)
    idx = np.digitize(r, bins) - 1
    prof = np.full(len(bins) - 1, np.nan)
    for i in range(len(bins) - 1):
        m = idx == i
        if m.any():
            prof[i] = np.percentile(scene[m], 95)
    # central reference: everything inside r < 0.25
    ref = float(np.percentile(scene[r < 0.25], 95))
    return prof / ref if ref > 0 else prof, ref


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", action="append", required=True,
                    help="dataset directory holding train/ and validation/ (repeatable)")
    ap.add_argument("--min-relative", type=float, default=0.50,
                    help="relative illumination at the effective-area corner (default 0.50)")
    ap.add_argument("--out", default=str(ROOT / "targets/effective_area.json"))
    args = ap.parse_args(argv)

    datasets = [Path(d) for d in args.dataset]
    frames = frame_paths(datasets)
    if not frames:
        raise SystemExit("no frames found")

    bins = np.arange(0.0, 1.55, 0.05)
    profiles = []
    refs = []
    used = []
    shape = None
    for p in frames:
        gray = imread_unicode(p)
        if gray is None:
            print(f"skip unreadable {p}")
            continue
        shape = gray.shape
        prof, ref = radial_profile(gray, bins)
        profiles.append(prof)
        refs.append(ref)
        used.append(p)

    prof = np.nanmedian(np.stack(profiles), axis=0)
    centers = (bins[:-1] + bins[1:]) / 2.0
    h, w = shape
    hh = h - FOOTER_ROWS

    ok = np.isfinite(prof) & (prof >= args.min_relative)
    r_cut = 0.0
    for c, good in zip(centers, ok):
        if good:
            r_cut = float(c)
        else:
            break
    if r_cut <= 0:
        raise SystemExit("relative illumination never reaches the threshold")

    # Corner of the effective rectangle sits exactly on r = r_cut, aspect preserved.
    k = r_cut / math.sqrt(2.0)
    half_w, half_h = k * (w / 2.0), k * (hh / 2.0)
    cx, cy = (w - 1) / 2.0, (hh - 1) / 2.0
    x0, x1 = int(round(cx - half_w)), int(round(cx + half_w))
    y0, y1 = int(round(cy - half_h)), int(round(cy + half_h))
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w - 1, x1), min(hh - 1, y1)
    rw, rh = x1 - x0 + 1, y1 - y0 + 1

    print(f"frames analysed      : {len(used)}   image {w}x{h} (scene rows {hh})")
    print("relative illumination by radius (95th percentile, median across frames):")
    line = "  "
    for c, v in zip(centers, prof):
        line += f"{c:4.2f}:{v:4.2f} " if np.isfinite(v) else f"{c:4.2f}: --  "
        if len(line) > 108:
            print(line)
            line = "  "
    if line.strip():
        print(line)
    print(f"r_cut at {args.min_relative:.0%} relative illumination: {r_cut:.2f}")
    print(f"effective rect       : x {x0}..{x1}  y {y0}..{y1}   ({rw}x{rh} px)")

    payload = dict(
        schema="effective_area_v1",
        created_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        generator="scripts/measure_effective_area.py",
        method=dict(
            radial_coordinate="hypot((x-cx)/(W/2), (y-cy)/(H/2)); 1.0 at edge midpoint",
            statistic="95th percentile per radius bin, divided by the central (r<0.25) 95th percentile",
            aggregation="median across frames",
            min_relative_illumination=args.min_relative,
            footer_rows_excluded=FOOTER_ROWS,
            rectangle="centred, aspect preserving, corner on r = r_cut",
        ),
        source_frames=len(used),
        source_datasets=[str(d) for d in datasets],
        frame_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in used},
        image_size=[w, h],
        scene_rows=hh,
        radial_profile={f"{c:.2f}": (None if not np.isfinite(v) else round(float(v), 4))
                        for c, v in zip(centers, prof)},
        r_cut=round(r_cut, 3),
        effective_rect=[x0, y0, x1, y1],
        effective_rect_size=[rw, rh],
        effective_area_fraction=round(rw * rh / float(w * hh), 4),
        statement=(
            "Corner and edge coverage is evaluated inside this rectangle only. Precision "
            "thresholds are unchanged (RMS <= 1 px, per-view <= 1.5 px, P95 <= 2 px). This is a "
            "measured domain correction, not a threshold relaxation, and it is not a claim that "
            "calibration accuracy is sufficient."
        ),
    )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"effective area       : {payload['effective_area_fraction'] * 100:.1f}% of the scene")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())