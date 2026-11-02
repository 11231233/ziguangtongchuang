"""Package the RAW acquisition candidate, never claim true calibration release."""
from pathlib import Path
import json,hashlib,shutil,zipfile,datetime,re,argparse
ap=argparse.ArgumentParser();ap.add_argument('--archive-name',default='C1_MARGIN20_RAW_CALIB_20261031.zip');args=ap.parse_args()
assert re.fullmatch(r'[A-Za-z0-9_-]+\.zip',args.archive_name),'Archive must be a simple ZIP filename'
ROOT=Path(__file__).resolve().parents[1];BUILD=ROOT/'build/margin_raw1296_20261031'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def latest(pattern):
 rows=sorted((ROOT/'reports').glob(pattern));assert rows,pattern
 return rows[-1]
assert read(BUILD/'validation.json')['passed']
assert all(sha(ROOT/n)==h for n,h in read(BUILD/'input_manifest.json').items()),'PDS inputs changed'
legacy=sorted((ROOT/'sim/results').glob('*/summary.json'))[-1]
assert read(legacy)['passed'] and read(legacy)['complete'] and len(read(legacy)['tests'])==40
reports=[legacy,*[latest(p+'/result.json') for p in ['margin_writer_full_*','margin_checked_*','margin_footer_*','margin_top_*','margin_view_0_*','margin_view_3_*','runtime_template_*','margin_corrected_20_*']],ROOT/'reports/software_verification.json',ROOT/'reports/coverage_algorithm_test.json']
for p in reports:
 d=read(p);assert d['passed'],str(p)
 for field in ['source_sha256','rtl_sha256']:
  assert all(sha(ROOT/n)==h for n,h in d.get(field,{}).items()),str(p)
assert read(ROOT/'reports/coverage_algorithm_test.json')['synthetic_test_only']
assert read(latest('margin_corrected_20_*/result.json'))['synthetic_test_only']
firm=ROOT/'firmware/C1_WIDE_RAW_1296X972_720P60_CALIB.sbit'
shutil.copy2(BUILD/'generate_bitstream/top_pangu50.sbit',firm)
rollback=ROOT/'firmware/ROLLBACK_KEY_ANGLE.sbit'
assert sha(rollback)=='67f47f64dba60a0672a5de3345b53bff8cfbd907548f71e712323dd8771be025'
pds=ROOT/'reports/pds';pds.mkdir(exist_ok=True)
for name in ['validation.json','input_manifest.json','console.log','build.tcl','report_timing/top_pangu50.rtr']:
 shutil.copy2(BUILD/name,pds/Path(name).name)
console=(BUILD/'console.log').read_text(errors='replace');resources={}
for name,caps in [('FF',(38700,25500)),('LUT',(25800,17000))]:
 values={int(cap):int(used) for used,cap in re.findall(r'\|\s*'+name+r'\s*\|\s*(\d+)\s*\|\s*(\d+)',console) if int(cap) in caps}
 assert set(values)==set(caps);resources[name]=sum(values.values())
for name in ['DRM','APM']:resources[name]=int(re.findall(r'\|\s*'+name+r'\s*\|\s*(\d+)',console)[-1])
summary=dict(created_at=datetime.datetime.now().astimezone().isoformat(),passed=True,
 scope='Offline RAW acquisition build and preparation tools only; not final calibrated correction release',
 hardware_programmed=False,hardware_tested=False,geometry_physically_verified=False,
 real_calibration_complete=False,formal_correction_released=False,live_30fps_verified=False,
 target_rotation_degrees=[-20,20],output_size=[1280,720],source_size=[1296,972],source_stride_pixels=1536,
 geometry=read(ROOT/'targets/capture_geometry.json'),firmware=dict(file=firm.relative_to(ROOT).as_posix(),sha256=sha(firm),role='raw_full_window_acquisition_only'),
 rollback=dict(file=rollback.relative_to(ROOT).as_posix(),sha256=sha(rollback)),
 pds_resources=resources,pds_configured_constraints_met=True,reports=[p.relative_to(ROOT).as_posix() for p in reports],
 limits=['Final real calibration requires verified full-window evidence and independent precision/coverage gates','Only frozen same-frame P0-P3 groups may be reconstructed',
 'Source VTS=1000 at original PLL: expected lower source FPS; HDMI remains 60Hz',
 '20 train + 6 held-out new RAW groups and full geometry/coverage gate required',
 'Final model-specific RTL/PDS and board 720P30/quality validation still required',
 'Synthetic numerical and RTL tests are not physical calibration'])
write(ROOT/'reports/validation_summary.json',summary)
write(ROOT/'firmware/manifest.json',dict(main=summary['firmware'],rollback=summary['rollback'],
 real_calibration_complete=False,formal_correction_released=False,hardware_programmed=False,
 target_rotation_degrees=[-20,20],capture_version_key2_key3='next/previous page, NOT angle controls'))
selected=set()
for name in ['rtl','constr','scripts','tools','targets','sim/tb','sim/model','firmware','docs']:
 selected.update(p for p in (ROOT/name).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ['.pyc','.vvp'])
selected.update([ROOT/'README.md',ROOT/'启动全窗口标定助手.cmd',ROOT/'reports/validation_summary.json',ROOT/'reports/geometry_audit.json'])
selected.update(p for p in pds.glob('*') if p.is_file())
for p in reports:
 selected.add(p)
 # Root-level records do not pull in unrelated reports, synthetic project trees or vectors.
 if p.parent!=ROOT/'reports':selected.update(p.parent.glob('*.log'))
manifest={p.relative_to(ROOT).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(selected)}
write(ROOT/'delivery_manifest.json',dict(files=manifest,manifest_self_excluded=True));selected.add(ROOT/'delivery_manifest.json')
archive=ROOT.parent/args.archive_name
with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
 for p in sorted(selected):z.write(p,'C1_MARGIN20_RAW_CALIB/'+p.relative_to(ROOT).as_posix())
with zipfile.ZipFile(archive) as z:
 assert z.testzip() is None
 assert all(hashlib.sha256(z.read('C1_MARGIN20_RAW_CALIB/'+n)).hexdigest()==v['sha256'] for n,v in manifest.items())
result=dict(archive=str(archive),sha256=sha(archive),files=len(selected),bytes=archive.stat().st_size,
 all_zip_hashes_verified=True,hardware_tested=False,real_calibration_complete=False,formal_correction_released=False)
write(archive.with_suffix('.json'),result);print(json.dumps(result|dict(firmware=summary['firmware'],resources=resources),indent=2))
