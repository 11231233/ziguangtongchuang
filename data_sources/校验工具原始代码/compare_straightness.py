"""Compare complete checkerboards in RAW/COR images; never claim camera calibration."""
import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from check_board_straightness import measure, line_error
from checkerboard_detection import detect_checkerboard, CheckerboardNotFound


def analyze(path, cols, rows):
    data = path.read_bytes()
    im = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if im is None:
        raise ValueError(f'Cannot decode image: {path}')
    try:
        corners = detect_checkerboard(im, (cols, rows))['points']
    except CheckerboardNotFound as error:
        raise ValueError(f'{error}\n图像：{path}') from None
    result = measure(corners, cols, rows)
    result.update(source=str(path.resolve()), source_sha256=hashlib.sha256(data).hexdigest(),
                  image_size=[im.shape[1], im.shape[0]],
                  corner_coordinates=corners.reshape(-1, 2).tolist())
    grid = corners.reshape(rows, cols, 2)
    for groups in (grid, grid.transpose(1, 0, 2)):
        for points in groups:
            _, center, axis = line_error(points)
            length = np.linalg.norm(points[-1] - points[0]) / 2
            a, b = (tuple(np.rint(center + sign * axis * length).astype(int)) for sign in (-1, 1))
            cv2.line(im, a, b, (0, 255, 0), 1, cv2.LINE_AA)
    for point in corners.reshape(-1, 2):
        cv2.circle(im, tuple(np.rint(point).astype(int)), 3, (0, 0, 255), -1)
    return result, im


def comparison(raw, cor, fixed_setup):
    a, b = (v['mean_line_rms_fraction_of_spacing'] for v in (raw, cor))
    # Tiny baselines make relative percentages misleading. Preserve measured
    # absolute values; this floor is numerical protection, not an acceptance limit.
    relative = 100 * (a - b) / a if fixed_setup and a > 1e-6 else None
    return {'raw_normalized_rms_percent': a * 100,
            'cor_normalized_rms_percent': b * 100,
            'normalized_rms_change_percent_points': (b - a) * 100,
            'relative_reduction_percent': relative,
            'relative_reduction_note': 'Positive means less measured curvature. '
                'Null if fixed setup is unconfirmed or RAW baseline is nearly zero. '
                'This is a relative visible-line metric, not calibration RMS or MTF.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw', type=Path, required=True)
    p.add_argument('--cor', type=Path, required=True)
    p.add_argument('--cols', type=int, required=True)
    p.add_argument('--rows', type=int, required=True)
    p.add_argument('--source', choices=['phone_screen', 'digital_hdmi'], required=True)
    p.add_argument('--fixed-setup-confirmed', action='store_true',
                   help='Operator confirms camera, flat target, phone, zoom and lighting were fixed')
    p.add_argument('--synthetic-test-data', action='store_true', help='Mark tool-test images; never real board evidence')
    p.add_argument('--out', type=Path, required=True, help='New output directory; never overwritten')
    a = p.parse_args()
    if min(a.cols, a.rows) < 3:
        p.error('At least three INNER corners per line are required')
    if a.out.exists():
        p.error('Output exists; preserve evidence and choose a new directory')
    try:
        if a.raw.read_bytes() == a.cor.read_bytes():
            raise ValueError('RAW and COR are the same file content; cannot count as a comparison')
        raw, rim = analyze(a.raw, a.cols, a.rows)
        cor, cim = analyze(a.cor, a.cols, a.rows)
        if raw['image_size'] != cor['image_size']:
            raise ValueError('Image sizes differ; use unchanged capture settings')
        if a.source == 'digital_hdmi' and raw['image_size'] != [1280, 720]:
            raise ValueError('This project requires unresized 1280x720 digital frames')
    except (ValueError, OSError) as e:
        p.error(str(e))
    result = {'source_kind_operator_declared': a.source, 'synthetic_test_data': a.synthetic_test_data,
              'fixed_setup_operator_confirmed': a.fixed_setup_confirmed,
              'pattern_inner_corners': [a.cols, a.rows],
              'lens_calibration': False, 'sensor_intrinsics_estimated': False,
              'quantitative_acceptance_pass': None,
              'limitations': 'No automatic proof of capture provenance or fixed setup. '
                  'Phone lens distortion, screen resampling, paper bending, residual '
                  'pose differences and corner error can affect these numbers. '
                  'A projective view alone preserves straight lines; nonlinear effects do not. '
                  'Independent line fits can hide a global affine/projective change. '
                  'These metrics do not assess absolute sharpness, coverage or calibrated accuracy.',
              'raw': raw, 'cor': cor,
              'comparison': comparison(raw, cor, a.fixed_setup_confirmed)}
    a.out.mkdir(parents=True)
    for name, im in [('raw_lines.png', rim), ('cor_lines.png', cim)]:
        cv2.imencode('.png', im)[1].tofile(a.out / name)
    (a.out / 'measurement.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    c = result['comparison']
    relative_text = ('未计算' if c['relative_reduction_percent'] is None
                     else f'{c["relative_reduction_percent"]:.4f}%')
    rows = '\n'.join(f'| {label} | {v["mean_line_rms_pixels"]:.4f} | '
                     f'{v["max_line_deviation_pixels"]:.4f} | '
                     f'{v["mean_line_rms_fraction_of_spacing"] * 100:.4f}% |'
                     for label, v in [('RAW', raw), ('COR', cor)])
    report = ('# RAW/COR可见直线度对照\n\n'
              + ('合成数据，仅工具验证，不是实机结果。\n\n' if a.synthetic_test_data else '') +
              f'取图方式（人工声明）：{a.source}。固定场景确认：{a.fixed_setup_confirmed}。\n\n'
              '| 画面 | 平均逐线RMS（输入图像像素） | 最大偏离（输入图像像素） | RMS/角点间距 |\n'
              '|---|---:|---:|---:|\n' + rows + '\n\n'
              f'相对减少比例：{relative_text}；固定条件不足或RAW基线接近零时不计算比例。\n\n'
              '本报告不是镜头标定、重投影误差或MTF50，不自动判定赛题精度达标。手机拍屏时像素单位属于照片，'
              '不能当作OV5640传感器像素。绿色拟合线、角点叠加图和原图SHA256用于复核。\n')
    (a.out / 'report.md').write_text(report, encoding='utf-8')
    print(json.dumps(c, indent=2))


if __name__ == '__main__':
    main()
