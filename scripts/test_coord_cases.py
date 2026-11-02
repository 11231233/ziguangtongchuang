"""Multi-case RTL-vs-float check for coord_map.

The main 30-test regression exercises one coefficient set. This script sweeps
several calibrations/angles (empirical S2 Z1, 31.5deg roll, tilt, a realish
calibration shape) through the same RTL testbench and archives the evidence.

It is still a coordinate-map test, not a lens calibration and not a board test.
"""
from pathlib import Path
import datetime
import json
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify import test, p  # noqa: E402

OUT = p / "sim" / "out"


def main():
    from sim_lock import acquire
    _simulation_lock=acquire(p)
    subprocess.run([sys.executable, str(p / "tools/gen_coord_vectors.py"), "--all"], check=True)
    run = p / "sim" / "results" / ("coord_cases_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    run.mkdir(parents=True)
    cases = ["base", "s2z1", "roll31p5", "tilt", "realish"]
    results = []
    for case in cases:
        name = "coord_case_" + case
        ok = test(name, "tb_coord", ["rtl/warp/coord_map.v", "sim/tb/tb_coord.v"],
                  plusargs=["+COEF=sim/out/coord_coef_%s.txt" % case,
                            "+VEC=sim/out/coord_vec_%s.txt" % case])
        for suffix in (".log", "_compile.log"):
            src = OUT / (name + suffix)
            if src.is_file():
                shutil.copy2(src, run / (name + suffix))
        for suffix in (".txt",):
            for kind in ("coord_coef_", "coord_vec_"):
                src = OUT / (kind + case + suffix)
                if src.is_file():
                    shutil.copy2(src, run / src.name)
        values = [int(x, 16) for x in (OUT / ("coord_coef_%s.txt" % case)).read_text().split()]
        signed = lambda v: v - (1 << 32) if v & 0x80000000 else v
        results.append({"case": case, "passed": ok,
                        "A": signed(values[0]), "C": signed(values[2]),
                        "E": signed(values[4]), "F": signed(values[5]),
                        "k1": signed(values[6]), "k2": signed(values[7])})
        if not ok:
            raise SystemExit("FAILED case " + case)
    summary = {"passed": all(r["passed"] for r in results),
               "complete": True,
               "cases": results,
               "note": "RTL coord_map vs float/Q16 vectors; synthetic coefficient sets, not a lens calibration"}
    (run / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print("COORD CASES PASS:", len(results), "cases; evidence:", run, flush=True)


if __name__ == "__main__":
    main()
