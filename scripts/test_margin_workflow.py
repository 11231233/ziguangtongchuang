"""Offline synthetic capture-to-dataset and our own hidden Tk form checks."""
from pathlib import Path
import sys,tempfile,unittest,threading
from unittest.mock import patch
import numpy as np,cv2,tkinter as tk
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'scripts'))
from test_margin_capture import view
import margin_dataset
from margin_geometry import load
from margin_calibration import load_verified_frame
from margin_calibration_console import Console

class Workflow(unittest.TestCase):
 def test_real_detector_and_tagged_evidence_save(self):
  with tempfile.TemporaryDirectory() as directory:
   parent=Path(directory);folder=margin_dataset.create(parent)
   image=np.full((972,1296,3),210,np.uint8)
   for y in range(10):
    for x in range(7):
     image[180+y*60:180+(y+1)*60,430+x*60:430+(x+1)*60]=255 if (x+y)%2 else 0
   pages=[]
   for page in range(4):
    p=parent/f'p{page}.png';cv2.imencode('.png',view(image,page))[1].tofile(p);pages.append(p)
   import json,hashlib
   original=parent/'transport.png';cv2.imencode('.png',cv2.flip(view(image,0),0))[1].tofile(original)
   pages[0].with_suffix('.json').write_text(json.dumps(dict(schema='margin_transport_restore_v1',normalization='vertical',
    original=str(original),original_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),canonical_sha256=hashlib.sha256(pages[0].read_bytes()).hexdigest())))
   saved=margin_dataset.save(folder,pages,'train',(6,9))
   np.testing.assert_array_equal(load_verified_frame(saved,load())[0],image)
   with self.assertRaisesRegex(ValueError,'already saved'):margin_dataset.save(folder,pages,'validation',(6,9))
   # The dataset keeps its own original pages and no longer depends on import paths.
   pages[0].unlink();original.unlink();load_verified_frame(saved,load())
   original=next((folder/'raw_groups').rglob('capture_0.png'))
   original.write_bytes(original.read_bytes()+b'changed')
   with self.assertRaisesRegex(ValueError,'changed or missing'):load_verified_frame(saved,load())

 def test_gui_numeric_inputs_and_thread_boundary(self):
  root=tk.Tk();root.withdraw()
  try:
   gui=Console(root);gui.folder=Path('SYNTHETIC_TEST_ONLY');gui.square.set('２０.５');gui.confirmed.set(True)
   tasks=[];gui.job=lambda fn:tasks.append(fn)
   main_thread=threading.get_ident();old_get=gui.confirmed.get
   def checked_get():
    self.assertEqual(threading.get_ident(),main_thread);return old_get()
   gui.confirmed.get=checked_get
   with patch('margin_calibration_console.messagebox.showerror') as error:
    gui.calibrate();error.assert_not_called()
   self.assertEqual(len(tasks),1)
   result=[]
   with patch('margin_calibration_console.calibrate',return_value=dict(ready_for_runtime=False,reasons=['synthetic test'])) as fit:
    thread=threading.Thread(target=lambda:result.append(tasks[0]()));thread.start();thread.join(5)
    self.assertFalse(thread.is_alive());self.assertEqual(len(result),1)
    args=fit.call_args.args;self.assertEqual(args[2:],((6,9),20.5,True))
   gui.square.set("9`")
   with patch('margin_calibration_console.messagebox.showerror') as error:
    gui.calibrate();error.assert_called_once()
  finally:root.destroy()

 def test_gui_manual_page_save_preserves_all_raw_pixels_and_no_auto_device(self):
  root=tk.Tk();root.withdraw()
  try:
   with patch('margin_calibration_console.cv2.VideoCapture') as device:
    gui=Console(root);device.assert_not_called()
   with tempfile.TemporaryDirectory() as directory:
    gui.folder=margin_dataset.create(directory);full=np.random.default_rng(7).integers(0,256,(972,1296,3),np.uint8)
    with patch('margin_calibration_console.messagebox.showerror') as error:
     for page in range(4):gui.raw=cv2.flip(view(full,page),0);gui.save_page()
     error.assert_not_called()
    from reconstruct_margin_frame import reconstruct
    np.testing.assert_array_equal(reconstruct(gui.pages)[0],full)
    import json
    evidence=json.loads(Path(gui.pages[0]).with_suffix('.json').read_text())
    self.assertEqual(evidence['normalization'],'vertical')
    original=Path(evidence['original']);original.write_bytes(original.read_bytes()+b'changed')
    with self.assertRaisesRegex(ValueError,'evidence changed'):reconstruct(gui.pages)
    gui.raw=view(full,0,frame=43);gui.save_page();self.assertEqual(len(gui.pages),1)
    gui.reset_pages();self.assertEqual(gui.pages,[]);self.assertIsNone(gui.saved_fid)
  finally:root.destroy()

if __name__=='__main__':unittest.main()
