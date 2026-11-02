from pathlib import Path
import hashlib,json
from verify import test
p=Path(__file__).resolve().parents[1]
files=['rtl/common/camera_probe.v','sim/tb/tb_camera_probe.v']
ok=test('camera_probe','tb_camera_probe',files)
(p/'reports/camera_probe_test.json').write_text(json.dumps({'passed':ok,'simulation_only':True,'source_sha256':{n:hashlib.sha256((p/n).read_bytes()).hexdigest() for n in files}},indent=2),encoding='utf-8')
raise SystemExit(0 if ok else 1)
