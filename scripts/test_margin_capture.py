"""Synthetic protocol/overlap tests, explicitly not real camera calibration."""
from pathlib import Path
import sys,tempfile,binascii,struct,json,unittest
import numpy as np,cv2
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from margin_geometry import load,identity
from reconstruct_margin_frame import reconstruct,decode,canonical_capture
g=load();gid=identity(g)[1]
def payload(page,frame=42,geometry=gid):
 x,y=g['raw_view_offsets'][page]
 data=b'WRAW'+bytes([1,0x7f,page,0])+geometry.to_bytes(4,'big')+struct.pack('>6H',1296,972,x,y,1280,688)+frame.to_bytes(4,'big')
 return data+binascii.crc_hqx(data,0xffff).to_bytes(2,'big')+b'OK'
def view(full,page,frame=42,geometry=gid):
 x,y=g['raw_view_offsets'][page];image=np.zeros((720,1280,3),np.uint8);image[:688]=full[y:y+688,x:x+1280]
 for i,bit in enumerate(np.unpackbits(np.frombuffer(payload(page,frame,geometry),np.uint8))):image[704:720,i*4:i*4+4]=255*bit
 return image
class Tests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.p=Path(self.temp.name)
  self.full=np.random.default_rng(20261031).integers(0,256,(972,1296,3),np.uint8)
  self.paths=[]
  for page in range(4):
   path=self.p/f'{page}.png';cv2.imencode('.png',view(self.full,page))[1].tofile(path);self.paths.append(path)
 def tearDown(self):self.temp.cleanup()
 def replace(self,page,image):cv2.imencode('.png',image)[1].tofile(self.paths[page])
 def test_exact_all_pixels_including_last_16_columns(self):
  image,meta=reconstruct(self.paths[::-1]);np.testing.assert_array_equal(image,self.full);self.assertTrue(meta['footer_verified'])
 def test_other_frame_rejected(self):
  self.replace(3,view(self.full,3,frame=43))
  with self.assertRaisesRegex(ValueError,'different source'):reconstruct(self.paths)
 def test_other_geometry_rejected(self):
  self.replace(0,view(self.full,0,geometry=gid^1))
  with self.assertRaisesRegex(ValueError,'geometry'):reconstruct(self.paths)
 def test_corrupt_crc_rejected(self):
  im=view(self.full,0);im[704:720,32:36]=255-im[704:720,32:36]
  with self.assertRaises(ValueError):decode(im)
 def test_duplicate_page_rejected(self):
  with self.assertRaisesRegex(ValueError,'different pages'):reconstruct([self.paths[0]]*4)
 def test_rescaled_frame_rejected(self):
  with self.assertRaisesRegex(ValueError,'unscaled'):decode(np.zeros((360,640,3),np.uint8))
 def test_overlap_mismatch_rejected(self):
  im=view(self.full,2);im[:688]=255-im[:688];self.replace(2,im)
  with self.assertRaisesRegex(ValueError,'Overlapping'):reconstruct(self.paths)
 def test_unfrozen_flag_rejected(self):
  im=view(self.full,0);data=bytearray(payload(0));data[5]&=~2;data[28:30]=binascii.crc_hqx(data[:28],0xffff).to_bytes(2,'big')
  for i,bit in enumerate(np.unpackbits(np.frombuffer(data,np.uint8))):im[704:720,i*4:i*4+4]=255*bit
  with self.assertRaisesRegex(ValueError,'conditions'):decode(im)
 def test_crc_tag_restores_whole_transport_only(self):
  image=view(self.full,1);restored,tag,orientation=canonical_capture(cv2.flip(image,0))
  self.assertEqual(orientation,'vertical');self.assertEqual(tag['page'],1);np.testing.assert_array_equal(restored,image)
  self.assertEqual(canonical_capture(image)[2],'identity')
  with self.assertRaises(ValueError):canonical_capture(cv2.flip(image,1))
 def test_unfrozen_tag_can_identify_direction_but_cannot_save(self):
  image=view(self.full,0);data=bytearray(payload(0));data[5]&=~2;data[28:30]=binascii.crc_hqx(data[:28],0xffff).to_bytes(2,'big')
  for i,bit in enumerate(np.unpackbits(np.frombuffer(data,np.uint8))):image[704:720,i*4:i*4+4]=255*bit
  restored,tag,orientation=canonical_capture(cv2.flip(image,0));self.assertEqual(orientation,'vertical')
  with self.assertRaisesRegex(ValueError,'conditions'):decode(restored)
if __name__=='__main__':unittest.main()
