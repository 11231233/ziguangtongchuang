"""Phone-lens correction + monitor homography. Outputs are INDIRECT estimates."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

import cv2
import numpy as np


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_image(path):
    im = cv2.imdecode(np.frombuffer(Path(path).read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    if im is None:
        raise ValueError('Cannot decode image')
    return im


def validate_points(points, size):
    q = np.asarray(points, np.float64)
    w, h = size
    if q.shape != (4, 2) or not np.isfinite(q).all():
        raise ValueError('Need four finite points: top-left, top-right, bottom-right, bottom-left')
    if np.any(q < 0) or np.any(q[:, 0] >= w) or np.any(q[:, 1] >= h):
        raise ValueError('Monitor corners must be inside the original decoded image')
    if not cv2.isContourConvex(q.astype(np.float32)) or cv2.contourArea(q.astype(np.float32), oriented=True) < 1000:
        raise ValueError('Monitor corners must form a nontrivial clockwise convex quadrilateral')
    if q[:2, 1].mean() >= q[2:, 1].mean() or q[[0, 3], 0].mean() >= q[[1, 2], 0].mean():
        raise ValueError('Wrong corner order; click TL, TR, BR, BL on the ACTIVE display area')
    return q


def rectify(image, points, out, phone_calib=None, mode='RAW', gamma='G0', test_mode='T0'):
    image, out = Path(image), Path(out)
    if out.exists():
        raise ValueError('Output already exists; preserve previous evidence')
    im = load_image(image)
    size = [im.shape[1], im.shape[0]]
    q = validate_points(points, size)
    corrected = im
    calibrated = False
    synthetic = False
    phone = None
    if phone_calib:
        phone_calib = Path(phone_calib)
        phone = json.loads(phone_calib.read_text(encoding='utf-8'))
        if phone.get('image_size') != size:
            raise ValueError('Phone calibration resolution differs; do not silently resize or rescale intrinsics')
        vals = [phone.get(n, float('nan')) for n in ('fx', 'fy', 'cx', 'cy', 'k1', 'k2', 'p1', 'p2')]
        if not np.isfinite(vals).all() or min(vals[:2]) <= 0:
            raise ValueError('Invalid phone calibration')
        k = np.array([[vals[0], 0., vals[2]], [0., vals[1], vals[3]], [0., 0., 1.]])
        d = np.array(vals[4:] + [phone.get('k3', 0.)])
        if not np.isfinite(d).all():
            raise ValueError('Invalid phone distortion coefficients')
        corrected = cv2.undistort(im, k, d, None, k)
        q = cv2.undistortPoints(q.reshape(-1, 1, 2), k, d, P=k).reshape(4, 2)
        validate_points(q, size)
        calibrated = phone.get('source_kind_operator_declared') == 'phone_direct'
        synthetic = bool(phone.get('synthetic_test_data'))
    target = np.array([[0, 0], [1279, 0], [1279, 719], [0, 719]], np.float32)
    transform = cv2.getPerspectiveTransform(q.astype(np.float32), target)
    if not np.isfinite(transform).all() or abs(np.linalg.det(transform)) < 1e-12:
        raise ValueError('Degenerate homography')
    result = cv2.warpPerspective(corrected, transform, (1280, 720), flags=cv2.INTER_LINEAR)
    meta = {'source_kind': 'monitor_rectified', 'indirect_estimate': True,
            'synthetic_test_data': synthetic, 'original_photo': str(image.resolve()),
            'original_photo_sha256': sha(image), 'original_image_size': size,
            'original_corners_TL_TR_BR_BL': np.asarray(points).tolist(),
            'undistorted_corners': q.tolist(), 'homography': transform.tolist(),
            'output_image_size': [1280, 720], 'phone_lens_calibration_declared': calibrated,
            'mode_operator_declared': mode, 'gamma_operator_declared': gamma,
            'test_mode_operator_declared': test_mode,
            'eligible_for_indirect_fit': calibrated and mode == 'RAW' and gamma == 'G0' and test_mode == 'T0',
            'direct_sensor_pixels': False, 'high_precision_calibration_verified': False,
            'limitations': ['Requires same phone lens, resolution, zoom, focus and processing in both stages',
                           'Phone calibration and operator declarations are not physically authenticated',
                           'Display resampling, moire, paper planarity, phone residual distortion and manual corners remain',
                           'Not equivalent to lossless digital capture; not isolated camera MTF or direct lens accuracy']}
    out.mkdir(parents=True)
    cv2.imencode('.png', result)[1].tofile(out / 'screen.png')
    shutil.copy2(image, out / ('source_photo' + image.suffix))
    if phone_calib:
        shutil.copy2(phone_calib, out / 'phone_calibration_snapshot.json')
        meta['phone_calibration_sha256'] = sha(phone_calib)
    meta['output_sha256'] = sha(out / 'screen.png')
    (out / 'metadata.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    return meta


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image', type=Path, required=True)
    p.add_argument('--corners', type=Path, required=True, help='JSON: points, image_size, image_sha256')
    p.add_argument('--phone-calib', type=Path)
    p.add_argument('--mode', choices=['RAW', 'COR'], required=True)
    p.add_argument('--gamma', choices=['G0', 'G1', 'G2', 'G3'], default='G0')
    p.add_argument('--test-mode', choices=['T0', 'T1', 'T2'], default='T0')
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    try:
        spec = json.loads(a.corners.read_text(encoding='utf-8'))
        im = load_image(a.image)
        if spec.get('image_size') != [im.shape[1], im.shape[0]] or spec.get('image_sha256') != sha(a.image):
            raise ValueError('Corner selection belongs to a different photo or resolution')
        meta = rectify(a.image, spec['points'], a.out, a.phone_calib, a.mode, a.gamma, a.test_mode)
    except (OSError, ValueError, KeyError) as e:
        p.error(str(e))
    print(json.dumps({'out': str(a.out), 'indirect_estimate': True,
                      'eligible_for_indirect_fit': meta['eligible_for_indirect_fit']}, indent=2))


if __name__ == '__main__':
    main()
