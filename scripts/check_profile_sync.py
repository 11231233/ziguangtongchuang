"""Check that the user-selected empirical profile and the RTL power-on defaults agree.

The profile JSON is the single human-readable record of the S2 Z0 preset; the RTL
reset block is what actually ships. They can drift silently, so this guard fails
if any coefficient, strength, or zoom differs.

This checks consistency, not lens calibration correctness.
"""
from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "targets/selected_empirical_profile.json"
RTL = ROOT / "rtl/common/warp_controls.v"

# profile key -> first RTL assignment name in the reset block
FIELDS = {"A": "A", "B": "B", "C": "C", "D": "D", "E": "E", "F": "F",
          "k1": "k1", "k2": "k2", "p1": "p1", "p2": "p2",
          "fx": "fx", "fy": "fy", "cx": "cx", "cy": "cy"}


def main():
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    coeff = profile["signed_q16_coefficients"]
    text = RTL.read_text(encoding="utf-8")
    errors = []
    for key, name in FIELDS.items():
        m = re.search(r"\b%s\s*<=\s*(-?\d+)" % re.escape(name), text)
        if not m:
            # B/D/p1/p2 are tied to 0 in top_pangu50.v, not assigned in warp_controls.
            if int(coeff[key]) == 0:
                continue
            errors.append("RTL missing assignment for %s" % key)
            continue
        rtl_value = int(m.group(1))
        if rtl_value != int(coeff[key]):
            errors.append("%s: profile=%d rtl=%d" % (key, int(coeff[key]), rtl_value))
    m = re.search(r"strength\s*<=\s*(\d+)", text)
    if not m or int(m.group(1)) != int(profile["strength"]):
        errors.append("strength mismatch")
    m = re.search(r"zoom\s*<=\s*(\d+)", text)
    if not m or int(m.group(1)) != int(profile["zoom_index"]):
        errors.append("zoom mismatch")
    if profile.get("lens_calibrated") is not False:
        errors.append("profile must state lens_calibrated=false")
    if list(profile.get("image_size", [])) != [1280, 720]:
        errors.append("profile image_size must be 1280x720")

    if errors:
        print("PROFILE_SYNC FAIL:", "; ".join(errors))
        raise SystemExit(1)
    print("PROFILE_SYNC PASS: S2 Z0 profile matches warp_controls.v reset defaults; "
          "lens_calibrated=false; single-view estimate, not a multi-view lens calibration")


if __name__ == "__main__":
    main()
