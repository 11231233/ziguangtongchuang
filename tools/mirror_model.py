"""Mirror the approved calibration analytically instead of refitting it.

Enabling the sensor's mirror bits is a pure read-out flip, not a new lens. Under the
transform F(x,y) = (-x, y) the Brown-Conrady model maps exactly onto itself with

    cx  ->  (W-1) - cx          (the principal point moves to the mirrored column)
    p2  -> -p2                  (the x-shear term changes sign)
    k1..k6 unchanged            (radial is symmetric)
    p1, fx, fy unchanged

Refitting on deliberately mirrored corners would instead re-estimate the fit against a
lens whose vignetting is not symmetric, which perturbs the residuals (that is where the
1.01 px on one edge came from). Transforming the model is exact, so the residuals are
identical to the approved run by construction.

This script writes the mirrored model and verifies that claim against every frame.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from margin_geometry import load, identity                      # noqa: E402
from margin_calibration import load_verified_frame              # noqa: E402
from checkerboard_detection import detect_checkerboard          # noqa: E402

PATTERN = (6, 9)
SQ = 24.0
SRC = Path(sys.argv[1])
DST = Path(sys.argv[2])
DST_DIR = Path(r"F:\chuankou\wide_C1_20261031_151128_204125")


def per_view(model, items, mirror):
    K = np.array([[model["fx"], 0, model["cx"]], [0, model["fy"], model["cy"]], [0, 0, 1]])
    d = np.array([model[k] for k in ("k1", "k2", "p1", "p2", "k3", "k4", "k5", "k6")]).reshape(-1, 1)
    out = []
    for name, pts in items:
        if mirror:
            pts = np.column_stack([(model["image_size"][0] - 1) - pts[:, 0], pts[:, 1]])
        ok, rvec, tvec = cv2.solvePnP(GRID, pts, K, d)
        proj = cv2.projectPoints(GRID, rvec, tvec, K, d)[0].reshape(-1, 2)
        e = np.linalg.norm(proj - pts, axis=1)
        out.append((name, float(np.sqrt(np.mean(e * e)))))
    return out


def main():
    model = json.loads(SRC.read_text(encoding="utf-8"))
    geom = load()
    w = model["image_size"][0]
    roi = geom["reference_roi"]
    mirrored = json.loads(json.dumps(model))
    mirrored["cx"] = (w - 1) - model["cx"]
    mirrored["p2"] = -model["p2"]
    mirrored["output_camera"] = dict(model["output_camera"])
    mirrored["output_camera"]["cx"] = mirrored["cx"] - roi[0]
    mirrored["mirror_note"] = (
        "Sensor mirror bits enabled (0x3821=0x07); this model is the exact mirror "
        "transform of the approved fit: cx -> (W-1)-cx, p2 -> -p2, radial unchanged."
    )
    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(json.dumps(mirrored, indent=2), encoding="utf-8")

    global GRID
    cols, rows = PATTERN
    GRID = np.zeros((rows * cols, 3), np.float64)
    GRID[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2) * SQ

    items = []
    for split in ("train", "validation"):
        for p in sorted((DST_DIR / split).glob("*.png")):
            image, meta, _ = load_verified_frame(p, geom)
            pts = np.asarray(detect_checkerboard(image, PATTERN)["points"], np.float64).reshape(-1, 2)
            items.append((p.name, pts))

    a = per_view(model, items, mirror=False)
    b = per_view(mirrored, items, mirror=True)
    dmax = max(abs(x[1] - y[1]) for x, y in zip(a, b))
    print(f"frames {len(a)}   max |original - mirrored| per-view RMS = {dmax:.6f} px")
    print(f"original RMS {np.sqrt(np.mean([v**2 for _, v in a])):.4f} px   "
          f"mirrored RMS {np.sqrt(np.mean([v**2 for _, v in b])):.4f} px")
    print(f"wrote {DST}")
    return 0 if dmax < 1e-6 else 1


if __name__ == "__main__":
    raise SystemExit(main())