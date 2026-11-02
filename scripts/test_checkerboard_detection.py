"""Full-board regression and diagnostic evidence; synthetic data are tool tests."""
from pathlib import Path
import json
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

from checkerboard_detection import (CheckerboardNotFound, detect_checkerboard,
                                   diagnose_partial_board)
import calibration_workflow as flow

USER_FRAME = Path('F:/chuankou/digital_20261029_202857_731998.png')
PATTERN = (9, 6)


def full_board(perspective=False, dark=False):
    """A complete 10x7-square board provides 9x6 inner corners, plus margin."""
    cell = 60
    board = np.full((620, 800, 3), 240, np.uint8)
    for y in range(7):
        for x in range(10):
            value = 12 if (x + y) % 2 == 0 else 245
            board[100+y*cell:100+(y+1)*cell,
                  100+x*cell:100+(x+1)*cell] = value
    if perspective:
        source = np.float32([[0, 0], [799, 0], [799, 619], [0, 619]])
        target = np.float32([[90, 65], [1190, 100], [1100, 690], [170, 625]])
        matrix = cv2.getPerspectiveTransform(source, target)
        image = cv2.warpPerspective(board, matrix, (1280, 720), borderValue=(230, 230, 230))
    else:
        image = np.full((720, 1280, 3), 240, np.uint8)
        image[50:670, 240:1040] = board
    if dark:
        image = np.clip(image.astype(np.float32) * .19 + 5, 0, 255).astype(np.uint8)
    return image


def regular_points(cols, rows):
    points = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2).astype(np.float32)
    return points * np.float32(50) + np.float32([150, 140])


