from pathlib import Path
import hashlib,json
from verify import test
p=Path(__file__).resolve().parents[1]
files=['rtl/video/quality_display.v','sim/tb/tb_quality_720p.v']
ok=test('quality_720p','tb_quality_720p',files,timeout=180)
(p/'reports/quality_720p_test.json').write_text(json.dumps({'passed':ok,
 'frames':3,'active_pixels_per_frame':921600,'timing_pixels_per_frame':1650*750,
 'tested_modes':[1,2,0],'simulation_only':True,'real_DDR_PHY_included':False,
 'source_sha256':{n:hashlib.sha256((p/n).read_bytes()).hexdigest() for n in files}},indent=2),encoding='utf-8')
raise SystemExit(0 if ok else 1)
