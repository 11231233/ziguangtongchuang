"""Numerical and CLI tests; all generated images are synthetic, not FPGA evidence."""
from pathlib import Path
import datetime
import json
import subprocess
import sys

import cv2
import numpy as np

p = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(p / 'tools'))
from check_board_straightness import measure
from compare_straightness import comparison

out = p / 'build' / ('synthetic_straightness_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
out.mkdir()

# A projective view of straight lines must remain straight, and normalization
# must be invariant to image scale. Curvature must produce a positive metric.
x, y = np.meshgrid(np.arange(9) * 50., np.arange(5) * 50.)
q = np.stack((x + 300, y + 200), axis=-1)
h = np.array([[1., .12, 40], [-.05, .9, 70], [.0003, -.0002, 1.]])
z = np.concatenate((q, np.ones((*q.shape[:2], 1))), axis=-1) @ h.T
q = z[..., :2] / z[..., 2:]
straight = measure(q, 9, 5)
assert straight['mean_line_rms_pixels'] < 1e-10
curved = q.copy()
curved[..., 1] += .0004 * (q[..., 0] - q[..., 0].mean()) ** 2
c = measure(curved, 9, 5)
assert c['mean_line_rms_pixels'] > .1
assert abs(c['mean_line_rms_fraction_of_spacing'] - measure(curved * 2.3, 9, 5)['mean_line_rms_fraction_of_spacing']) < 1e-12
assert comparison(straight, c, True)['relative_reduction_percent'] is None
assert comparison(c, straight, False)['relative_reduction_percent'] is None

# Actual corner detector + report path, including non-ASCII Windows filenames.
ideal = np.full((720, 1280, 3), 160, np.uint8)
for row in range(6):
    for col in range(10):
        cv2.rectangle(ideal, (240 + col * 80, 120 + row * 80),
                      (240 + (col + 1) * 80 - 1, 120 + (row + 1) * 80 - 1),
                      (0, 0, 0) if (row + col) % 2 == 0 else (255, 255, 255), -1)
k = np.array([[650., 0, 640], [0, 640, 360], [0, 0, 1]])
curved_image = cv2.undistort(ideal, k, np.array([-.23, .06, .001, -.001, 0.]))
for name, im in [('原始合成.png', curved_image), ('矫正合成.png', ideal)]:
    cv2.imencode('.png', im)[1].tofile(out / name)
base = [sys.executable, str(p / 'tools/compare_straightness.py'), '--raw', str(out / '原始合成.png'),
        '--cor', str(out / '矫正合成.png'), '--cols', '9', '--rows', '5',
        '--source', 'phone_screen', '--synthetic-test-data']


def run(extra, expected_ok):
    r = subprocess.run(base + extra, capture_output=True, text=True, encoding='utf-8', errors='replace',
                       env={**__import__('os').environ, 'PYTHONIOENCODING': 'utf-8'})
    assert (r.returncode == 0) == expected_ok, r.stdout + r.stderr
    return r


r = run(['--fixed-setup-confirmed', '--out', str(out / 'fixed')], True)
v = json.loads((out / 'fixed/measurement.json').read_text(encoding='utf-8'))
assert v['synthetic_test_data'] and not v['lens_calibration']
assert v['comparison']['relative_reduction_percent'] > 90
assert v['raw']['source_sha256'] != v['cor']['source_sha256']
run(['--out', str(out / 'unconfirmed')], True)
assert json.loads((out / 'unconfirmed/measurement.json').read_text(encoding='utf-8'))['comparison']['relative_reduction_percent'] is None
run(['--out', str(out / 'fixed')], False)
run(['--cor', str(out / '原始合成.png'), '--out', str(out / 'same')], False)
assert not (out / 'same').exists()
cv2.imencode('.png', np.zeros((720, 1280, 3), np.uint8))[1].tofile(out / 'blank.png')
run(['--cor', str(out / 'blank.png'), '--out', str(out / 'blank')], False)
assert not (out / 'blank').exists()
(out / 'test_result.json').write_text(json.dumps({'passed': True, 'synthetic_test_data': True,
    'not_actual_board_measurement': True,
    'checks': ['projective lines', 'normalized scale invariance', 'curvature detection', 'tiny baseline guard',
               'CLI detector/report', 'Chinese paths', 'unconfirmed setup suppresses percentage',
               'no overwrite', 'duplicate input rejection', 'missing board rejection']}, indent=2), encoding='utf-8')
print('STRAIGHTNESS PASS: numeric invariants and CLI; SYNTHETIC ONLY', out)
