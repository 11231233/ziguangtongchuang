from pathlib import Path
import hashlib,json
from verify import test
p=Path(__file__).resolve().parents[1]
files=['rtl/video/metrics_osd.v','rtl/cam/reg_config.v','rtl/cam/i2c_com.v','rtl/cam/ov5640_reg_rom.v','sim/tb/tb_c2_status_rom.v']
ok=test('c2_status_rom','tb_c2_status_rom',files)
(p/'reports/c2_status_rom_test.json').write_text(json.dumps({'passed':ok,'simulation_only':True,
 'source_sha256':{n:hashlib.sha256((p/n).read_bytes()).hexdigest() for n in files}},indent=2),encoding='utf-8')
raise SystemExit(0 if ok else 1)
