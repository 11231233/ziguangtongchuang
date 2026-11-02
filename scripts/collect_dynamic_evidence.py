"""Run after full regression, with no concurrent simulation using sim/out/."""
from pathlib import Path
import argparse,json,shutil,subprocess,sys
p=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--tests',required=True);a=ap.parse_args();dest=Path(a.tests)
data=json.loads((dest/'summary.json').read_text());assert data['passed'] and data['complete']
for script,logname in [('scripts/check_structure.py','structure_run.log'),('tools/verify_geometry.py','geometry_run.log'),('scripts/test_host_tools.py','host_tools.log'),('scripts/test_latency.py','latency_tools.log')]:
 r=subprocess.run([sys.executable,str(p/script)],capture_output=True,text=True)
 (dest/logname).write_text(r.stdout+r.stderr,encoding='utf-8')
 if r.returncode:raise SystemExit(script+' failed: '+r.stdout+r.stderr)
 print(script,'PASS',flush=True)
shutil.copy2(p/'sim/out/top_structure.json',dest/'top_structure.json')
shutil.copy2(p/'sim/results/production_geometry.json',dest/'production_geometry.json')
print('EVIDENCE',dest,flush=True)
