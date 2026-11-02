"""Synthetic numerical and rejection tests, never a real calibration result."""
from pathlib import Path
import sys,json,tempfile,hashlib,unittest
import cv2,numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from margin_geometry import load,identity
from margin_calibration import coefficients,coverage,require_runtime_model,load_verified_frame
from prepare_margin_runtime import render_controls
from reconstruct_margin_frame import reconstruct
from test_margin_capture import view

def test_model():
 return dict(fx=520.,fy=520.,cx=648.,cy=486.,k1=-21061/65536,k2=7082/65536,p1=0.,p2=0.,k3=0.,
  image_size=[1296,972],geometry_sha256=identity(load())[0],source_kind='synthetic_points_test',synthetic_test_data=True,
  output_camera=dict(fx=520.,fy=520.,cx=640.,cy=360.,width=1280,height=720))

class Tests(unittest.TestCase):
 def test_illustrative_margin_passes_but_never_real(self):
  model=test_model();r=coverage(model,load(),angles=[-20,0,20],step=8)
  self.assertTrue(r['passed']);self.assertFalse(r['full_pixel_audit'])
  self.assertIn("assign certified=1'b0",render_controls(model,True))
 def test_insufficient_real_area_rejected_without_autozoom(self):
  m=test_model();m.update(k1=0.,k2=0.)
  before=dict(m['output_camera']);r=coverage(m,load(),angles=[20],step=8)
  self.assertFalse(r['passed']);self.assertGreater(r['rows'][0]['invalid_pixels'],0);self.assertEqual(m['output_camera'],before)
 def test_pixel_rotation_with_unequal_focal_lengths(self):
  m=test_model();m['output_camera'].update(fx=510.,fy=530.,cx=638.,cy=362.)
  c=coefficients(m,20);t=np.deg2rad(20);x,y=731.,417.
  nx=(np.cos(t)*(x-640)-np.sin(t)*(y-360)+640-638)/510
  ny=(np.sin(t)*(x-640)+np.cos(t)*(y-360)+360-362)/530
  self.assertLess(abs((c['A']*x+c['B']*y)/2**24+c['C']/65536-nx),5e-5)
  self.assertLess(abs((c['D']*x+c['E']*y)/2**24+c['F']/65536-ny),5e-5)
 def test_legacy_model_cannot_prepare(self):
  with tempfile.TemporaryDirectory() as directory:
   p=Path(directory);m=test_model();m.update(source_kind='ov5640_raw_digital',image_size=[1280,720],synthetic_test_data=False)
   (p/'m.json').write_text(json.dumps(m));(p/'v.json').write_text(json.dumps(dict(ready_for_runtime=True)))
   with self.assertRaises(ValueError):require_runtime_model(p/'m.json',p/'v.json')
 def test_same_size_different_geometry_rejected(self):
  with tempfile.TemporaryDirectory() as directory:
   p=Path(directory);m=test_model();m.update(source_kind='verified_margin_raw_calibration',synthetic_test_data=False,geometry_sha256='wrong')
   (p/'m.json').write_text(json.dumps(m));(p/'v.json').write_text(json.dumps(dict(ready_for_runtime=True)))
   with self.assertRaisesRegex(ValueError,'Geometry'):require_runtime_model(p/'m.json',p/'v.json')
 def test_raw_image_hash_and_geometry_bound(self):
  with tempfile.TemporaryDirectory() as directory:
   p=Path(directory)/'im.png';data=cv2.imencode('.png',np.zeros((972,1296,3),np.uint8))[1].tobytes();p.write_bytes(data)
   pages=[]
   for page in range(4):
    raw=p.parent/f'p{page}.png';cv2.imencode('.png',view(np.zeros((972,1296,3),np.uint8),page))[1].tofile(raw);pages.append(raw)
   _,meta=reconstruct(pages);meta['image_sha256']=hashlib.sha256(data).hexdigest()
   p.with_suffix('.json').write_text(json.dumps(meta));self.assertEqual(load_verified_frame(p,load())[0].shape,(972,1296,3))
   p.write_bytes(data+b'changed')
   with self.assertRaisesRegex(ValueError,'changed'):load_verified_frame(p,load())
 def test_raw_rom_turns_off_all_distortion(self):
  m=test_model();m.update(p1=.001,p2=-.002)
  cor=coefficients(m,12);raw=coefficients(m,12,True)
  self.assertNotEqual(cor['p1'],0)
  for name in ['k1','k2','p1','p2']:self.assertEqual(raw[name],0)
  for name in ['A','B','C','D','E','F','fx','fy','cx','cy']:self.assertEqual(raw[name],cor[name])

if __name__=='__main__':unittest.main()
