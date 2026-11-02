"""Independent ideal geometry versus host/export/CV; no hardware operations."""
from pathlib import Path
import json
import math
import subprocess
import sys
import tempfile
import unittest

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from host_control import coefficients
from calib_to_fpga import quantized_error
from warp_model import CamParams, OutGeom, WarpParams, s32


def measured_values():
    # Regression values from a locally measured model; tests make no claim
    # about its physical accuracy and send nothing to an FPGA.
    return dict(fx=319.27163278242404, fy=319.74124154033683,
                cx=641.3706264989074, cy=381.30715070581033,
                k1=-0.052046863929536724, k2=0.00419732533153469,
                p1=0.010278978111041762, p2=-0.0008922687315533415,
                k3=0.0, image_size=[1280, 720], source_kind_operator_declared='synthetic')


def camera(values):
    return CamParams(**{k: values[k] for k in ('fx', 'fy', 'cx', 'cy', 'k1', 'k2', 'p1', 'p2')})


def output(values):
    return OutGeom(fx=values['fx'], fy=values['fy'], cx=values['cx'], cy=values['cy'])


def distort(values, ux, uy):
    radius = ux**2 + uy**2
    radial = 1 + radius * (values['k1'] + values['k2'] * radius)
    return (values['fx'] * (ux * radial + 2 * values['p1'] * ux * uy +
                            values['p2'] * (3 * ux**2 + uy**2)) + values['cx'],
            values['fy'] * (uy * radial + values['p1'] * (ux**2 + 3 * uy**2) +
                            2 * values['p2'] * ux * uy) + values['cy'])


def independent_ideal(values, out, x, y, roll=0, yaw=0, pitch=0, zoom=1, H=None):
    """Direct camera/rotation equations, without WarpParams or Q16 helpers."""
    nx = (np.asarray(x, np.float64) - out.cx) / out.fx
    ny = (np.asarray(y, np.float64) - out.cy) / out.fy
    if H is None:
        # Rotate Rx, then Ry, then Rz. Like the FPGA affine approximation,
        # keep the first two coordinates without dividing by rotated z.
        r, ya, pi = map(math.radians, (roll, yaw, pitch))
        rx_x = nx
        rx_y = math.cos(pi) * ny - math.sin(pi)
        rx_z = math.sin(pi) * ny + math.cos(pi)
        ry_x = math.cos(ya) * rx_x + math.sin(ya) * rx_z
        ry_y = rx_y
        ux = (math.cos(r) * ry_x - math.sin(r) * ry_y) / zoom
        uy = (math.sin(r) * ry_x + math.cos(r) * ry_y) / zoom
    else:
        ux = H[0][0] * nx + H[0][1] * ny + H[0][2]
        uy = H[1][0] * nx + H[1][1] * ny + H[1][2]
    return distort(values, ux, uy)


def independent_quantized(coeff, x, y):
    q = {k: s32(v) / 65536.0 for k, v in coeff.items()}
    ux = q['A'] * x + q['B'] * y + q['C']
    uy = q['D'] * x + q['E'] * y + q['F']
    return distort(q, ux, uy)


def independent_error(values, coeff, out, **transform):
    xs = np.unique(np.r_[np.arange(0, out.width, 32), out.width - 1]).astype(np.float64)
    ys = np.unique(np.r_[np.arange(0, out.height, 32), out.height - 1]).astype(np.float64)
    x, y = np.meshgrid(xs, ys)
    ideal = independent_ideal(values, out, x, y, **transform)
    quantized = independent_quantized(coeff, x, y)
    return np.hypot(quantized[0] - ideal[0], quantized[1] - ideal[1])


