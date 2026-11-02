"""Synthetic acceptance cases, not measurements from a connected board."""
from pathlib import Path
import copy
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from image30_check import assess

rows=[dict(elapsed_s=i/30+.03,completed_frames=i+1,process_ms=29) for i in range(1799)]
baseline=dict(packets=rows,passed=True,completed_fps_serial_estimate=30,version_failures=0,requested_seconds=60)
assert assess(baseline)['passed']
slow=copy.deepcopy(baseline);slow['completed_fps_serial_estimate']=27
assert not assess(slow)['passed']
stopped=copy.deepcopy(baseline);stopped['packets']=stopped['packets'][:900]
assert not assess(stopped)['passed']
burst=copy.deepcopy(baseline)
for row in burst['packets'][300:330]: row['elapsed_s']=11.03
assert not assess(burst)['passed']
bad=copy.deepcopy(baseline);bad['version_failures']=1
assert not assess(bad)['passed']
wrap=copy.deepcopy(baseline)
for row in wrap['packets']:row['completed_frames']=(row['completed_frames']+0xffffff00)&0xffffffff
assert assess(wrap)['passed']
Path('reports/image30_check_test.json').write_text(json.dumps(dict(passed=True,synthetic_only=True,cases=6),indent=2))
print('IMAGE30_CHECK PASS stable, slow, stopped, USB gap, bad version, counter wrap')
