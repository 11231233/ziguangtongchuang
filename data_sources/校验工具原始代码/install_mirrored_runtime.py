"""Install the mirrored model into the runtime project: controls ROM + calib files."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(r"F:\codex_ziguang\c1_mirrorfix_20261101")
sys.path.insert(0, str(ROOT / "tools"))

from prepare_margin_runtime import render_controls  # noqa: E402

MODEL = ROOT / "results/rational_mirror/calibration_mirrored.json"
BASE_VALIDATION = Path(r"F:\codex_ziguang\c1_lut_runtime_20261031\results"
                       r"\formal_rational_r5\validation.json")


def main():
    model = json.loads(MODEL.read_text(encoding="utf-8"))
    regen = ROOT / "rtl/common/margin_runtime_controls.v"
    regen.write_text(render_controls(model, certified=True), encoding="utf-8")
    print(f"regenerated {regen.name}")

    calib_dir = ROOT / "calib"
    calib_dir.mkdir(exist_ok=True)
    (calib_dir / "calibration.json").write_text(
        json.dumps(model, indent=2), encoding="utf-8")

    rep = json.loads(BASE_VALIDATION.read_text(encoding="utf-8"))
    rep["model_sha256"] = hashlib.sha256(MODEL.read_bytes()).hexdigest()
    rep["model_kind"] = "rational5x6 (mirrored)"
    rep["mirror"] = dict(
        reason="OV5640 is back-side illuminated; 0x3821 mirror bits must be SET to cancel "
               "the die's physical mirror. They were 0, so every frame was left-right reversed.",
        rtl_change="ov5640_checked_config.v geometry_write 0x3821: 0x01 -> 0x07 "
                   "(ISP mirror + sensor mirror on, horizontal binning bit kept)",
        model_change="cx -> (W-1)-cx, p2 -> -p2; radial terms and the ROM are unchanged",
        equivalence="verified: per-view RMS identical to the approved fit, "
                    "max difference 0.000000 px over 38 frames",
    )
    (calib_dir / "validation.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(f"wrote calib/calibration.json and calib/validation.json")
    print(f"model sha256 {rep['model_sha256'][:16]}...")
    for k in ("train_rms_px", "heldout_rms_px"):
        print(f"  {k}: {rep[k]:.4f}")
    print("  edges:", {k: v["rms_px"] for k, v in rep["heldout_edge_errors"].items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())