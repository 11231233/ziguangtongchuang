from pathlib import Path
import hashlib,json
from verify import test
root=Path(__file__).resolve().parents[1]
files=['rtl/video/metrics_osd.v','sim/tb/tb_osd_pipeline.v']
ok=test('osd_pipeline','tb_osd_pipeline',files)
(root/'reports/osd_pipeline_test.json').write_text(json.dumps(dict(passed=ok,simulation_only=True,
 checks=['67200 exact image/overlay comparisons','glyph lookup delayed one cycle','blanking and box bounds','reset'],
 source_sha256={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in files}),indent=2),encoding='utf-8')
raise SystemExit(0 if ok else 1)
