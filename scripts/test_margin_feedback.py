from pathlib import Path
import sys,unittest,numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from margin_feedback import frame_feedback,edge_counts,corner_counts,calibration_summary
class Feedback(unittest.TestCase):
 def test_overlay_never_changes_input_pixels(self):
  raw=np.full((972,1296,3),80,np.uint8);saved=raw.copy();shown,text=frame_feedback(raw,np.array([[100,100],[1200,900]],np.float32))
  np.testing.assert_array_equal(raw,saved);self.assertFalse(np.array_equal(shown,raw))
  self.assertEqual(edge_counts([[100,100],[1200,900]],(1296,972)),dict(left=1,right=1,top=1,bottom=1))
  self.assertIn('不要求单张覆盖四边',text)
 def test_failed_report_explains_missing_places_without_promoting(self):
  r=dict(ready_for_runtime=False,train_rms_px=1.62,heldout_rms_px=1.49,
   spatial_coverage=dict(edges=dict(right=dict(views=0,points=0)),corners=dict(bl=0,br=0)),
   heldout_edge_errors=dict(bottom=dict(points=0)),mapping_coverage=dict(passed=True),reasons=[])
  text=calibration_summary(r);self.assertIn('1.62',text);self.assertIn('右',text);self.assertIn('左下',text);self.assertIn('暂不能',text)
  self.assertFalse(r['ready_for_runtime'])
 def test_corner_is_wider_than_edge_intersection_and_needs_no_eight_points(self):
  from margin_calibration import spatial_coverage
  points=np.array([[200.,760.]],np.float32)
  self.assertEqual(edge_counts(points,(1296,972)),dict(left=0,right=0,top=0,bottom=0))
  corners=corner_counts(points,(1296,972));self.assertEqual(corners['bl'],1)
  self.assertEqual(corners,spatial_coverage([points.reshape(-1,1,2)],(1296,972))['corners'])
  _,text=frame_feedback(np.zeros((972,1296,3),np.uint8),points)
  self.assertIn('左下1',text);self.assertIn('不要求单张8点',text);self.assertIn('四角各有观测即可',text)
if __name__=='__main__':unittest.main()
