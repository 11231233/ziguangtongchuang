from pathlib import Path
import hashlib,json
from verify import test
p=Path(__file__).resolve().parents[1]
files=['rtl/cam/sccb_checked_master.v','sim/model/sccb_sensor_model.v','sim/tb/tb_sccb_master.v']
ok=test('sccb_master','tb_sccb_master',files)
(p/'reports/sccb_master_test.json').write_text(json.dumps({'passed':ok,'simulation_only':True,
 'source_sha256':{n:hashlib.sha256((p/n).read_bytes()).hexdigest() for n in files}},indent=2),encoding='utf-8')
raise SystemExit(0 if ok else 1)
