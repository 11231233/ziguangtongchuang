"""Offline checks for the host angle sweep; no serial hardware needed."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write_calib(path: Path):
    path.write_text(json.dumps(dict(
        fx=520.0, fy=520.0, cx=640.0, cy=360.0, k1=0.0, k2=0.0, p1=0.0, p2=0.0,
        k3=0.0, image_size=[1280, 720], frames_used=12,
        source_kind_operator_declared="synthetic",
        calibration_scope="source_declared_in_metadata")), encoding="utf-8")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="host_sweep_"))
    calib = tmp / "calib.json"
    write_calib(calib)
    out = tmp / "sweep"
    r = subprocess.run([sys.executable, str(ROOT / "tools/host_sweep.py"),
                        "--calib", str(calib), "--out-dir", str(out),
                        "--amplitude", "12", "--hz", "0.25", "--duration", "2", "--fps", "10",
                        "--allow-synthetic"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    summary = json.loads((out / "sweep.json").read_text(encoding="utf-8"))
    timeline = json.loads((out / "timeline.json").read_text(encoding="utf-8"))
    assert summary["packets"] == 21 and summary["offline_only"] is True
    assert len(timeline) == 21
    frames = sorted(out.glob("frame_*.bin"))
    assert len(frames) == 21 and all(f.stat().st_size == 62 for f in frames)
    assert all(abs(p["roll_deg"]) <= 12.0 + 1e-9 for p in timeline)
    seqs = [p["sequence"] for p in timeline]
    assert seqs == list(range(1, 22))
    for f in frames:
        b = f.read_bytes()
        assert b[:2] == b"\xa5\x5a" and b[2] == 1

    phone = tmp / "phone.json"
    data = json.loads(calib.read_text(encoding="utf-8"))
    data["source_kind_operator_declared"] = "phone_direct"
    phone.write_text(json.dumps(data), encoding="utf-8")
    bad = subprocess.run([sys.executable, str(ROOT / "tools/host_sweep.py"),
                          "--calib", str(phone), "--out-dir", str(tmp / "bad")],
                         capture_output=True, text=True)
    assert bad.returncode != 0 and not (tmp / "bad").exists()

    print("HOST_SWEEP PASS: 21 packets, 62 bytes, roll within +/-12, seq 1..21, phone rejected; offline only", tmp)


if __name__ == "__main__":
    main()
