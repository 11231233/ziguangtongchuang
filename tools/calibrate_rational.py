"""Formal calibration for the rational radial model (the one the LUT implements).

margin_calibration.py only fits the 4-term model, so it cannot certify this lens. This
tool keeps that file's guarantees - verified reconstructed RAW frames only, geometry
fingerprint match, no synthetic data - and swaps in the rational model the hardware LUT
actually runs. It then evaluates the same gates:

  * train / held-out RMS <= 1 px, per-view <= 1.5 px
  * spatial coverage on the measured effective area (every edge >=8 points and >=2 poses,
    every corner observed)
  * per-edge validated residuals <= 1 px RMS and <= 2 px P95
  * fixed-view +/-20 deg mapping audit at FULL resolution, using the Q16 LUT arithmetic
    the RTL performs, not floating point

Nothing here can set ready_for_runtime by itself; it evaluates and reports.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

from checkerboard_detection import detect_checkerboard  # noqa: E402
from margin_calibration import load_verified_frame, effective_region, spatial_coverage  # noqa: E402
from margin_geometry import load, identity  # noqa: E402

CELLS = 2048
R2_Q16_MAX = 2097152


MIRROR_X = False


def load_pairs(folder: Path, geometry: dict) -> list[dict]:
    items = []
    width = geometry["source_size"][0]
    for p in sorted(Path(folder).glob("*.png")):
        image, meta, digest = load_verified_frame(p, geometry)
        pts = np.asarray(detect_checkerboard(image, PATTERN)["points"], np.float64).reshape(-1, 2)
        if MIRROR_X:
            # The sensor's mirror bits were disabled, so every stored frame is left-right
            # reversed. Enabling those bits (0x3821=0x07) flips the read-out horizontally;
            # mirroring the measured corner coordinates models exactly that, keeping the
            # real lens, focus and illumination untouched.
            pts = np.column_stack([(width - 1) - pts[:, 0], pts[:, 1]])
        items.append(dict(path=str(p), image=image, points=pts, sha256=digest))
    return items


PATTERN = (6, 9)
SQUARE_MM = 24.0


def object_grid() -> np.ndarray:
    cols, rows = PATTERN
    grid = np.zeros((rows * cols, 3), np.float64)
    grid[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2) * SQUARE_MM
    return grid


def fit_rational(train: list[dict], size) -> tuple[np.ndarray, np.ndarray, float]:
    obj = object_grid().astype(np.float32)      # cv2 5.x requires Point3f
    objs = [obj] * len(train)
    obs = [t["points"].reshape(-1, 1, 2).astype(np.float32) for t in train]
    rms, K, d, _, _ = cv2.calibrateCamera(objs, obs, tuple(size), None, None,
                                          flags=cv2.CALIB_RATIONAL_MODEL)
    return K, np.asarray(d, np.float64).ravel()[:8], float(rms)


def per_view(obj, K, d, items):
    out = []
    for it in items:
        obs = it["points"]
        ok, rvec, tvec = cv2.solvePnP(obj, obs, K, d)
        if not ok:
            raise SystemExit(f"solvePnP failed: {it['path']}")
        proj = cv2.projectPoints(obj, rvec, tvec, K, d)[0].reshape(-1, 2)
        e = np.linalg.norm(proj - obs, axis=1)
        out.append(dict(file=it["path"], rms_px=float(np.sqrt(np.mean(e * e))),
                        p95_px=float(np.percentile(e, 95)), max_px=float(e.max()),
                        points=obs))
    return out


def build_rom(k, rom_path: Path) -> np.ndarray:
    """2048 cells of {Q24 base, Q24 delta} exactly as gen_radial_lut_rom.py does."""
    edges = np.arange(CELLS + 1, dtype=np.float64) / 64.0
    num = 1 + k[0] * edges + k[1] * edges ** 2 + k[4] * edges ** 3
    den = 1 + k[5] * edges + k[6] * edges ** 2 + k[7] * edges ** 3
    bases = np.round(num / den * (1 << 24)).astype(np.int64)
    deltas = bases[1:] - bases[:-1]
    if int(np.abs(bases).max()) >= 1 << 31 or int(np.abs(deltas).max()) >= 1 << 31:
        raise SystemExit("Q24 overflow in ROM")
    words = np.fromiter((((int(b) & 0xFFFFFFFF) << 32) | (int(x) & 0xFFFFFFFF)
                         for b, x in zip(bases[:-1], deltas)), np.uint64, count=CELLS)
    rom_path.parent.mkdir(parents=True, exist_ok=True)
    rom_path.write_text("\n".join(f"{int(w):016x}" for w in words) + "\n", encoding="ascii")
    return words


def lut_factor(words: np.ndarray, r2_q16: np.ndarray) -> np.ndarray:
    r2 = np.asarray(r2_q16, np.int64)
    endpoint = r2 >= R2_Q16_MAX
    addr = np.where(endpoint, CELLS - 1, (r2 >> 10) & (CELLS - 1))
    frac = np.where(endpoint, 1024, r2 & 1023)
    raw = words[addr]
    hi = (raw >> np.uint64(32)).astype(np.int64)
    lo = (raw & np.uint64(0xFFFFFFFF)).astype(np.int64)
    base = np.where(hi >= (1 << 31), hi - (1 << 32), hi)
    delta = np.where(lo >= (1 << 31), lo - (1 << 32), lo)
    return ((base << 10) + delta * frac + (1 << 17)) >> 18


def float_map(k, out_cam, angle, x, y):
    t = math.radians(angle)
    co, si = math.cos(t), math.sin(t)
    fx, fy, ox, oy = out_cam["fx"], out_cam["fy"], out_cam["cx"], out_cam["cy"]
    ux = (co * (x - 640) - si * (y - 360) + 640 - ox) / fx
    uy = (si * (x - 640) + co * (y - 360) + 360 - oy) / fy
    r2 = ux * ux + uy * uy
    num = 1 + k[0] * r2 + k[1] * r2 ** 2 + k[4] * r2 ** 3
    den = 1 + k[5] * r2 + k[6] * r2 ** 2 + k[7] * r2 ** 3
    s = num / den
    u = kF[0] * (ux * s + 2 * k[2] * ux * uy + k[3] * (r2 + 2 * ux * ux)) + kC[0]
    v = kF[1] * (uy * s + k[2] * (r2 + 2 * uy * uy) + 2 * k[3] * ux * uy) + kC[1]
    return u, v, ux, uy, r2, s


def mapping_audit(k, out_cam, words, geometry, angles=range(-20, 21), step=1):
    """Full-resolution fixed-point audit using the Q16 LUT path."""
    sw, sh = geometry["source_size"]
    y, x = np.mgrid[0:720:step, 0:1280:step]
    x = x.astype(np.int64)
    y = y.astype(np.int64)
    fx, fy, ox, oy = out_cam["fx"], out_cam["fy"], out_cam["cx"], out_cam["cy"]
    rows = []
    for angle in angles:
        t = math.radians(angle)
        co, si = math.cos(t), math.sin(t)
        A = round(co / fx * 2 ** 24)
        B = round(-si / fx * 2 ** 24)
        C = round((640 - co * 640 + si * 360 - ox) / fx * 65536)
        D = round(si / fy * 2 ** 24)
        E = round(co / fy * 2 ** 24)
        F = round((360 - si * 640 - co * 360 - oy) / fy * 65536)
        qx = ((A * x + B * y + 128) >> 8) + C
        qy = ((D * x + E * y + 128) >> 8) + F
        qr = (qx * qx + qy * qy + 32768) >> 16
        factor = lut_factor(words, qr)
        mul = lambda a, b: (a * b + 32768) >> 16
        qfx, qfy = round(kF[0] * 65536), round(kF[1] * 65536)
        qcx, qcy = round(kC[0] * 65536), round(kC[1] * 65536)
        qp1, qp2 = round(k[2] * 65536), round(k[3] * 65536)
        xx, yy, xy = mul(qx, qx), mul(qy, qy), mul(qx, qy)
        qu = mul(qfx, mul(qx, factor) + 2 * mul(qp1, xy) + mul(qp2, qr + 2 * xx)) + qcx
        qv = mul(qfy, mul(qy, factor) + mul(qp1, qr + 2 * yy) + 2 * mul(qp2, xy)) + qcy
        u, v, ux, uy, r2, s = float_map(k, out_cam, angle, x, y)
        good = ((u >= 1) & (u <= sw - 2) & (v >= 1) & (v <= sh - 2)
                & (qu >= 65536) & (qu <= (sw - 2) * 65536)
                & (qv >= 65536) & (qv <= (sh - 2) * 65536)
                & (np.abs(qx) <= 262144) & (np.abs(qy) <= 262144))
        err = float(np.hypot(qu / 65536 - u, qv / 65536 - v).max())
        dsdx = 2 * ux * (k[0] + 2 * k[1] * r2 + 3 * k[4] * r2 ** 2)
        dsdy = 2 * uy * (k[0] + 2 * k[1] * r2 + 3 * k[4] * r2 ** 2)
        j00 = s + ux * dsdx + 2 * k[2] * uy + 6 * k[3] * ux
        j01 = ux * dsdy + 2 * k[2] * ux + 2 * k[3] * uy
        j10 = uy * dsdx + 2 * k[2] * ux + 2 * k[3] * uy
        j11 = s + uy * dsdy + 6 * k[2] * uy + 2 * k[3] * ux
        det = float((j00 * j11 - j01 * j10).min())
        rows.append(dict(angle=int(angle), pixels=int(x.size),
                         invalid_pixels=int((~good).sum()),
                         max_fixed_error_px=err, min_jacobian_det=det,
                         passed=bool(good.all() and err <= .25 and det > 0)))
    return dict(passed=all(r["passed"] for r in rows), full_pixel_audit=step == 1,
                angle_range=[min(angles), max(angles)], rows=rows)


def main(argv=None):
    global kF, kC
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--geometry", type=Path, default=None)
    ap.add_argument("--full-window-confirmed", action="store_true")
    ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--mirror-x", action="store_true",
                    help="fit on horizontally mirrored corner coordinates, i.e. the "
                         "sensor configuration after enabling the 0x3821 mirror bits")
    a = ap.parse_args(argv)
    global MIRROR_X
    MIRROR_X = bool(a.mirror_x)

    if not a.full_window_confirmed:
        raise SystemExit("confirm the full-window capture and fixed lens/imaging mode first")
    geometry = load(str(a.geometry) if a.geometry else None)
    train = load_pairs(a.dataset / "train", geometry)
    validation = load_pairs(a.dataset / "validation", geometry)
    if len(train) < 20 or len(validation) < 6:
        raise SystemExit(f"need >=20 train and >=6 validation, got {len(train)}/{len(validation)}")

    obj = object_grid()
    K, d, train_rms = fit_rational(train, geometry["source_size"])
    kF = (float(K[0, 0]), float(K[1, 1]))
    kC = (float(K[0, 2]), float(K[1, 2]))
    roi = geometry["reference_roi"]
    out_cam = dict(fx=kF[0], fy=kF[1], cx=kC[0] - roi[0], cy=kC[1] - roi[1], width=1280, height=720,
                   selection="fixed central virtual view at source pixel scale; never adjusted with rotation")

    a.out.mkdir(parents=True, exist_ok=False)
    words = build_rom(d, a.out / "radial_lut.hex")

    tr = per_view(obj, K, d, train)
    va = per_view(obj, K, d, validation)
    heldout = float(np.sqrt(np.mean([r["rms_px"] ** 2 for r in va])))
    region = effective_region()
    spatial = spatial_coverage([r["points"] for r in train], geometry["source_size"], region)
    mapping = mapping_audit(d, out_cam, words, geometry, step=a.step)

    x0, y0, x1, y1 = region
    rw, rh = x1 - x0 + 1, y1 - y0 + 1
    edge = {}
    for name, fn in (("left", lambda p: p[:, 0] < x0 + .15 * rw), ("right", lambda p: p[:, 0] > x1 - .15 * rw),
                     ("top", lambda p: p[:, 1] < y0 + .15 * rh), ("bottom", lambda p: p[:, 1] > y1 - .15 * rh)):
        e = []
        for r in va:
            mask = fn(r["points"])
            if mask.any():
                proj_pts = r["points"][mask]
                ok, rv, tv = cv2.solvePnP(obj, r["points"], K, d)
                proj = cv2.projectPoints(obj, rv, tv, K, d)[0].reshape(-1, 2)
                e.extend(np.linalg.norm(proj - r["points"], axis=1)[mask].tolist())
        arr = np.array(e)
        edge[name] = dict(points=int(arr.size),
                          rms_px=float(np.sqrt(np.mean(arr ** 2))) if arr.size else None,
                          p95_px=float(np.percentile(arr, 95)) if arr.size else None)

    model = dict(model_kind="rational5x6", fx=kF[0], fy=kF[1], cx=kC[0], cy=kC[1],
                 k1=d[0], k2=d[1], p1=d[2], p2=d[3], k3=d[4], k4=d[5], k5=d[6], k6=d[7],
                 camera=geometry.get("camera", "C1"), image_size=list(geometry["source_size"]),
                 geometry_sha256=identity(geometry)[0], output_camera=out_cam,
                 radial_lut="results ROM radial_lut.hex (2048 cells, Q24 base+delta, Q16 out)",
                 rtl_radial_path="RADIAL_MODEL_LUT=1, lut_enable=1 (k1,k2 forced to 0)",
                 source_kind="verified_margin_raw_calibration",
                 synthetic_test_data=False, train_rms_px=train_rms,
                 pattern=list(PATTERN), square_mm=SQUARE_MM,
                 training_frames=len(train), validation_frames=len(validation))

    reasons = []
    if train_rms > 1 or heldout > 1 or max(r["rms_px"] for r in va) > 1.5:
        reasons.append("Independent image residual threshold failed; inspect data/model, do not force coefficients")
    if not spatial["passed"]:
        reasons.append("Effective-area edges/corners lack independent training observations")
    if any(v["points"] < 8 or v["rms_px"] is None or v["rms_px"] > 1 or v["p95_px"] > 2 for v in edge.values()):
        reasons.append("Independent validation edges lack observations or exceed outer-ring residual limits")
    if not mapping["passed"]:
        reasons.append("Fixed-view +/-20 degrees lacks source coverage, fixed-point precision or monotonicity")

    model_bytes = json.dumps(model, indent=2).encode("utf-8")
    (a.out / "calibration.json").write_bytes(model_bytes)
    report = dict(geometry_sha256=identity(geometry)[0], model_kind="rational5x6",
                  operator_full_window_confirmed=True,
                  training_frames=len(train), validation_frames=len(validation),
                  source_images=[dict(file=t["path"], sha256=t["sha256"]) for t in train + validation],
                  train_rms_px=train_rms, heldout_rms_px=heldout,
                  per_view=[{k: v for k, v in r.items() if k != "points"} for r in va], spatial_coverage=spatial,
                  effective_area=dict(region=region, source="targets/effective_area.json"),
                  heldout_edge_errors=edge, mapping_coverage=mapping,
                  rom=dict(file="radial_lut.hex",
                           sha256=hashlib.sha256((a.out / "radial_lut.hex").read_bytes()).hexdigest()),
                  error_thresholds=dict(train_rms_px=1., heldout_rms_px=1., max_view_rms_px=1.5,
                                        edge_rms_px=1., edge_p95_px=2., fixed_point_px=.25),
                  hardware_tested=False, model_sha256=hashlib.sha256(model_bytes).hexdigest(),
                  reasons=reasons, ready_for_runtime=not reasons)
    (a.out / "validation.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(dict(train_rms_px=round(train_rms, 4), heldout_rms_px=round(heldout, 4),
                          max_view_px=round(max(r["rms_px"] for r in va), 4),
                          coverage=spatial["passed"],
                          edges={k: (v["points"], None if v["rms_px"] is None else round(v["rms_px"], 2))
                                 for k, v in edge.items()},
                          mapping=mapping["passed"], reasons=reasons,
                          ready_for_runtime=not reasons), indent=2, ensure_ascii=False))
    print(f"Result {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())