from pathlib import Path
import json,subprocess,sys,tempfile
from sim_lock import acquire,release
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as folder:
    lock=acquire(folder)
    code='import sys;from sim_lock import acquire;acquire(sys.argv[1])'
    busy=subprocess.run([sys.executable,'-c',code,folder],cwd=root/'scripts',capture_output=True,text=True)
    assert busy.returncode!=0 and 'Another simulation workflow' in busy.stderr
    release(lock)
    ready=subprocess.run([sys.executable,'-c',code,folder],cwd=root/'scripts',capture_output=True,text=True)
    assert ready.returncode==0,ready.stdout+ready.stderr
(root/'reports/simulation_lock_test.json').write_text(json.dumps(dict(passed=True,
    concurrent_workflow_rejected=True,released_lock_reusable=True,hardware_tested=False),indent=2),encoding='utf-8')
print('SIM_LOCK PASS: concurrent vector generation blocked, lock released and reusable')
