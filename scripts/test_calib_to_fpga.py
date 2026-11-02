"""Unit/integration checks for the calibration -> FPGA coefficient exporter.

Synthetic data only. This test proves the tool contract; it is not a lens calibration.
"""
from pathlib import Path
import binascii
import json
import subprocess
import sys
import tempfile
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from calib_to_fpga import quantized_error  # noqa: E402
from warp_model import CamParams, OutGeom, WarpParams, s32  # noqa: E402


def write_calib(path: Path, **over):
    data = dict(fx=520.0, fy=520.0, cx=640.0, cy=360.0, k1=0.0, k2=0.0, p1=0.0, p2=0.0,
                k3=0.0, rms=0.0, image_size=[1280, 720], frames_used=12,
                source_kind_operator_declared="synthetic",
                calibration_scope="source_declared_in_metadata",
                high_precision_calibration_verified=False)
    data.update(over)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="calib_to_fpga_"))
    good = tmp / "good.json"
    write_calib(good)
    out = tmp / "out"
    r = subprocess.run([sys.executable, str(ROOT / "tools/calib_to_fpga.py"),
                        "--calib", str(good), "--out-dir", str(out), "--allow-synthetic"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    coeff = json.loads((out / "coeff.json").read_text(encoding="utf-8"))
    c = coeff["coeff_signed"]
    assert c["A"] == 126 and c["C"] == -80660, c
    assert c["fx"] == 520 << 16 and c["cx"] == 640 << 16
    assert coeff["geometry_guard"]["window_misses"] == 0
    # Compare with the unquantized identity, rather than a reference that has
    # already rounded A..F. Even fx=520 has >0.25px full-field Q16 slope error.
    xs, ys = np.meshgrid([0.0, 1279.0], [0.0, 719.0])
    uq = (c['A'] * xs + c['C']) / 65536 * 520 + 640
    vq = (c['E'] * ys + c['F']) / 65536 * 520 + 360
    expected_error = float(np.hypot(uq - xs, vq - ys).max())
    qerr = coeff['quantization_error']
    assert abs(qerr['max_px'] - expected_error) < 1e-9, (qerr, expected_error)
    assert qerr['threshold_px'] == 0.25 and expected_error > 0.25
    assert qerr['passed'] is False and 'WARNING:' in r.stderr

    packet = (out / "packet.bin").read_bytes()
    assert len(packet) == 62 and packet[:4] == b"\xa5\x5a\x01\x01"
    assert int.from_bytes(packet[-2:], "big") == binascii.crc_hqx(packet[2:-2], 0xFFFF)

    # 1:1 mapping: output (0,0) -> source (0,0), (W-1,H-1) -> (W-1,H-1)
    wp = WarpParams(cam=CamParams(fx=520, fy=520, k1=0, k2=0, p1=0, p2=0),
                    out=OutGeom(fx=520, fy=520))
    u, v = wp.map_pixels(__import__("numpy").array([[0.0, 1279.0]]),
                         __import__("numpy").array([[0.0, 719.0]]))
    # Q16 A=126 is 65536/520 rounded; accept sub-pixel quantization, not exact float equality.
    assert abs(float(u[0, 0])) < 0.5 and abs(float(v[0, 0])) < 0.5, (u, v)
    assert abs(float(u[0, 1]) - 1279.0) < 0.5 and abs(float(v[0, 1]) - 719.0) < 0.5, (u, v)

    # The empirical S2 Z1 profile must be reproducible from fx=520 + zoom=1.25.
    s2 = tmp / "s2z1.json"
    write_calib(s2, k1=-0.40, k2=0.12)
    s2out = tmp / "s2z1_out"
    r = subprocess.run([sys.executable, str(ROOT / "tools/calib_to_fpga.py"),
                        "--calib", str(s2), "--out-dir", str(s2out),
                        "--zoom", "1.25", "--allow-synthetic"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    s2c = json.loads((s2out / "coeff.json").read_text(encoding="utf-8"))["coeff_signed"]
    assert (s2c["A"], s2c["C"], s2c["E"], s2c["F"]) == (101, -64528, 101, -36297), s2c
    assert (s2c["k1"], s2c["k2"]) == (-26214, 7864), s2c
    assert s2c["fx"] == 520 << 16 and s2c["cx"] == 640 << 16

    # Phone model must not silently become an OV5640 coefficient set.
    phone = tmp / "phone.json"
    write_calib(phone, source_kind_operator_declared="phone_direct",
                calibration_scope="phone_camera", image_size=[1080, 2344])
    bad = subprocess.run([sys.executable, str(ROOT / "tools/calib_to_fpga.py"),
                          "--calib", str(phone), "--out-dir", str(tmp / "phone_out")],
                         capture_output=True, text=True)
    assert bad.returncode != 0 and not (tmp / "phone_out").exists()

    # k3 must be rejected, not silently dropped.
    k3 = tmp / "k3.json"
    write_calib(k3, k3=0.01)
    bad = subprocess.run([sys.executable, str(ROOT / "tools/calib_to_fpga.py"),
                          "--calib", str(k3), "--out-dir", str(tmp / "k3_out"), "--allow-synthetic"],
                         capture_output=True, text=True)
    assert bad.returncode != 0 and not (tmp / "k3_out").exists()

    print("CALIB_TO_FPGA PASS: identity A=126/C=-80660, honest quantization warning, "
          "62-byte CRC packet, geometry guard, phone/k3 rejection; synthetic only", tmp)


if __name__ == "__main__":
    main()
