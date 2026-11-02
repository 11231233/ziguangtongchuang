"""Prove the runtime firmware carries exactly the coefficients the real calibration implies.

No host PC and no serial link needed. This closes the competition item
"标定参数解析：能够正确读取并解析相机内参矩阵（焦距、主点）及畸变系数（k1、k2 等）"
by making the whole chain reproducible and checkable on one command:

    calibration.json (real capture)
      -> parse intrinsics + distortion
      -> quantise to Q16.16
      -> per-angle coefficient sets (-20..+20)
      -> margin_runtime_controls.v ROM
      -> bitstream

It re-derives every angle from the JSON and diffs it against the ROM actually present in
the RTL, so the numbers on the board provably come from the calibration rather than from
hand-typed constants.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from margin_calibration import coefficients, require_runtime_model  # noqa: E402
from prepare_margin_runtime import packed                          # noqa: E402

ROW = re.compile(r"6'd(\d+):begin cor<=448'h([0-9a-fA-F]{112});raw<=448'h([0-9a-fA-F]{112});")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", type=Path, default=ROOT / "calib/calibration.json")
    ap.add_argument("--validation", type=Path, default=ROOT / "calib/validation.json")
    ap.add_argument("--controls", type=Path, default=ROOT / "rtl/common/margin_runtime_controls.v")
    ap.add_argument("--out", type=Path, default=ROOT / "reports/calib_chain_report.json")
    a = ap.parse_args(argv)

    model, report = require_runtime_model(a.model, a.validation)
    print("== 1. 解析标定产物 ==")
    print(f"  model file      {a.model}")
    print(f"  sha256          {hashlib.sha256(a.model.read_bytes()).hexdigest()[:32]}…")
    print(f"  model_kind      {model.get('model_kind', 'poly2')}")
    print(f"  内参 fx,fy     {model['fx']:.4f}, {model['fy']:.4f}")
    print(f"  主点 cx,cy     {model['cx']:.4f}, {model['cy']:.4f}")
    print(f"  切向 p1,p2     {model['p1']:+.8f}, {model['p2']:+.8f}")
    ks = [f"k{i}={model.get(f'k{i}', 0):+.8f}" for i in range(1, 7)]
    print("  径向 " + "  ".join(ks))
    print(f"  输出相机       {model['output_camera']['fx']:.3f} / {model['output_camera']['cx']:.3f},"
          f"{model['output_camera']['cy']:.3f}")
    print(f"  训练/验证 RMS  {report['train_rms_px']:.4f} / {report['heldout_rms_px']:.4f} px")
    print(f"  ready_for_runtime {report['ready_for_runtime']}  reasons={report['reasons']}")

    print("\n== 2. 重新生成 41 档系数（-20..+20）==")
    expect = {}
    for angle in range(-20, 21):
        cor = packed(coefficients(model, angle))
        raw = packed(coefficients(model, angle, True))
        expect[angle + 20] = (f"{cor:0112x}", f"{raw:0112x}")

    print("\n== 3. 与固件 ROM 逐档比对 ==")
    if not a.controls.is_file():
        raise SystemExit(f"controls file not found: {a.controls}")
    text = a.controls.read_text(encoding="utf-8")
    got = {int(m.group(1)): (m.group(2).lower(), m.group(3).lower()) for m in ROW.finditer(text)}
    print(f"  固件档数 {len(got)} / 期望 41")
    if len(got) != 41:
        raise SystemExit("ROM row count mismatch")

    bad = []
    for idx, (cor, raw) in expect.items():
        g = got.get(idx)
        if g is None or g[0] != cor or g[1] != raw:
            bad.append(idx)
    print(f"  不匹配档数 {len(bad)}")
    if bad:
        for idx in bad[:6]:
            ang = idx - 20
            print(f"    angle {ang:+d}: expected {expect[idx][0][:24]}… got {got.get(idx, ('',''))[0][:24]}…")
        raise SystemExit("ROM does not match the calibration")

    print("\n== 4. 抽样展示（现场演示可直接用这几行）==")
    for ang in (0, -20, 20):
        idx = ang + 20
        cor, raw = expect[idx]
        print(f"  {ang:+3d}°  COR={cor[:32]}…{cor[-8:]}  RAW={raw[:16]}…")
        print(f"        与固件 ROM {'一致' if got[idx] == (cor, raw) else '不一致'}")

    rom_hash = hashlib.sha256(a.controls.read_bytes()).hexdigest()
    out = dict(
        passed=True,
        model=str(a.model),
        model_sha256=hashlib.sha256(a.model.read_bytes()).hexdigest(),
        controls=str(a.controls),
        controls_sha256=rom_hash,
        intrinsics={k: model[k] for k in ("fx", "fy", "cx", "cy")},
        tangential={k: model[k] for k in ("p1", "p2")},
        radial={f"k{i}": model.get(f"k{i}", 0.0) for i in range(1, 7)},
        output_camera=model["output_camera"],
        train_rms_px=report["train_rms_px"],
        heldout_rms_px=report["heldout_rms_px"],
        ready_for_runtime=report["ready_for_runtime"],
        angles_checked=41,
        angle_range=[-20, 20],
        mismatched_angles=[],
        statement=(
            "The 41 coefficient sets in the runtime ROM are re-derived from calibration.json "
            "and compared word for word. A pass means the board runs the parsed real "
            "calibration, not hand-entered numbers."
        ),
    )
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nPASS  全部 41 档与标定一致   报告: {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())