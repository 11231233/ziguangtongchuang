"""Latest-frame workers under slow filters, device stalls and mode changes."""
import queue,sys,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from preview_stream import LatestCapture,LatestPreviewFilter
from calibration_console import Console


def wait_for(predicate,timeout=2):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        if predicate():return True
        threading.Event().wait(.005)
    return False

class FakeCapture:
    def __init__(self):self.frames=queue.Queue();self.released=False
    def read(self):
        try:return True,self.frames.get(timeout=.02)
        except queue.Empty:return False,None
    def release(self):self.released=True

class BlockFirst:
    def __init__(self):self.entered=threading.Event();self.gate=threading.Event();self.calls=[];self.resets=0;self.corrected_pixels=0
    def reset(self):self.resets+=1
    def process(self,image,mode,use_temporal):
        value=int(image[0,0,0]);self.calls.append(value)
        if len(self.calls)==1:self.entered.set();self.gate.wait(2)
        return image.copy()

class StreamTests(unittest.TestCase):
    def test_capture_latest_and_single_owner_release(self):
        cap=FakeCapture();reader=LatestCapture(cap)
        try:
            for value in range(1,6):cap.frames.put(np.full((4,4,3),value,np.uint8))
            self.assertTrue(wait_for(lambda:reader.latest() and reader.latest()[0]>=5))
            self.assertEqual(int(reader.latest()[2][0,0,0]),5)
            self.assertIsNone(reader.latest(5))
        finally:self.assertTrue(reader.stop())
        self.assertTrue(cap.released)
    def test_blocked_read_does_not_block_ui_stop(self):
        gate=threading.Event();entered=threading.Event()
        cap=FakeCapture()
        def read():entered.set();gate.wait(2);return False,None
        cap.read=read;reader=LatestCapture(cap)
        self.assertTrue(entered.wait(1))
        started=time.monotonic();self.assertFalse(reader.stop(.01))
        self.assertLess(time.monotonic()-started,.5);self.assertFalse(cap.released)
        gate.set();reader.thread.join(1);self.assertTrue(cap.released)
    def test_slow_filter_skips_pending_old_frames(self):
        proc=BlockFirst();worker=LatestPreviewFilter(proc)
        frame=lambda value:np.full((4,4,3),value,np.uint8)
        try:
            worker.submit(frame(1),'small_spots',{'frame':1});self.assertTrue(proc.entered.wait(1))
            for value in range(2,11):worker.submit(frame(value),'small_spots',{'frame':value})
            proc.gate.set();self.assertTrue(wait_for(lambda:worker.latest() and worker.latest()['metadata']['frame']==10))
            self.assertEqual(proc.calls,[1,10]);self.assertGreaterEqual(worker.skipped,8)
            self.assertEqual(worker.latest()['original'][0,0,0],10)
        finally:proc.gate.set();worker.close()
    def test_mode_change_discards_in_flight_old_result(self):
        proc=BlockFirst();worker=LatestPreviewFilter(proc)
        try:
            worker.submit(np.full((4,4,3),1,np.uint8),'small_spots',{'version':'old'})
            self.assertTrue(proc.entered.wait(1));worker.invalidate()
            self.assertIsNone(worker.latest())
            worker.submit(np.full((4,4,3),9,np.uint8),'bilateral',{'version':'new'})
            proc.gate.set();self.assertTrue(wait_for(lambda:worker.latest() and worker.latest()['metadata']['version']=='new'))
            self.assertEqual(worker.latest()['mode'],'bilateral');self.assertGreaterEqual(proc.resets,2)
        finally:proc.gate.set();worker.close()
    def test_idle_filter_closes(self):
        worker=LatestPreviewFilter();self.assertTrue(worker.close())
    def test_live_gui_show_never_runs_filter_synchronously(self):
        app=SimpleNamespace(cap=Mock(),capture_reader=Mock(),queue_capture_preview=Mock(),preview_denoiser=Mock())
        image=np.zeros((4,4,3),np.uint8);Console.show(app,image)
        app.queue_capture_preview.assert_called_once_with(image)
        app.preview_denoiser.process.assert_not_called()

if __name__=='__main__':unittest.main()
