"""Exercise all-pixel coverage mathematics with an illustrative, non-real model."""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'scripts'))
from test_margin_calibration import test_model
from margin_geometry import load
from margin_calibration import coverage
r=coverage(test_model(),load())
r.update(synthetic_test_only=True,real_calibration_complete=False,hardware_tested=False,
         scope='Numerical algorithm test only; old empirical radial model with assumed centered margin')
(ROOT/'reports/coverage_algorithm_test.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
assert r['passed'] and len(r['rows'])==41 and all(v['pixels']==921600 for v in r['rows'])
print('PASS: 41 angles, 37785600 pixels, fixed output camera, independent fixed-point bounds and tile fetch windows; SYNTHETIC ONLY')
