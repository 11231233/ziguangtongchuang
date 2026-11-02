"""Promote the diagnostic rational fit into a standalone model artifact.

The rational coefficients only exist inside
`diagnostics/<audit>/diagnosis.json` today, where they are produced by
`scripts/diagnose_margin_dataset.py`. This script converts that diagnostic entry
into the same JSON shape as `calibration.json` so the LUT generator and the RTL
pipeline can consume it.

Hard rules:
  * The artifact is marked certified=false / diagnostic_only=true. It may NOT be
    exported as a runtime project or flashed.
  * cv2 5.x returns 14 coefficients for the rational model. The last six are
    s1..s4 (thin prism) and tauX/tauY (tilted sensor). This RTL/LUT path cannot
    represent them, so a non-zero value is a hard error rather than a silent
    truncation.
  * k3 is the numerator r^6 term here. It must never be confused with the legacy
    "k3 unsupported" field of the 4-term model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

FIELDS_TAIL = ("s1", "s2", "s3", "s4", "tauX", "tauY")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--diagnosis", required=True, help="diagnostics/<audit>/diagnosis.json")
    ap.add_argument("--geometry", required=True, help="targets/capture_geometry.json")
    ap.add_argument("--out", required=True, help="output model JSON path")
    ap.add_argument("--model-name", default="diagnostic_rational")
    ap.add_argument(
        "--dataset-json",
        help="dataset.json carrying geometry_sha256; defaults to <diagnosis.dataset>/dataset.json",
    )
    args = ap.parse_args(argv)

    diag_path = Path(args.diagnosis)
    geom_path = Path(args.geometry)
    out_path = Path(args.out)

    diag = json.loads(diag_path.read_text(encoding="utf-8"))
    geometry = json.loads(geom_path.read_text(encoding="utf-8"))

    # diagnosis.json points at the dataset directory in a string field; the
    # geometry fingerprint lives in that dataset's dataset.json.
    ds_ref = diag.get("dataset")
    if args.dataset_json:
        ds_path = Path(args.dataset_json)
    elif isinstance(ds_ref, str) and ds_ref:
        ds_path = Path(ds_ref) / "dataset.json"
    else:
        raise SystemExit("cannot locate dataset.json; pass --dataset-json")
    if not ds_path.is_file():
        raise SystemExit(f"dataset.json not found: {ds_path}")
    dataset = json.loads(ds_path.read_text(encoding="utf-8"))
    captured_geometry = dataset.get("geometry_sha256")
    if not captured_geometry:
        raise SystemExit(f"{ds_path} carries no geometry_sha256; refusing to guess")

    entry = next((m for m in diag["model_comparisons"] if m["name"] == args.model_name), None)
    if entry is None:
        raise SystemExit(f"model '{args.model_name}' not found in {diag_path}")
    if "error" in entry:
        raise SystemExit(f"model '{args.model_name}' failed in the audit: {entry['error']}")

    d = [float(v) for v in entry["d"]]
    if len(d) < 8:
        raise SystemExit(f"expected at least 8 rational coefficients, got {len(d)}")
    tail = d[8:]
    if any(abs(v) > 1e-12 for v in tail):
        raise SystemExit(
            "model uses thin-prism/tilted-sensor terms "
            f"{dict(zip(FIELDS_TAIL, tail))}; neither the LUT nor the RTL can represent them"
        )

    k1, k2, p1, p2, k3, k4, k5, k6 = d[:8]
    K = entry["K"]
    fx, fy, cx, cy = float(K[0][0]), float(K[1][1]), float(K[0][2]), float(K[1][2])

    # Same reference ROI / virtual output camera rule as tools/margin_calibration.py.
    roi = geometry["reference_roi"]
    out_w, out_h = geometry["output_size"]

    for name, value in dict(k1=k1, k2=k2, k3=k3, k4=k4, k5=k5, k6=k6, p1=p1, p2=p2).items():
        if not math.isfinite(value):
            raise SystemExit(f"non-finite coefficient {name}={value}")

    model = {
        "model_kind": "rational5x6",
        "fx": fx,
        "fy": fy,
        "cx": cx,
        "cy": cy,
        # numerator numerator: 1 + k1 r^2 + k2 r^4 + k3 r^6
        "k1": k1,
        "k2": k2,
        "k3": k3,
        # denominator: 1 + k4 r^2 + k5 r^4 + k6 r^6
        "k4": k4,
        "k5": k5,
        "k6": k6,
        "p1": p1,
        "p2": p2,
        "camera": geometry.get("camera", "C1"),
        "image_size": list(geometry["source_size"]),
        "geometry_sha256": captured_geometry,
        "train_rms_px": entry.get("train_rms_px"),
        "heldout_rms_px": entry.get("heldout_rms_px"),
        "output_camera": {
            "fx": fx,
            "fy": fy,
            "cx": cx - float(roi[0]),
            "cy": cy - float(roi[1]),
            "width": int(out_w),
            "height": int(out_h),
            "selection": "fixed central virtual view at source pixel scale; never adjusted with rotation",
        },
        "source_kind": "diagnostic_cached_verified_corners",
        "certified": False,
        "diagnostic_only": True,
        "models_deployed": False,
        "provenance": {
            "diagnosis_json": str(diag_path),
            "diagnosis_sha256": sha256_file(diag_path),
            "geometry_json": str(geom_path),
            "geometry_sha256_file": sha256_file(geom_path),
            "captured_geometry_sha256": captured_geometry,
            "dataset_json": str(ds_path),
            "corner_source": "verified_corners.npz (audit cache, diagnostic only)",
            "audit_findings": [
                "rational improves fit vs the deployed 4-term model but does not pass the 1px gate",
                "this artifact exists to exercise the LUT/ROM path, not to certify accuracy",
            ],
        },
    }

    # The capture-geometry fingerprint must match, otherwise old coefficients
    # must not be reused after a window change.
    captured = model["geometry_sha256"]
    if not captured:
        raise SystemExit("diagnosis.json carries no dataset.geometry_sha256; refusing to guess")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    from margin_geometry import identity  # type: ignore

    expected = identity(geometry)[0]
    if captured != expected:
        raise SystemExit(
            f"geometry mismatch: model {captured} vs targets {expected}; reacquire/recalibrate"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(model, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out_path}")
    print(f"  k1..k3 = {k1:+.6f} {k2:+.6f} {k3:+.8f}")
    print(f"  k4..k6 = {k4:+.6f} {k5:+.6f} {k6:+.8f}")
    print(f"  p1,p2  = {p1:+.6f} {p2:+.6f}")
    print(f"  fx,fy  = {fx:.3f} {fy:.3f}   cx,cy = {cx:.3f} {cy:.3f}")
    print(f"  train/heldout RMS = {entry.get('train_rms_px'):.4f} / {entry.get('heldout_rms_px'):.4f} px")
    print("  certified=false diagnostic_only=true (must not be exported or flashed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())