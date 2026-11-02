from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from analyze_latency import analyze

class LatencyTest(unittest.TestCase):
 def test_paired_seconds(self):
  r=analyze([dict(reference_s=10,hdmi_s=9.9),dict(reference_s=11,hdmi_s=10.8),dict(reference_s=12,hdmi_s=11.7)])
  self.assertEqual(r['samples'],3);self.assertAlmostEqual(r['median_ms'],200);self.assertAlmostEqual(r['mean_ms'],200)
  self.assertAlmostEqual(r['p95_ms_nearest_rank'],300)
 def test_no_abs_or_fake_data(self):
  for rows in [[],[dict(reference_s=1,hdmi_s=2)],[dict(reference_s='nan',hdmi_s=1)],[dict(reference_s=1)]]:
   with self.assertRaises(ValueError):analyze(rows)

if __name__=='__main__':unittest.main()
