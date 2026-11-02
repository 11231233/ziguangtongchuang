"""Capture normalization must affect saved pixels once, without mutating driver data."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from calibration_console import Console

class CaptureDirection(unittest.TestCase):
    def test_capture_and_save_use_same_normalized_pixels(self):
        for flip in (False,True):
            driver=np.arange(18,dtype=np.uint8).reshape(3,2,3);unchanged=driver.copy()
            app=SimpleNamespace(cap=Mock(),capture_flip_vertical=SimpleNamespace(get=lambda:flip),device=SimpleNamespace(get=lambda:'0'),preview_flip_vertical=SimpleNamespace(get=lambda:False),show=Mock(),info=Mock(),root=Mock(),capture_tick=Mock())
            app.capture_reader=Mock();app.capture_reader.latest.return_value=(1,1.,driver)
            app.capture_reader.error=None;app.update_preview_stats=Mock()
            app.capture_sequence=0;app.queue_capture_preview=Mock();app.preview_job=0
            app.preview_worker=Mock();app.preview_worker.latest.return_value=None;app.preview_worker.error=None
            app.denoise_mode=SimpleNamespace(get=lambda:'关闭')
            Console.capture_tick(app)
            expected=unchanged[::-1] if flip else unchanged
            np.testing.assert_array_equal(app.raw,expected)
            np.testing.assert_array_equal(driver,unchanged)
            app.require_session=lambda:Path('dummy_session')
            app.guarded=lambda fn:fn();app.job=lambda fn:fn()
            with patch('calibration_console.flow.save_frame') as save:
                Console.save(app,'train')
                np.testing.assert_array_equal(save.call_args.args[1],expected)
                self.assertIn('input_flip_vertical='+str(int(flip)),save.call_args.args[3])
    def test_existing_session_locks_capture_direction(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            (folder/'session.json').write_text(json.dumps(dict(schema='ov5640_digital_session_v1',frames=[{'file':'kept.png'}],capture_input_transform={'flip_vertical':False})),encoding='utf-8')
            flag=Mock();flag.get.return_value=True
            app=SimpleNamespace(busy=False,session=folder,capture_flip_vertical=flag)
            with patch('calibration_console.messagebox.showinfo'):
                Console.capture_direction_changed(app)
            flag.set.assert_called_once_with(False)
            self.assertFalse(json.loads((folder/'session.json').read_text())['capture_input_transform']['flip_vertical'])

if __name__=='__main__':unittest.main()
