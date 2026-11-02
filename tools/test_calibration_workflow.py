"""Synthetic tool checks only; never evidence of real lens/board accuracy."""
import argparse
import json
from pathlib import Path
import sys

import cv2
import numpy as np

import calibration_workflow as f


def board_image(index, K, d):
    rng = np.random.default_rng(1000 + index)
    rv = rng.uniform([-.45, -.45, -.3], [.45, .45, .3])
    R, _ = cv2.Rodrigues(rv)
    depth = rng.uniform(520, 770)
    center = np.array([rng.uniform(-180, 180), rng.uniform(-90, 90), depth])
    tv = center - R @ np.array([100, 62.5, 0])
    im = np.full((1440, 2560, 3), 190, np.uint8)
    for y in range(-1, 6):
        for x in range(-1, 9):
            shape = []
            for a, b in [((x, y), (x + 1, y)), ((x + 1, y), (x + 1, y + 1)),
                         ((x + 1, y + 1), (x, y + 1)), ((x, y + 1), (x, y))]:
                for t in np.linspace(0, 1, 10, endpoint=False):
                    shape.append([(a[0] * (1 - t) + b[0] * t) * 25,
                                  (a[1] * (1 - t) + b[1] * t) * 25, 0])
            pts, _ = cv2.projectPoints(np.array(shape), rv, tv, K, d)
            points = np.rint(pts.reshape(-1, 2) * 2).astype(np.int32)
            shade = 15 if (x + y) % 2 == 0 else 245
            cv2.fillPoly(im, [points], (shade, shade, shade), lineType=cv2.LINE_AA)
    im = cv2.resize(im, (1280, 720), interpolation=cv2.INTER_AREA)
    cv2.putText(im, 'SYNTHETIC TOOL TEST - NOT HARDWARE', (20, 700), cv2.FONT_HERSHEY_SIMPLEX, .65, (30, 30, 180), 2)
    return im


