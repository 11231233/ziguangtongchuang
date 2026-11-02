from pathlib import Path
import hashlib,json
from verify import test
p=Path(__file__).resolve().parents[1]
files=['rtl/cam/ov5640_reg_rom.v','rtl/cam/sccb_checked_master.v','rtl/cam/ov5640_checked_config.v','sim/model/sccb_sensor_model.v','sim/tb/tb_image30_checked.v']
ok=test('image30_checked','tb_image30_checked',files)
r={'passed':ok,'simulation_only':True,'hardware_image_verified':False,'checks':['280 configuration writes','15 image register readback mismatch injection cases block capture','AEC/AGC and AWB automatic','fixed VTS 740 and exposure ceiling 736','PLL readback failure','transient ACK/retry','native bars','permanent NACK fail-stop'],'source_sha256':{n:hashlib.sha256((p/n).read_bytes()).hexdigest() for n in files}}
(p/'reports/image30_config_test.json').write_text(json.dumps(r,indent=2))
raise SystemExit(0 if ok else 1)
