"""Run host-side checks sequentially, with auditable per-command logs."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
(ROOT/'build').mkdir(exist_ok=True)
checks=['scripts/test_competition_tools.py','scripts/test_host_sweep.py','scripts/test_image30_check.py','scripts/test_host_tools.py','scripts/test_completion.py','scripts/test_latency.py','scripts/test_calibration.py','scripts/test_calib_to_fpga.py','scripts/test_straightness.py','scripts/test_quality_workbench.py','tools/test_calibration_workflow.py']
folder=ROOT/'reports'/('host_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
folder.mkdir(parents=True)
env=os.environ.copy();env['PYTHONIOENCODING']='utf-8';env['PYTHONUTF8']='1'
results=[]
for name in checks:
    print('RUN',name,flush=True)
    run=subprocess.run([sys.executable,str(ROOT/name)],cwd=ROOT,env=env,capture_output=True,encoding='utf-8',errors='replace')
    log=folder/(Path(name).stem+'.log')
    log.write_text(run.stdout+run.stderr,encoding='utf-8')
    results.append(dict(script=name,passed=run.returncode==0,log=log.relative_to(ROOT).as_posix()))
    (ROOT/'reports/host_validation_20261029.json').write_text(json.dumps(dict(passed=all(r['passed'] for r in results),complete=len(results)==len(checks),synthetic_only=True,checks=results),indent=2),encoding='utf-8')
    if run.returncode:
        print(run.stdout+run.stderr);raise SystemExit(run.returncode)
print('HOST VALIDATION PASS',len(results),flush=True)