def must_fail(fn, text):
    try:
        fn()
    except (ValueError, FileNotFoundError):
        return
    raise AssertionError('Expected rejection: ' + text)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--out', type=Path)
    a = ap.parse_args()
    out = a.out or f.ROOT / 'reports/revision4' / ('software_test_' + f.stamp())
    out.mkdir(parents=True, exist_ok=False)
    session = out / 'synthetic_session'
    model = dict(fx=800., fy=790., cx=640., cy=360., k1=-.23, k2=.06, p1=.002, p2=-.001,
                 image_size=[1280, 720], synthetic_test_data=True, source_kind_operator_declared='synthetic')
    K, d = f.camera_matrix(model)
    must_fail(lambda: f.create_session(session, 'C1', 9, 6, 25, False), 'unconfirmed provenance')
    f.create_session(session, 'C1', 9, 6, 25, True, synthetic=True)
    for i in range(24):
        f.save_frame(session, board_image(i, K, d), 'train' if i < 18 else 'validation', 'synthetic_projected_board_' + str(i))
    data = f.load_session(session)
    assert len(data['frames']) == 24
    im = f.read_image(session / data['frames'][0]['file'])
    must_fail(lambda: f.save_frame(session, im, 'validation', 'duplicate'), 'train/validation overlap')
    must_fail(lambda: f.save_frame(session, im[:360], 'train', 'resized'), 'wrong size')
    must_fail(lambda: f.save_frame(session, np.zeros_like(im), 'train', 'no board'), 'missing checkerboard')
    good = f.validate(session, model, out / 'known_model_validation')
    bad = f.validate(session, dict(model, k1=0, k2=0, p1=0, p2=0), out / 'incorrect_model_validation')
    assert good['held_out_reprojection_rms_px'] < .65, good
    assert bad['held_out_reprojection_rms_px'] > good['held_out_reprojection_rms_px'] * 1.5, (good, bad)
    overlap = dict(model, input_images_sha256={'bad': data['frames'][-1]['sha256']})
    must_fail(lambda: f.validate(session, overlap, out / 'must_not_pass'), 'training hash in validation')
    corrected = f.remap_preview(im, model)
    frontal = f.plane_preview(im, model, (9, 6))
    assert corrected.shape == im.shape == frontal.shape
    cv2.imencode('.png', corrected)[1].tofile(out / 'synthetic_corrected_preview.png')
    cv2.imencode('.png', frontal)[1].tofile(out / 'synthetic_plane_preview.png')
    result_dir, report = f.calibrate(session)
    estimated = json.loads((result_dir / 'calibration.json').read_text(encoding='utf-8'))
    assert estimated['synthetic_test_data'] and estimated['source_kind_operator_declared'] == 'synthetic'
    assert abs(estimated['fx'] / model['fx'] - 1) < .08
    assert abs(estimated['fy'] / model['fy'] - 1) < .08
    assert report['held_out_reprojection_rms_px'] < .8, report
    assert not f.load_session(session)['real_lens_calibration_complete']
    from prepare_calibrated_project import prepare
    must_fail(lambda: prepare(result_dir / 'calibration.json', result_dir / 'validation/validation.json', out / 'rejected_synthetic'), 'synthetic static project')
    static = out / 'synthetic_static_project'
    record = prepare(result_dir / 'calibration.json', result_dir / 'validation/validation.json', static, allow_synthetic_test=True)
    top = (static / 'rtl/top/top_pangu50.v').read_text(encoding='utf-8')
    assert record['synthetic_test_data'] and not record['hardware_tested']
    assert ".key_n({key3,1'b1,1'b1,key0})" in top
    assert 'metrics_osd #(.SINGLE_CAMERA(1))' in top and 'cam2_pclk' not in top
    # image30 exposes four modes and natural-detail control. Check the actual
    # current instance, rather than the older single-parameter instantiation.
    assert 'quality_display #(.DEFAULT_MODE(2),.MAX_MODE(3),.NATURAL_DETAIL(1)) u_quality_display' in top
    assert '(local_correction_active?' in top and record['coefficients']['p1'] != 0
    # A fusion-default source must also generate an explicitly locked C2
    # project; neither output may silently retain fusion mode.
    c2_model = dict(estimated, camera='C2')
    c2_report = dict(report, camera='C2')
    f.write_json(out / 'synthetic_c2_model.json', c2_model)
    f.write_json(out / 'synthetic_c2_validation.json', c2_report)
    must_fail(lambda: prepare(out / 'synthetic_c2_model.json', out / 'synthetic_c2_validation.json',
            out / 'synthetic_static_project_c2', allow_synthetic_test=True), 'C2 model on C1-only hardware')
    assert not (out / 'synthetic_static_project_c2').exists()
    changed = dict(json.loads((result_dir / 'validation/validation.json').read_text(encoding='utf-8')),
                   model_parameters_sha256='wrong')
    f.write_json(out / 'wrong_model_validation.json', changed)
    must_fail(lambda: prepare(result_dir / 'calibration.json', out / 'wrong_model_validation.json', out / 'mismatch_project', True), 'model/report mismatch')
    # An input edit must invalidate the saved session, not silently train on it.
    image_path = session / data['frames'][0]['file']
    original = image_path.read_bytes(); image_path.write_bytes(original + b'changed')
    must_fail(lambda: f.check_files(session, f.load_session(session)), 'tampered file')
    image_path.write_bytes(original)
    summary = {'passed': True, 'synthetic_test_data': True, 'hardware_tested': False,
        'checks': ['strict source confirmation', '24 distinct checkerboards', '18/6 training/validation split',
                   'duplicate rejection', 'wrong-size rejection', 'missing-board rejection',
                   'held-out pose-only residual', 'incorrect distortion scores worse', 'overlap hash rejection',
                   'same-scale remap', 'known-plane perspective preview', 'full calibration subprocess',
                   'parameter recovery within 8 percent', 'synthetic label retained', 'tamper rejection',
                   'synthetic deployment rejected by default', 'static single-camera project preserves tangential terms',
                   'static profile locks camera/zoom', 'C2 model rejected on C1-only hardware',
                   'Q2 display retained in generated profiles', 'model/report binding'],
        'known_model_holdout_rms_px': good['held_out_reprojection_rms_px'],
        'incorrect_model_holdout_rms_px': bad['held_out_reprojection_rms_px'],
        'estimated_model_holdout_rms_px': report['held_out_reprojection_rms_px'],
        'estimated_fx_fy': [estimated['fx'], estimated['fy']], 'reference_fx_fy': [800, 790],
        'result_folder': str(result_dir)}
    f.write_json(out / 'summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