class CheckerboardDetection(unittest.TestCase):
    def assert_complete(self, image, pattern=PATTERN):
        original = image.copy()
        result = detect_checkerboard(image, pattern)
        points = result['points']
        self.assertEqual(points.shape, (pattern[0] * pattern[1], 2))
        self.assertEqual(points.dtype, np.float32)
        self.assertTrue(np.isfinite(points).all())
        self.assertTrue(result['method'])
        self.assertIsInstance(result['attempts'], list)
        self.assertTrue(result['attempts'])
        np.testing.assert_array_equal(image, original)
        return result

    def assert_not_complete(self, image, pattern=PATTERN):
        original = image.copy()
        with self.assertRaises(CheckerboardNotFound) as raised:
            detect_checkerboard(image, pattern)
        self.assertEqual(raised.exception.pattern, tuple(pattern))
        self.assertIsInstance(raised.exception.attempts, list)
        self.assertTrue(raised.exception.attempts)
        np.testing.assert_array_equal(image, original)

    def test_complete_plain_and_perspective(self):
        for perspective in (False, True):
            with self.subTest(perspective=perspective):
                self.assert_complete(full_board(perspective=perspective))

    def test_dark_perspective_board(self):
        self.assert_complete(full_board(perspective=True, dark=True))

    def test_blank_and_half_board_are_rejected(self):
        self.assert_not_complete(np.full((720, 1280, 3), 127, np.uint8))
        image = full_board()
        image[:, 640:] = 240
        self.assert_not_complete(image)

    @unittest.skipUnless(hasattr(cv2, 'findChessboardCornersSB'), 'OpenCV SB not available')
    def test_sb_accepts_both_point_shapes(self):
        image = full_board()
        points = regular_points(*PATTERN)
        for shape in ((54, 2), (54, 1, 2)):
            with self.subTest(shape=shape), \
                 patch('checkerboard_detection.cv2.findChessboardCornersSB',
                       return_value=(True, points.reshape(shape))) as sb, \
                 patch('checkerboard_detection.cv2.findChessboardCorners',
                       return_value=(False, None)) as classic:
                result = self.assert_complete(image)
            sb.assert_called_once()
            classic.assert_not_called()
            np.testing.assert_allclose(result['points'], points)

    @unittest.skipUnless(hasattr(cv2, 'findChessboardCornersSB'), 'OpenCV SB not available')
    def test_36_partial_points_never_become_54_training_corners(self):
        partial = regular_points(6, 6)
        with patch('checkerboard_detection.cv2.findChessboardCornersSB',
                   return_value=(True, partial.reshape(-1, 1, 2))), \
             patch('checkerboard_detection.cv2.findChessboardCorners', return_value=(False, None)):
            self.assert_not_complete(full_board(), PATTERN)

    @unittest.skipUnless(hasattr(cv2, 'findChessboardCornersSB'), 'OpenCV SB not available')
    def test_scrambled_full_count_is_rejected(self):
        points = regular_points(*PATTERN)
        points[[1, 2]] = points[[2, 1]]
        with patch('checkerboard_detection.cv2.findChessboardCornersSB', return_value=(True, points)), \
             patch('checkerboard_detection.cv2.findChessboardCorners', return_value=(False, None)):
            self.assert_not_complete(full_board())

    def test_workflow_uses_shared_detector(self):
        points = regular_points(*PATTERN)
        with patch('calibration_workflow.detect_checkerboard',
                   return_value={'points': points, 'method': 'test', 'attempts': []}) as detector:
            result = flow.corners(full_board(), PATTERN)
        detector.assert_called_once()
        np.testing.assert_array_equal(result, points)

    def test_complete_check_saves_unmodified_original_and_overlay(self):
        image = full_board(perspective=True)
        original = image.copy()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'check'
            report = flow.check_checkerboard(image, PATTERN, out)
            self.assertTrue(report['found'])
            self.assertEqual(report['detected_count'], 54)
            self.assertFalse(report['training_frame_saved'])
            self.assertFalse(report['partial_grid_is_training_data'])
            self.assertEqual(json.loads(json.dumps(report)),
                             json.loads((out / 'report.json').read_text(encoding='utf-8')))
            np.testing.assert_array_equal(flow.read_image(out / 'original.png'), original)
            self.assertTrue((out / 'overlay.png').is_file())
            self.assertFalse(np.array_equal(flow.read_image(out / 'overlay.png'), original))
        np.testing.assert_array_equal(image, original)

    @unittest.skipUnless(USER_FRAME.is_file(), 'User digital frame is local evidence')
    def test_user_6x9_failure_keeps_evidence_without_adding_training_frame(self):
        image = flow.read_image(USER_FRAME)
        original = image.copy()
        self.assertEqual(image.shape, (720, 1280, 3))
        self.assert_not_complete(image, (6, 9))
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'session'
            # A temporary tool-test session cannot be promoted to real evidence.
            flow.create_session(folder, 'C1', 6, 9, 20.0, confirmed=True, synthetic=True)
            before = (folder / 'session.json').read_bytes()
            with self.assertRaises(ValueError) as raised:
                flow.save_frame(folder, image, 'train', str(USER_FRAME))
            reports = list((folder / 'diagnostics').glob('checkerboard_*/report.json'))
            self.assertEqual(len(reports), 1)
            out = reports[0].parent
            self.assertIn(str(reports[0].resolve()), str(raised.exception))
            self.assertIn('完整', str(raised.exception))
            self.assertEqual((folder / 'session.json').read_bytes(), before)
            self.assertEqual(flow.load_session(folder)['frames'], [])
            self.assertEqual(list((folder / 'train').iterdir()), [])
            report = json.loads(reports[0].read_text(encoding='utf-8'))
            self.assertFalse(report['found'])
            self.assertEqual(report['expected_count'], 54)
            self.assertEqual(report['detected_count'], 0)
            self.assertFalse(report['training_frame_saved'])
            self.assertFalse(report['partial_grid_is_training_data'])
            partial = report.get('partial_candidate')
            if partial:
                self.assertTrue(partial['not_accepted_for_calibration'])
                self.assertLess(partial['corner_count'], 54)
            np.testing.assert_array_equal(flow.read_image(out / 'original.png'), original)
            self.assertTrue((out / 'overlay.png').is_file())
        np.testing.assert_array_equal(image, original)

    def test_partial_grid_diagnostic_is_explicitly_not_training(self):
        image = full_board()
        before = image.copy()
        candidate = diagnose_partial_board(image)
        self.assertTrue(candidate is None or isinstance(candidate, dict))
        if candidate:
            self.assertTrue(candidate['not_accepted_for_calibration'])
            self.assertEqual(len(candidate['points']), candidate['corner_count'])
        np.testing.assert_array_equal(image, before)

    def test_session_board_settings_update_only_before_first_frame(self):
        from calibration_console import Console
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / 'empty'
            populated = Path(tmp) / 'populated'
            for folder in (empty, populated):
                flow.create_session(folder, 'C1', 9, 6, 20.0,
                                    confirmed=True, synthetic=True)
            flow.save_frame(populated, full_board(), 'train', 'synthetic tool test')
            app = SimpleNamespace(session=empty,
                confirmed=SimpleNamespace(get=lambda: True),
                camera=SimpleNamespace(get=lambda: 'C1'),
                capture_flip_vertical=SimpleNamespace(get=lambda: False),
                board_inputs=lambda: (6, 9, 25.0), note=Mock())
            self.assertEqual(Console.require_session(app), empty)
            data = flow.load_session(empty)
            self.assertEqual(data['inner_corners'], [6, 9])
            self.assertEqual(data['square_mm_operator_measured'], 25.0)
            self.assertEqual(data['frames'], [])
            app.session = populated
            before = (populated / 'session.json').read_bytes()
            with self.assertRaisesRegex(ValueError, '已有图片'):
                Console.require_session(app)
            self.assertEqual((populated / 'session.json').read_bytes(), before)
            self.assertEqual(len(flow.load_session(populated)['frames']), 1)


if __name__ == '__main__':
    unittest.main()
