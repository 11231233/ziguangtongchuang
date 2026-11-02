from pathlib import Path
import binascii,json,struct,sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from host_control import FIELDS,packet,coefficients
from validate_coefficients import validate

class HostTools(unittest.TestCase):
 def setUp(self):
  self.calib=dict(fx=520,fy=520,cx=640,cy=360,k1=-.28,k2=.08,p1=.001,p2=-.0005,image_size=[1280,720],k3=0)
 def test_wire_format(self):
  c=coefficients(self.calib,roll=31.5);p=packet(c,99)
  self.assertEqual(len(p),62);self.assertEqual(p[:4],b'\xa5\x5a\x01\x63')
  self.assertEqual(struct.unpack('<14i',p[4:60]),tuple(c[k] for k in FIELDS))
  self.assertEqual(int.from_bytes(p[-2:],'big'),binascii.crc_hqx(p[2:-2],0xffff))
  self.assertEqual(binascii.crc_hqx(b'123456789',0xffff),0x29b1)
 def test_real_calibration_contract(self):
  with self.assertRaises(ValueError):coefficients(dict(self.calib,k3=.01))
  with self.assertRaises(ValueError):coefficients(dict(self.calib,image_size=[640,480]))
  with self.assertRaises(ValueError):coefficients(self.calib,zoom=0)
 def test_signed_limit(self):
  c=coefficients(self.calib);c['p1']=131072
  with self.assertRaises(ValueError):packet(c)
 def test_geometry_rejects_unfetchable_mapping(self):
  c=coefficients(self.calib);c['A']=65536
  with self.assertRaises(ValueError):validate(c)
 def test_rotation_tilt_and_exact_raw(self):
  for roll,yaw,pitch in [(0,0,0),(31.5,0,0),(-179.5,0,0),(12.25,5,-5)]:
   self.assertTrue(validate(coefficients(self.calib,roll=roll,yaw=yaw,pitch=pitch))['passed'])
  raw=coefficients({},raw=True)
  self.assertEqual(validate(raw)['valid_pixels'],921600)
  self.assertEqual(raw['A']*raw['fx']>>16,65536)

if __name__=='__main__':unittest.main()
