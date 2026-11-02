from pathlib import Path
import hashlib,json
from verify import test
p=Path(__file__).resolve().parents[1]
files=['rtl/common/async_fifo.v','rtl/cam/dvp_capture.v','rtl/cam/dvp_capture_phase.v','sim/tb/tb_dvp_phase.v']
ok=test('dvp_phase','tb_dvp_phase',files)
(p/'reports/dvp_phase_test.json').write_text(json.dumps({'passed':ok,'simulation_only':True,
 'source_sha256':{n:hashlib.sha256((p/n).read_bytes()).hexdigest() for n in files}},indent=2),encoding='utf-8')
raise SystemExit(0 if ok else 1)
