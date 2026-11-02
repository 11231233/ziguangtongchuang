"""Loading a measured model must clear an old demo selection before sending."""
from pathlib import Path
import json
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from calibration_console import Console


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def model(camera='C1', source='ov5640_raw_digital', synthetic=False):
    return dict(camera=camera, source_kind_operator_declared=source,
                synthetic_test_data=synthetic, image_size=[1280, 720],
                fx=600.0, fy=605.0, cx=639.5, cy=359.5,
                k1=-0.2, k2=0.04, p1=0.001, p2=-0.001, k3=0.0)


def console(output):
    app = SimpleNamespace(model=None, model_path=None,
        camera=Value('C1'), initial_demo=Value(True), wired=Value(True),
        port=Value('COM24'), roll=Value('0'),
        initial_demo_box=Mock(), model_source_info=Value(''),
        note=Mock(), refresh=Mock(), destination=Mock(return_value=output),
        reset_preview_processing=Mock(), command=Mock(return_value='mocked command'))
    app.real_model = lambda: Console.real_model(app)
    app.update_model_source = lambda: Console.update_model_source(app)
    app.guarded = lambda operation: operation()
    app.job = Mock(side_effect=lambda operation: operation())
    return app


class ModelSelection(unittest.TestCase):
    def test_loaded_real_model_overrides_previous_demo_for_live_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            path = folder / 'measured.json'
            path.write_text(json.dumps(model()), encoding='utf-8')
            app = console(folder / 'export')
            self.assertTrue(app.initial_demo.get())
            with patch('calibration_console.cv2.VideoCapture') as capture, \
                 patch('serial_link.open_uart') as uart, \
                 patch('calibration_console.subprocess.run') as subprocess:
                Console.set_model(app, path)
                self.assertFalse(app.initial_demo.get())
                self.assertEqual(Console.real_model(app), path)
                app.initial_demo_box.configure.assert_called_with(state='disabled')
                self.assertIn(str(path), app.model_source_info.get())
                # Even stale/programmatic demo state cannot replace a loaded
                # real model on the next send.
                app.initial_demo.set(True)
                Console.host(app, live=True)
                self.assertFalse(app.initial_demo.get())
            capture.assert_not_called()
            uart.assert_not_called()
            subprocess.assert_not_called()
            app.command.assert_called_once()
            args, log = app.command.call_args.args
            self.assertEqual(args[args.index('--calib') + 1], path)
            self.assertNotIn('--allow-indirect', args)
            self.assertNotIn('--raw', args)
            self.assertEqual(args[args.index('--port') + 1], 'COM24')
            self.assertEqual(args[args.index('--roll') + 1], '0.0')
            self.assertEqual(log, folder / 'export/host.log')
            self.assertTrue(any('关闭' in str(call.args[0]) and '初估' in str(call.args[0])
                                for call in app.note.call_args_list))

    def test_indirect_model_is_not_accepted_as_measured(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'indirect.json'
            path.write_text(json.dumps(model(source='monitor_rectified')), encoding='utf-8')
            app = console(Path(tmp) / 'unused_export')
            Console.set_model(app, path)
            self.assertTrue(app.initial_demo.get())
            self.assertEqual(app.model['source_kind_operator_declared'], 'monitor_rectified')
            with self.assertRaisesRegex(ValueError, '实际OV5640'):
                Console.real_model(app)
            app.command.assert_not_called()

    def test_synthetic_model_does_not_clear_demo_or_pass_measured_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'synthetic.json'
            path.write_text(json.dumps(model(synthetic=True)), encoding='utf-8')
            app = console(Path(tmp) / 'unused_export')
            Console.set_model(app, path)
            self.assertTrue(app.initial_demo.get())
            with self.assertRaisesRegex(ValueError, '实际OV5640'):
                Console.real_model(app)
            app.command.assert_not_called()

    def test_other_camera_model_does_not_clear_demo_or_pass_camera_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'C2.json'
            path.write_text(json.dumps(model(camera='C2')), encoding='utf-8')
            app = console(Path(tmp) / 'unused_export')
            Console.set_model(app, path)
            self.assertTrue(app.initial_demo.get())
            with self.assertRaisesRegex(ValueError, '相机'):
                Console.real_model(app)
            app.command.assert_not_called()


if __name__ == '__main__':
    unittest.main()
