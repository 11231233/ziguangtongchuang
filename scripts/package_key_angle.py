"""Ship the validated board-key release. Never opens hardware or serial."""
from pathlib import Path
import json,hashlib,shutil,zipfile,datetime,re
ROOT=Path(__file__).resolve().parents[1];BUILD=ROOT/'build/key_angle_20261031'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
build=read(BUILD/'validation.json');assert build['passed']
inputs=read(BUILD/'input_manifest.json');assert all(sha(ROOT/n)==h for n,h in inputs.items())
legacy=sorted((ROOT/'sim/results').glob('*/summary.json'))[-1]
unit=sorted((ROOT/'reports').glob('key_angles_*/result.json'))[-1]
frames=[sorted((ROOT/'reports').glob(f'angle_frame_{a}_*/result.json'))[-1] for a in (0,15,-90)]
reports=[legacy,unit,ROOT/'reports/key_angle_top_test.json',ROOT/'reports/angle_osd/result.json',ROOT/'reports/zero_original_comparison.json',*frames]
for f in reports:
 d=read(f);assert d['passed'],str(f)
 for key in ('rtl_sha256','source_sha256'):
  assert all(sha(ROOT/n)==h for n,h in d.get(key,{}).items()),str(f)
assert read(legacy)['complete'] and len(read(legacy)['tests'])==40
assert read(unit)['settings_compared']==1080
assert all(read(f)['pixels_compared']==921600 and not read(f)['source_changed'] for f in frames)
firm=ROOT/'firmware/C1_KEY_ANGLE_720P60.sbit';shutil.copy2(BUILD/'generate_bitstream/top_pangu50.sbit',firm)
assert sha(ROOT/'firmware/ROLLBACK_STANDALONE.sbit')=='84ce6edea8472f9cf56894b0ba3f5d2a6a8217a26ea69b058f58ceba11df91bf'
assert sha(ROOT/'firmware/RESTORE_ORIGINAL_C1.sbit')=='30a9237480f627b25055f31ef8c2a19cb196989235982ea3b1ab4ca972b9d673'
pds=ROOT/'reports/pds';pds.mkdir(exist_ok=True)
for source in ['validation.json','input_manifest.json','report_timing/top_pangu50.rtr','console.log','build.tcl']:
 shutil.copy2(BUILD/source,pds/Path(source).name)
console=(BUILD/'console.log').read_text(errors='replace');resources={}
for name,capacities in [('FF',(38700,25500)),('LUT',(25800,17000))]:
 parts={int(cap):int(used) for used,cap in re.findall(r'\|\s*'+name+r'\s*\|\s*(\d+)\s*\|\s*(\d+)',console) if int(cap) in capacities}
 assert set(parts)==set(capacities);resources[name]=sum(parts.values())
for name in ('DRM','APM'):resources[name]=int(re.findall(r'\|\s*'+name+r'\s*\|\s*(\d+)',console)[-1])
summary=dict(created_at=datetime.datetime.now().astimezone().isoformat(),passed=True,
 hardware_programmed=False,hardware_tested=False,live_30fps_verified=False,
 firmware=dict(file=firm.relative_to(ROOT).as_posix(),sha256=sha(firm)),
 board_controls=dict(angle_min=-180,angle_max=179,step_degrees=1,hold_repeat_hz=10,hold_delay_seconds=.5,
  key2='plus',key3='minus',chord='zero; hold 2 seconds restores geometry defaults',key0='short RAW/COR; long zoom',key1='short strength; long freeze'),
 original_zero_mapping_preserved=True,new_calibration_loaded=False,host_control_enabled=False,
 affine_slopes_fraction_bits=24,other_fields_fraction_bits=16,
 model_scope='Original C1 empirical presets; no new true-lens calibration claim',
 reports=[p.relative_to(ROOT).as_posix() for p in reports],
 full_frames=[{k:v for k,v in read(p).items() if k not in ('rtl_sha256','coeff')} for p in frames],
 pds_resources=resources,
 limits=['No board image/FPS validation','External IO timing/DDR electrical behavior require board validation','Angles are manual; no IMU/horizon detection or full perspective correction'])
write(ROOT/'reports/validation_summary.json',summary)
write(ROOT/'firmware/manifest.json',dict(main=summary['firmware'],rollback={p.name:sha(p) for p in (ROOT/'firmware').glob('*.sbit') if p!=firm},hardware_programmed=False))
selected=set()
for folder in ['rtl','constr','scripts','tools','targets','sim/tb','sim/model','firmware']:
 selected.update(p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.vvp'))
selected.update([ROOT/'README.md',ROOT/'reports/validation_summary.json'])
selected.update(p for p in pds.glob('*') if p.is_file())
for f in reports:
 selected.add(f);selected.update(p for p in f.parent.glob('*.log') if p.is_file())
for name in ['key_angle_top.log','key_angle_top_compile.log']:selected.add(ROOT/'sim/out'/name)
manifest={p.relative_to(ROOT).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(selected)}
write(ROOT/'delivery_manifest.json',dict(files=manifest,manifest_self_excluded=True));selected.add(ROOT/'delivery_manifest.json')
archive=ROOT.parent/'C1_KEY_ANGLE_20261031.zip'
with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
 for p in sorted(selected):z.write(p,'C1_KEY_ANGLE/'+p.relative_to(ROOT).as_posix())
with zipfile.ZipFile(archive) as z:
 assert z.testzip() is None
 assert all(hashlib.sha256(z.read('C1_KEY_ANGLE/'+n)).hexdigest()==row['sha256'] for n,row in manifest.items())
result=dict(archive=str(archive),sha256=sha(archive),files=len(selected),bytes=archive.stat().st_size,all_zip_hashes_verified=True,hardware_tested=False)
write(archive.with_suffix('.json'),result)
print(json.dumps(summary|result,ensure_ascii=False,indent=2))
