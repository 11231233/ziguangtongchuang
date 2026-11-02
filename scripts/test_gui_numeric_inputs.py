"""Validate board inputs before dialogs or session writes; never open hardware."""
from pathlib import Path
import json
import sys
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

from calibration_inputs import BoardInputError, parse_board_inputs, parse_inner_corners
from calibration_console import Console


class BoardInputParsing(unittest.TestCase):
    def assert_field_error(self, field, cols='9', rows='6', square='20.5'):
        with self.assertRaises(BoardInputError) as raised:
            parse_board_inputs(cols, rows, square)
        self.assertEqual(raised.exception.field, field)
        self.assertNotIn('invalid literal', str(raised.exception))
        self.assertTrue(str(raised.exception))

    def test_plain_and_full_width_inputs(self):
        self.assertEqual(parse_board_inputs('9', '6', '20.5'), (9, 6, 20.5))
        self.assertEqual(parse_board_inputs('　９　', ' ６ ', '　２０．５　'), (9, 6, 20.5))
        self.assertEqual(parse_inner_corners('３', '３'), (3, 3))

    def test_column_typo_is_not_silently_removed(self):
        for text in ('9`', "9'", '9mm', '9.0', '9e0', '9 0', '', '-9', '2'):
            with self.subTest(text=text):
                self.assert_field_error('cols', cols=text)

    def test_row_error_reports_row(self):
        for text in ('6`', '6.0', '', '2'):
            with self.subTest(text=text):
                self.assert_field_error('rows', rows=text)

    def test_square_requires_finite_positive_number(self):
        for text in ('', ' ', 'abc', '20mm', '20`', '20,5', 'NaN', 'nan',
                     'Inf', '-Inf', '1e309', '0', '-0', '-1'):
            with self.subTest(text=text):
                self.assert_field_error('square', square=text)


class NewSessionInputGuard(unittest.TestCase):
    def setUp(self):
        self.hardware = [patch('calibration_console.cv2.VideoCapture'),
                         patch('serial_link.open_uart')]
        self.hardware_mocks = [p.start() for p in self.hardware]
        self.addCleanup(lambda: [p.stop() for p in reversed(self.hardware)])
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = Console(self.root)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        existing = self.parent / 'existing_session'
        existing.mkdir()
        (existing / 'kept.txt').write_text('unchanged', encoding='utf-8')
        # Preserve recognizable old state when starting a new session fails.
        self.app.session = existing
        self.app.model = {'kept_model': True}
        self.app.model_path = existing / 'kept_model.json'
        self.app.raw = object()
        self.app.raw_source = 'kept_source'
        self.app.cols.set('9')
        self.app.rows.set('6')
        self.app.square.set('20.5')
        self.app.confirmed.set(True)

    def tearDown(self):
        self.app.close()
        for mocked in self.hardware_mocks:
            mocked.assert_not_called()

    def snapshot(self):
        return (self.app.session, self.app.model, self.app.model_path,
                self.app.raw, self.app.raw_source)

    def files_snapshot(self):
        return {str(p.relative_to(self.parent)): p.read_bytes()
                for p in self.parent.rglob('*') if p.is_file()}

    def test_invalid_field_prevents_dialog_and_session_creation(self):
        for field, bad_text in [('cols', '9`'), ('rows', '6`'),
                                ('square', ''), ('square', 'NaN')]:
            with self.subTest(field=field, text=bad_text):
                self.app.cols.set('9')
                self.app.rows.set('6')
                self.app.square.set('20.5')
                getattr(self.app, field).set(bad_text)
                before = self.snapshot()
                files_before = self.files_snapshot()
                directories_before = sorted(p.relative_to(self.parent).as_posix()
                                            for p in self.parent.rglob('*') if p.is_dir())
                entry = self.app.board_entries[field]
                with patch('calibration_console.filedialog.askdirectory', return_value=str(self.parent)) as dialog, \
                     patch('calibration_console.flow.create_session') as create, \
                     patch('calibration_console.messagebox.showerror') as error, \
                     patch.object(entry, 'focus_set') as focus, \
                     patch.object(entry, 'selection_range') as selection:
                    self.app.new_session()
                dialog.assert_not_called()
                create.assert_not_called()
                error.assert_called_once()
                self.assertNotIn('invalid literal', error.call_args.args[1])
                focus.assert_called_once()
                selection.assert_called_once_with(0, tk.END)
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(self.files_snapshot(), files_before)
                self.assertEqual(sorted(p.relative_to(self.parent).as_posix()
                                        for p in self.parent.rglob('*') if p.is_dir()),
                                 directories_before)

    def test_confirmation_is_checked_before_folder_dialog(self):
        self.app.confirmed.set(False)
        before = self.snapshot()
        with patch('calibration_console.filedialog.askdirectory') as dialog, \
             patch('calibration_console.flow.create_session') as create, \
             patch('calibration_console.messagebox.showerror') as error:
            self.app.new_session()
        dialog.assert_not_called()
        create.assert_not_called()
        error.assert_called_once()
        self.assertIn('确认', error.call_args.args[1])
        self.assertEqual(self.snapshot(), before)

    def test_cancelled_folder_keeps_existing_session(self):
        before = self.snapshot()
        files_before = self.files_snapshot()
        with patch('calibration_console.filedialog.askdirectory', return_value='') as dialog, \
             patch('calibration_console.flow.create_session') as create, \
             patch('calibration_console.messagebox.showerror') as error:
            self.app.new_session()
        dialog.assert_called_once()
        create.assert_not_called()
        error.assert_not_called()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.files_snapshot(), files_before)

    def test_valid_normalized_values_create_correct_session(self):
        self.app.cols.set('　９　')
        self.app.rows.set('６')
        self.app.square.set('　２０．５　')
        # This writes only inside TemporaryDirectory, not a user session.
        with patch('calibration_console.filedialog.askdirectory', return_value=str(self.parent)), \
             patch('calibration_console.messagebox.showerror') as error:
            self.app.new_session()
        error.assert_not_called()
        data = json.loads((self.app.session / 'session.json').read_text(encoding='utf-8'))
        self.assertEqual(data['inner_corners'], [9, 6])
        self.assertEqual(data['square_mm_operator_measured'], 20.5)
        self.assertEqual((self.app.cols.get(), self.app.rows.get(), self.app.square.get()),
                         ('9', '6', '20.5'))
        self.assertIsNone(self.app.model)
        self.assertIsNone(self.app.model_path)
        self.assertEqual((self.parent / 'existing_session/kept.txt').read_text(encoding='utf-8'),
                         'unchanged')


if __name__ == '__main__':
    unittest.main()
