"""Shared full-pattern detection; partial grids are diagnostic information only."""
import cv2
import numpy as np


class CheckerboardNotFound(ValueError):
    def __init__(self, pattern, attempts):
        self.pattern = tuple(pattern)
        self.attempts = attempts
        cols, rows = self.pattern
        super().__init__(f'未识别到完整的{cols}列×{rows}行内角点（需要{cols * rows}个点，'
                         f'对应{cols + 1}×{rows + 1}个方格）。\n'
                         '请让整个棋盘及四周白边进入画面，移离画面边缘，停稳并避免反光；'
                         '同时核对填写的是内角点数量。')


def _gray(image):
    if image is None or image.dtype != np.uint8 or image.size == 0:
        raise ValueError('棋盘检查需要有效的8位原始图像')
    if image.ndim == 2:
        return np.ascontiguousarray(image)
    if image.ndim == 3 and image.shape[2] == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    raise ValueError('棋盘检查需要灰度图或三通道图像')


def _checked_points(points, pattern, shape):
    if points is None:
        return None
    cols, rows = pattern
    points = np.asarray(points, np.float32)
    if points.size != cols * rows * 2:
        return None
    points = points.reshape(-1, 2)
    height, width = shape
    if (not np.isfinite(points).all() or np.any(points < 0)
            or np.any(points[:, 0] >= width) or np.any(points[:, 1] >= height)):
        return None
    grid = points.reshape(rows, cols, 2)
    horizontal = np.diff(grid, axis=1)
    vertical = np.diff(grid, axis=0)
    if min(np.linalg.norm(horizontal, axis=2).min(),
           np.linalg.norm(vertical, axis=2).min()) < .5:
        return None
    # Each cell must have a consistent orientation, rejecting collapsed or
    # scrambled arrays while allowing perspective and lens curvature.
    a, b = horizontal[:-1], vertical[:, :-1]
    area = a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]
    if not (np.all(area > .01) or np.all(area < -.01)):
        return None
    return np.ascontiguousarray(points)


def detect_checkerboard(image, pattern):
    pattern = tuple(int(x) for x in pattern)
    if len(pattern) != 2 or min(pattern) < 3:
        raise ValueError('棋盘内角点列数和行数均须至少为3')
    gray = _gray(image)
    attempts = []
    if hasattr(cv2, 'findChessboardCornersSB'):
        for method, flags in [
                ('sb', cv2.CALIB_CB_NORMALIZE_IMAGE),
                ('sb_exhaustive_accuracy', cv2.CALIB_CB_NORMALIZE_IMAGE |
                 cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY)]:
            try:
                found, points = cv2.findChessboardCornersSB(gray, pattern, flags=flags)
                points = _checked_points(points, pattern, gray.shape) if found else None
                attempts.append({'method': method, 'found': points is not None})
                if points is not None:
                    # SB already returns subpixel coordinates. Do not run the
                    # classic cornerSubPix over them a second time.
                    return {'points': points, 'method': method, 'attempts': attempts}
            except cv2.error as exc:
                attempts.append({'method': method, 'found': False, 'error': str(exc)})
    try:
        found, points = cv2.findChessboardCorners(gray, pattern,
            cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE)
        if found:
            points = cv2.cornerSubPix(gray, points, (5, 5), (-1, -1),
                (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 40, .001))
            points = _checked_points(points, pattern, gray.shape)
        else:
            points = None
        attempts.append({'method': 'classic_subpixel', 'found': points is not None})
        if points is not None:
            return {'points': points, 'method': 'classic_subpixel', 'attempts': attempts}
    except cv2.error as exc:
        attempts.append({'method': 'classic_subpixel', 'found': False, 'error': str(exc)})
    raise CheckerboardNotFound(pattern, attempts)


def diagnose_partial_board(image):
    """Locate an arbitrary visible grid for feedback, never for calibration."""
    if not hasattr(cv2, 'findChessboardCornersSBWithMeta'):
        return None
    gray = _gray(image)
    try:
        found, points, meta = cv2.findChessboardCornersSBWithMeta(gray, (3, 3),
            flags=cv2.CALIB_CB_NORMALIZE_IMAGE | cv2.CALIB_CB_EXHAUSTIVE |
                  cv2.CALIB_CB_ACCURACY | cv2.CALIB_CB_LARGER)
    except cv2.error:
        return None
    if not found or meta is None:
        return None
    rows, cols = meta.shape
    points = _checked_points(points, (cols, rows), gray.shape)
    if points is None:
        return None
    return {'inner_corners': [cols, rows], 'corner_count': len(points),
            'points': points.tolist(), 'method': 'sb_larger_diagnostic_only',
            'not_accepted_for_calibration': True}
