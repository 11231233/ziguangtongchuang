"""Verify the responsive preview update and retain reproducible CPU evidence."""
import hashlib,importlib.util,json,os,statistics,subprocess,sys,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'reports/preview_performance_20261029';out.mkdir(exist_ok=True)
env=os.environ.copy();env['PYTHONIOENCODING']='utf-8';env['PYTHONUTF8']='1'
checks=[]
for name in ['scripts/test_preview_stream.py','scripts/test_alternative_denoise.py','scripts/test_preview_denoise.py','scripts/test_capture_direction.py','scripts/test_preview_orientation.py','scripts/test_preview_layout.py','scripts/check_calibration_gui.py']:
    command=[sys.executable,str(ROOT/name)]
    if name.endswith('check_calibration_gui.py'):command+=['--out',str(out/'gui_smoke.json')]
    run=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,encoding='utf-8',errors='replace')
    (out/(Path(name).stem+'.log')).write_text(run.stdout+run.stderr,encoding='utf-8')
    checks.append(dict(script=name,passed=run.returncode==0))
    if run.returncode:print(run.stdout+run.stderr);raise SystemExit(run.returncode)
sys.path.insert(0,str(ROOT/'tools'))
from preview_denoise import repair_small_spots
spec=importlib.util.spec_from_file_location('previous_filter',ROOT/'experiments/preview_performance_20261029/preview_denoise_before.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
cases=[]
for name,points in [('one_spot',[(300,600)]),('many_spots',[(y,x) for y in range(20,700,24) for x in range(20,1260,32)])]:
    frame=np.full((720,1280,3),80,np.uint8)
    for y,x in points:frame[y:y+2,x:x+2]=255
    case=dict(case=name,spot_clusters=len(points),synthetic_only=True)
    for version,fn in [('before',old.repair_small_spots),('after',repair_small_spots)]:
        fn(frame);times=[]
        for _ in range(7):
            started=time.perf_counter();image,mask=fn(frame);times.append((time.perf_counter()-started)*1000)
        case[version+'_processing_ms_median']=statistics.median(times)
        case[version+'_replaced_pixels']=int(mask.sum())
    cases.append(case)
manifest=json.loads((ROOT/'firmware/manifest_image30.json').read_text(encoding='utf-8'))
assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest for name,digest in manifest['input_sha256'].items())
files=['tools/calibration_console.py','tools/preview_stream.py','tools/preview_denoise.py','scripts/test_preview_stream.py','scripts/test_alternative_denoise.py','scripts/verify_preview_performance.py']
report=dict(passed=True,complete=True,checks=checks,synthetic_filter_benchmark=cases,hardware_preview_fps_verified=False,
            fpga_build_inputs_unchanged=True,old_preview_extra_wait_ms=100,new_preview_poll_target_ms=33,
            latest_frame_only=True,ui_camera_read=False,ui_live_filter=False,
            user_report='USB-TTL ground connected; some sparkles reduced but many remain. Cause not conclusively isolated.',
            source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files})
(out/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report|{'source_sha256':'see validation.json'},ensure_ascii=False,indent=2))
