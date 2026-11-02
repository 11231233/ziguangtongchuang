"""Measure visible checkerboard line curvature; phone photos are NOT lens calibration."""
import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from checkerboard_detection import detect_checkerboard, CheckerboardNotFound


def line_error(points):
    points = np.asarray(points, dtype=float)
    center = points.mean(axis=0)
    _, _, axes = np.linalg.svd(points - center, full_matrices=False)
    distance = (points - center) @ axes[-1]
    return {'rms_pixels': float(np.sqrt(np.mean(distance ** 2))),
            'max_pixels': float(np.max(np.abs(distance)))}, center, axes[0]


def measure(corners, cols, rows):
    grid = np.asarray(corners).reshape(rows, cols, 2)
    spacing = np.concatenate((np.linalg.norm(np.diff(grid, axis=1), axis=2).ravel(),
                              np.linalg.norm(np.diff(grid, axis=0), axis=2).ravel()))
    lines = []
    for direction, groups in [('row', grid), ('column', grid.transpose(1, 0, 2))]:
        for i, points in enumerate(groups):
            error, _, _ = line_error(points)
            lines.append(dict(direction=direction, index=i, **error))
    scale = float(np.median(spacing))
    return {'lines': lines, 'median_corner_spacing_pixels': scale,
            'mean_line_rms_pixels': float(np.mean([v['rms_pixels'] for v in lines])),
            'max_line_deviation_pixels': max(v['max_pixels'] for v in lines),
            'mean_line_rms_fraction_of_spacing': float(np.mean([v['rms_pixels'] for v in lines])) / scale,
            'interpretation': 'Visible residual line curvature in this supplied image; '
                              'not camera calibration or calibration reprojection RMS. '
                              'Phone lens, paper bending, screen resampling and corner localization also contribute. '
                              'Compare only fixed-camera, fixed-target, fixed-phone captures.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--cols', type=int, required=True, help='INNER corner columns')
    parser.add_argument('--rows', type=int, required=True, help='INNER corner rows')
    parser.add_argument('--out', type=Path, required=True, help='new output directory')
    args = parser.parse_args()
    if min(args.cols, args.rows) < 3:
        parser.error('Need at least three corners per line')
    if args.out.exists():
        parser.error('Output already exists; preserve evidence and choose a new directory')
    image = cv2.imdecode(np.fromfile(args.image, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        parser.error('Cannot decode image')
    try:
        corners = detect_checkerboard(image, (args.cols, args.rows))['points']
    except CheckerboardNotFound as error:
        parser.error(str(error))
    result = measure(corners, args.cols, args.rows)
    result.update(source=str(args.image.resolve()), source_sha256=hashlib.sha256(args.image.read_bytes()).hexdigest(),
                  pattern_inner_corners=[args.cols, args.rows], image_size=[image.shape[1], image.shape[0]],
                  corner_coordinates=corners.reshape(-1, 2).tolist(), actual_supplied_image=True,
                  lens_calibration=False)
    overlay = image.copy()
    grid = corners.reshape(args.rows, args.cols, 2)
    for groups in (grid, grid.transpose(1, 0, 2)):
        for points in groups:
            _, center, axis = line_error(points)
            length = np.linalg.norm(points[-1] - points[0]) / 2
            start = tuple(np.rint(center - axis * length).astype(int))
            end = tuple(np.rint(center + axis * length).astype(int))
            cv2.line(overlay, start, end, (0, 255, 0), 1, cv2.LINE_AA)
    for corner in corners.reshape(-1, 2):
        cv2.circle(overlay, tuple(np.rint(corner).astype(int)), 3, (0, 0, 255), -1)
    args.out.mkdir(parents=True)
    cv2.imencode('.png', overlay)[1].tofile(args.out / 'detected_lines.png')
    (args.out / 'measurement.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('mean_line_rms_pixels', 'max_line_deviation_pixels',
                                                 'mean_line_rms_fraction_of_spacing', 'lens_calibration')}, indent=2))


if __name__ == '__main__':
    main()