class MappingConsistency(unittest.TestCase):
    def test_host_and_exporter_share_measured_principal_point(self):
        values = measured_values()
        out = output(values)
        for transform in ({}, dict(roll=8.0, yaw=3.0, pitch=-2.0, zoom=1.15)):
            with self.subTest(transform=transform):
                wp = WarpParams(cam=camera(values), out=out,
                    roll_deg=transform.get('roll', 0), yaw_deg=transform.get('yaw', 0),
                    pitch_deg=transform.get('pitch', 0), zoom=transform.get('zoom', 1))
                exported = {k: s32(v) for k, v in wp.coeffs().items()}
                self.assertEqual(coefficients(values, **transform), exported)

    def test_ideal_zero_angle_matches_opencv_same_K(self):
        values = measured_values()
        out = output(values)
        K = np.array([[values['fx'], 0, values['cx']],
                      [0, values['fy'], values['cy']], [0, 0, 1.]])
        d = np.array([values[k] for k in ('k1', 'k2', 'p1', 'p2')] + [0.])
        cv_u, cv_v = cv2.initUndistortRectifyMap(K, d, None, K, (1280, 720), cv2.CV_32FC1)
        x, y = np.meshgrid(np.arange(0, 1280, 127), np.arange(0, 720, 71))
        wp = WarpParams(cam=camera(values), out=out)
        expected = independent_ideal(values, out, x, y)
        actual = wp.map_pixels_ideal(x, y)
        np.testing.assert_allclose(actual, expected, atol=1e-10, rtol=0)
        np.testing.assert_allclose(actual[0], cv_u[y, x], atol=6.2e-5, rtol=0)
        np.testing.assert_allclose(actual[1], cv_v[y, x], atol=6.2e-5, rtol=0)

    def test_nonzero_transform_uses_unquantized_affine_reference(self):
        values = measured_values(); out = output(values)
        transform = dict(roll=8.0, yaw=3.0, pitch=-2.0, zoom=1.15)
        wp = WarpParams(cam=camera(values), out=out, roll_deg=8, yaw_deg=3,
                        pitch_deg=-2, zoom=1.15)
        x = np.array([0., 123., 641., 1279.]); y = np.array([0., 719., 381., 333.])
        np.testing.assert_allclose(wp.map_pixels_ideal(x, y),
            independent_ideal(values, out, x, y, **transform), atol=1e-10, rtol=0)
        coeff = wp.coeffs()
        report = quantized_error(values, coeff, out, **transform)
        error = independent_error(values, coeff, out, **transform)
        self.assertAlmostEqual(report['max_px'], float(error.max()), places=9)
        self.assertAlmostEqual(report['mean_px'], float(error.mean()), places=9)
        self.assertAlmostEqual(report['p95_px'], float(np.percentile(error, 95)), places=9)

    def test_custom_H_is_the_actual_reference(self):
        values = measured_values(); out = output(values)
        H = [[.91, -.04, .025], [.03, .95, -.02], [0., 0., 1.]]
        wp = WarpParams(cam=camera(values), out=out, H=H)
        report = quantized_error(values, wp.coeffs(), out, H=H)
        error = independent_error(values, wp.coeffs(), out, H=H)
        self.assertAlmostEqual(report['max_px'], float(error.max()), places=9)

    def test_affine_quantization_over_threshold_is_reported_false(self):
        values = measured_values(); out = output(values)
        coeff = coefficients(values)
        report = quantized_error(values, coeff, out)
        error = independent_error(values, coeff, out)
        self.assertEqual(coeff['A'], 205)
        self.assertGreater(report['max_px'], 1.0)
        self.assertAlmostEqual(report['max_px'], float(error.max()), places=9)
        self.assertEqual(report['threshold_px'], .25)
        self.assertFalse(report['passed'])
        self.assertTrue(report['includes_affine_quantization'])

    def test_legacy_map_pixels_keeps_its_quantized_affine_semantics(self):
        values = measured_values(); out = output(values)
        wp = WarpParams(cam=camera(values), out=out)
        x = np.array([0., 640., 1279.]); y = np.array([0., 360., 719.])
        coeff = {k: s32(v) / 65536. for k, v in wp.coeffs().items()}
        ux = coeff['A'] * x + coeff['B'] * y + coeff['C']
        uy = coeff['D'] * x + coeff['E'] * y + coeff['F']
        np.testing.assert_allclose(wp.map_pixels(x, y), distort(values, ux, uy),
                                   atol=1e-10, rtol=0)
        legacy = wp.map_pixels(x, y); ideal = wp.map_pixels_ideal(x, y)
        self.assertGreater(float(np.hypot(legacy[0]-ideal[0], legacy[1]-ideal[1]).max()), 1.)

    def test_cli_nonzero_transform_reports_same_error_and_warns(self):
        values = measured_values(); out = output(values)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp); model = folder / 'model.json'; target = folder / 'export'
            model.write_text(json.dumps(values), encoding='utf-8')
            transform = dict(roll=8., yaw=3., pitch=-2., zoom=1.15)
            run = subprocess.run([sys.executable, str(ROOT / 'tools/calib_to_fpga.py'),
                '--calib', str(model), '--out-dir', str(target), '--allow-synthetic',
                '--roll', '8', '--yaw', '3', '--pitch', '-2', '--zoom', '1.15'],
                capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            exported = json.loads((target / 'coeff.json').read_text(encoding='utf-8'))
            coeff = exported['coeff_signed']
            self.assertEqual(coeff, coefficients(values, **transform))
            expected = float(independent_error(values, coeff, out, **transform).max())
            report = exported['quantization_error']
            self.assertAlmostEqual(report['max_px'], expected, places=9)
            self.assertEqual(report['passed'], expected <= .25)
            self.assertEqual(report['threshold_px'], .25)
            if expected > .25:
                self.assertIn('WARNING:', run.stderr)


if __name__ == '__main__':
    unittest.main()
