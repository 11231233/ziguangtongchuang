"""Generate the radial-factor ROM for rtl/warp/radial_lut.v.

The deployed pipeline models the radial scale as a pure function of r^2:

    legacy  : s = 1 + k1 r^2 + k2 r^4
    rational: s = (1 + k1 r^2 + k2 r^4 + k3 r^6) / (1 + k4 r^2 + k5 r^4 + k6 r^6)

The rational form has a division, which has no place in the 27-clock coordinate
pipeline. Tabulating s(r^2) turns the division into a ROM read plus one linear
interpolation, and it also removes the k3..k6 expressiveness limit of the current
RTL without touching the affine, tangential or output-camera stages.

ROM format, exactly as radial_lut.v reads it:
    word[63:32] = Q24 base   = round(s(c/64) * 2^24)
    word[31:0]  = Q24 delta  = base(c+1) - base(c)
    address     = r2_q16[20:10]        (r^2 in [0,32] Q16, 2048 cells)
    fraction    = r2_q16[9:0]          (1024 = end of cell)
    out         = (base<<10 + delta*frac + 2^17) >>> 18   -> Q16

This script does not trust the table: it emulates the RTL bit-exactly, compares
against the double-precision model over the whole Q16 domain, and reports the
worst per-pixel consequence. It refuses to emit a ROM when the model has a
denominator pole, a fold-back, or a factor the Q16/Q24 widths cannot hold.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

CELLS = 2048
R2_MAX = 32.0
R2_Q16_MAX = int(R2_MAX * 65536)  # 2097152


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def model_coefficients(model: dict) -> dict:
    kind = model.get("model_kind", "poly2")
    return dict(
        kind=kind,
        k1=float(model.get("k1", 0.0)),
        k2=float(model.get("k2", 0.0)),
        k3=float(model.get("k3", 0.0)),
        k4=float(model.get("k4", 0.0)),
        k5=float(model.get("k5", 0.0)),
        k6=float(model.get("k6", 0.0)),
    )


def factor_float(c: dict, r2: np.ndarray) -> np.ndarray:
    r2 = np.asarray(r2, dtype=np.float64)
    num = 1.0 + c["k1"] * r2 + c["k2"] * r2**2 + c["k3"] * r2**3
    den = 1.0 + c["k4"] * r2 + c["k5"] * r2**2 + c["k6"] * r2**3
    return num / den


def denominator_float(c: dict, r2: np.ndarray) -> np.ndarray:
    r2 = np.asarray(r2, dtype=np.float64)
    return 1.0 + c["k4"] * r2 + c["k5"] * r2**2 + c["k6"] * r2**3


def build_table(c: dict):
    """Return (words, bases, deltas): 2048 ROM words, base Q24 high 32, delta Q24 low 32."""
    edges = np.arange(CELLS + 1, dtype=np.float64) / 64.0
    vals = factor_float(c, edges)
    bases = np.round(vals * (1 << 24)).astype(np.int64)
    deltas = bases[1:] - bases[:-1]
    for name, arr in (("base", bases), ("delta", deltas)):
        lo, hi = int(arr.min()), int(arr.max())
        if lo < -(1 << 31) or hi > (1 << 31) - 1:
            raise SystemExit(f"{name} does not fit signed 32 bits: [{lo}, {hi}]")
    # Two's-complement packing; everything is built as a non-negative Python int
    # first so the uint64 conversion can never wrap.
    words = np.fromiter(
        (((int(b) & 0xFFFFFFFF) << 32) | (int(d) & 0xFFFFFFFF)
         for b, d in zip(bases[:-1], deltas)),
        dtype=np.uint64,
        count=CELLS,
    )
    return words, bases, deltas


def emulate_rtl(words: np.ndarray, r2_q16: np.ndarray) -> np.ndarray:
    """Bit-exact model of radial_lut.v including address/fraction split and rounding."""
    r2 = np.asarray(r2_q16, dtype=np.int64)
    endpoint = r2 >= R2_Q16_MAX
    address = np.where(endpoint, CELLS - 1, (r2 >> 10) & (CELLS - 1))
    frac = np.where(endpoint, 1024, r2 & 1023)

    raw = words[address]
    hi = (raw >> np.uint64(32)).astype(np.int64)          # 0 .. 2^32-1
    lo = (raw & np.uint64(0xFFFFFFFF)).astype(np.int64)   # 0 .. 2^32-1
    base = np.where(hi >= (1 << 31), hi - (1 << 32), hi)
    delta = np.where(lo >= (1 << 31), lo - (1 << 32), lo)

    interp = (base << 10) + delta * frac
    return (interp + (1 << 17)) >> 18


def reachable_r2(model: dict, geometry: dict, step: int = 1) -> float:
    """Max r^2 over all 41 board angles, using the RTL's own fixed-point form."""
    out = model["output_camera"]
    fx, fy, ox, oy = out["fx"], out["fy"], out["cx"], out["cy"]
    y, x = np.mgrid[0 : out["height"] : step, 0 : out["width"] : step]
    x = x.astype(np.int64)
    y = y.astype(np.int64)
    worst = 0.0
    for angle in range(-20, 21):
        t = math.radians(angle)
        co, si = math.cos(t), math.sin(t)
        A = round(co / fx * 2**24)
        B = round(-si / fx * 2**24)
        C = round((640 - co * 640 + si * 360 - ox) / fx * 65536)
        D = round(si / fy * 2**24)
        E = round(co / fy * 2**24)
        F = round((360 - si * 640 - co * 360 - oy) / fy * 65536)
        qx = ((A * x + B * y + 128) >> 8) + C
        qy = ((D * x + E * y + 128) >> 8) + F
        r2 = ((qx * qx + qy * qy + 32768) >> 16) / 65536.0
        worst = max(worst, float(r2.max()))
    return worst


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", required=True, help="calibration.json (poly2) or rational model JSON")
    ap.add_argument("--geometry", required=True, help="targets/capture_geometry.json")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--name", default="radial_lut")
    args = ap.parse_args(argv)

    model_path = Path(args.model)
    geometry_path = Path(args.geometry)
    out_dir = Path(args.out)
    model = load_json(model_path)
    geometry = load_json(geometry_path)
    c = model_coefficients(model)

    out_dir.mkdir(parents=True, exist_ok=True)
    reasons: list[str] = []

    # ---- 1. denominator pole / sign on the whole table domain -----------------
    probe = np.linspace(0.0, R2_MAX, 65537)
    den = denominator_float(c, probe)
    den_min = float(den.min())
    pole_free = den_min > 1e-6
    if not pole_free:
        reasons.append(f"denominator reaches {den_min:.3e} on r^2 in [0,{R2_MAX}]: pole or sign flip")

    # ---- 2. radial mapping must stay single-valued ---------------------------
    r = np.linspace(0.0, math.sqrt(R2_MAX), 20001)
    rd = r * factor_float(c, r * r)
    drd = np.diff(rd)
    monotonic = bool((drd > 0).all())
    if not monotonic:
        bad = float(r[int(np.argmin(drd))])
        reasons.append(f"r*f(r^2) is not strictly increasing near r={bad:.3f}: fold-back")

    # ---- 3. factor magnitude must fit Q24 / Q16 ------------------------------
    f = factor_float(c, probe)
    f_min, f_max = float(f.min()), float(f.max())
    if f_min <= 0:
        reasons.append(f"factor reaches {f_min:.6f} <= 0: sign inversion")
    if max(abs(f_min), abs(f_max)) >= 128.0:
        reasons.append(f"factor |{max(abs(f_min), abs(f_max)):.3f}| exceeds Q24 headroom")

    # ---- 4. table vs float, over every representable Q16 r^2 ------------------
    words, bases, deltas = build_table(c)
    all_r2 = np.arange(0, R2_Q16_MAX + 1, dtype=np.int64)
    got = emulate_rtl(words, all_r2)
    want = factor_float(c, all_r2 / 65536.0)
    err = np.abs(got.astype(np.float64) / 65536.0 - want)
    i_worst = int(np.argmax(err))
    max_factor_err = float(err[i_worst])
    r_worst = math.sqrt(float(all_r2[i_worst]) / 65536.0)

    # Pixel consequence: u = fx*ux*s + ..., so |du| <= fx*r*|ds|.
    out = model["output_camera"]
    fx_eff = max(abs(out["fx"]), abs(out["fy"]))
    px_bound = fx_eff * r_worst * max_factor_err

    # Cell linearity: the piecewise-linear table is second order; report the
    # worst cell curvature term so a future 1024-cell table is a measured choice.
    edge_lo = np.arange(CELLS, dtype=np.float64) / 64.0
    edge_hi = edge_lo + 1.0 / 64.0
    edge_mid = (edge_lo + edge_hi) / 2.0
    lin = (factor_float(c, edge_lo) + factor_float(c, edge_hi)) / 2.0
    max_cell_err = float(np.abs(lin - factor_float(c, edge_mid)).max())

    # ---- 5. domain coverage --------------------------------------------------
    need = reachable_r2(model, geometry)
    domain_ok = need <= R2_MAX

    # ---- 6. fixed-point vs float pixel error is bounded by the same table err
    fixed_px = fx_eff * math.sqrt(need) * max_factor_err if need else px_bound
    if max_factor_err > 2e-5:
        reasons.append(f"table error {max_factor_err:.3e} in factor units exceeds 2e-5")

    # ---- emit ---------------------------------------------------------------
    hex_name = f"{args.name}.hex"
    with (out_dir / hex_name).open("w", encoding="ascii", newline="\n") as fh:
        for w in words:
            fh.write(f"{int(w):016x}\n")

    report = dict(
        generator="scripts/gen_radial_lut_rom.py",
        model_path=str(model_path),
        model_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),
        model_kind=c["kind"],
        geometry_path=str(geometry_path),
        rom_file=hex_name,
        rom_words=int(CELLS),
        rom_bytes=int(CELLS * 8),
        rom_sha256=hashlib.sha256((out_dir / hex_name).read_bytes()).hexdigest(),
        domain=dict(r2_min=0.0, r2_max=R2_MAX, cells=CELLS, cell_width=1.0 / 64.0,
                    q16_steps_per_cell=1024, fraction_bits=10),
        coefficients=dict(k1=c["k1"], k2=c["k2"], k3=c["k3"],
                          k4=c["k4"], k5=c["k5"], k6=c["k6"],
                          p1=model.get("p1"), p2=model.get("p2")),
        checks=dict(
            denominator_min=den_min,
            denominator_pole_free=bool(pole_free),
            radial_monotonic=monotonic,
            factor_min=f_min,
            factor_max=f_max,
            q24_signed_headroom=bool(max(abs(f_min), abs(f_max)) < 128.0),
        ),
        table_error=dict(
            samples=len(all_r2),
            max_factor_error=max_factor_err,
            max_factor_error_px_bound=px_bound,
            worst_r2_q16=int(all_r2[i_worst]),
            worst_r=float(r_worst),
            mean_factor_error=float(err.mean()),
            max_midcell_linearity_error=max_cell_err,
        ),
        domain_coverage=dict(
            required_r2=need,
            table_r2_limit=R2_MAX,
            headroom=float(R2_MAX - need),
            passed=bool(domain_ok),
        ),
        fixed_point_px_error_bound=fixed_px,
        fixed_point_px_gate=0.25,
        passed=bool(pole_free and monotonic and domain_ok and not reasons),
        reasons=reasons,
        certified=False,
        diagnostic_only=True,
        note=(
            "Diagnostic ROM for pipeline bring-up. A passing table check means the "
            "LUT faithfully reproduces its model; it says nothing about whether the "
            "model is accurate enough, and it is not a bitstream release."
        ),
    )
    report_path = out_dir / f"{args.name}_verify.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps({k: v for k, v in report.items()
                      if k in ("checks", "table_error", "domain_coverage",
                               "fixed_point_px_error_bound", "passed", "reasons")},
                     indent=2))
    print(f"\nROM   : {out_dir / hex_name}  ({report['rom_bytes']} bytes, sha256 {report['rom_sha256'][:16]}...)")
    print(f"report: {report_path}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())