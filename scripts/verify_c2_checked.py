from pathlib import Path
import hashlib,json
from verify import test
p=Path(__file__).resolve().parents[1]
files=['rtl/cam/ov5640_reg_rom.v','rtl/cam/sccb_checked_master.v','rtl/cam/ov5640_checked_config.v','sim/model/sccb_sensor_model.v','sim/tb/tb_c2_checked.v']
ok=test('c2_checked','tb_c2_checked',files)
(p/'reports/c2_checked_test.json').write_text(json.dumps({'passed':ok,'simulation_only':True,
 'source_sha256':{n:hashlib.sha256((p/n).read_bytes()).hexdigest() for n in files}},indent=2),encoding='utf-8')
raise SystemExit(0 if ok else 1)
