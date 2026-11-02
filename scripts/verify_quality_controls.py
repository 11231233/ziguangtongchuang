from pathlib import Path
import hashlib,json
from verify import test
p=Path(__file__).resolve().parents[1]
files=['rtl/common/key_short_long.v','rtl/video/metrics_osd.v','rtl/video/quality_display.v','sim/tb/tb_quality_controls.v']
ok=test('quality_controls','tb_quality_controls',files)
(p/'reports/quality_controls_test.json').write_text(json.dumps({'passed':ok,'source_sha256':
 {n:hashlib.sha256((p/n).read_bytes()).hexdigest() for n in files}},indent=2),encoding='utf-8')
raise SystemExit(0 if ok else 1)
