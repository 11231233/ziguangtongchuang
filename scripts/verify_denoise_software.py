"""Validate the optional PC denoising update without touching hardware."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];folder=ROOT/'reports/denoise_20261029';folder.mkdir(exist_ok=True)
env=os.environ.copy();env['PYTHONIOENCODING']='utf-8';env['PYTHONUTF8']='1'
results=[]
for name in ['scripts/test_preview_denoise.py','scripts/test_capture_direction.py','scripts/test_preview_orientation.py','scripts/test_preview_layout.py','scripts/check_calibration_gui.py']:
    cmd=[sys.executable,str(ROOT/name)]
    if name.endswith('check_calibration_gui.py'):cmd+=['--out',str(folder/'gui_smoke.json')]
    job=subprocess.run(cmd,cwd=ROOT,env=env,capture_output=True,encoding='utf-8',errors='replace')
    path=folder/(Path(name).stem+'.log');path.write_text(job.stdout+job.stderr,encoding='utf-8')
    results.append(dict(script=name,passed=job.returncode==0,log=path.relative_to(ROOT).as_posix()))
    if job.returncode:print(job.stdout+job.stderr);raise SystemExit(job.returncode)
manifest=json.loads((ROOT/'firmware/manifest_image30.json').read_text(encoding='utf-8'))
changed=[name for name,digest in manifest['input_sha256'].items() if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest]
if changed:raise SystemExit('FPGA build input changed: '+str(changed))
files=['tools/preview_denoise.py','tools/denoise_compare.py','tools/calibration_console.py','scripts/test_preview_denoise.py','scripts/evaluate_preview_denoise.py','scripts/verify_denoise_software.py']
report=dict(passed=True,complete=True,scope='PC preview denoising only; real camera quality not verified',checks=results,
            fpga_build_inputs_unchanged=True,fpga_denoise_applied=False,firmware_sha256=hashlib.sha256((ROOT/'firmware'/manifest['firmware']).read_bytes()).hexdigest(),
            source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files})
(folder/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report|{'source_sha256':'see validation.json'},ensure_ascii=False,indent=2))
