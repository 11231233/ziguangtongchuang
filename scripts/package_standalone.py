"""Validate and package the standalone build; no board or serial operations."""
from pathlib import Path
import json,hashlib,shutil,zipfile,datetime,re
ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/'build/standalone_pipeline_20261030'
BASE=ROOT.parent/'competition_20261029'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
build=read(BUILD/'validation.json');assert build['passed']
inputs=read(BUILD/'input_manifest.json')
assert all(sha(ROOT/n)==h for n,h in inputs.items())
original=read(BASE/'evidence/baseline_20261027/manifest_image30.json')
assert all(sha(BASE/n)==h for n,h in original['input_sha256'].items())
changed=[p.relative_to(ROOT).as_posix() for p in (ROOT/'rtl').rglob('*') if p.is_file() and sha(p)!=sha(BASE/p.relative_to(ROOT))]
assert sorted(changed)==['rtl/top/top_pangu50.v','rtl/warp/warp_frame.v'],changed
legacy=sorted((ROOT/'sim/results').glob('*/summary.json'))[-1];reg=read(legacy)
ab=sorted((ROOT/'reports').glob('lookahead_*/result.json'))[-1]
full=sorted((ROOT/'reports').glob('standalone_full_*/result.json'))[-1]
reports=[legacy,ab,full,ROOT/'reports/single_uart_test.json',ROOT/'reports/single_uart_84m_test.json']
for f in reports:
 d=read(f);assert d['passed'],str(f)
 assert all(sha(ROOT/n)==h for n,h in d.get('rtl_sha256',{}).items())
 assert all(sha(ROOT/n)==h for n,h in d.get('source_sha256',{}).items())
assert reg['complete'] and len(reg['tests'])==40
assert read(full)['exact_compared_pixels']==921600
firm=ROOT/'firmware/C1_STANDALONE_PIPELINE_720P60.sbit'
shutil.copy2(BUILD/'generate_bitstream/top_pangu50.sbit',firm)
rollback=ROOT/'firmware/RESTORE_ORIGINAL_C1.sbit'
assert sha(rollback)==original['firmware_sha256']
pds=ROOT/'reports/pds';pds.mkdir(exist_ok=True)
for source in ['validation.json','input_manifest.json','report_timing/top_pangu50.rtr','device_map/top_pangu50_dmr.prt','console.log']:
 shutil.copy2(BUILD/source,pds/Path(source).name)
historical=ROOT/'reports/original_baseline';historical.mkdir(exist_ok=True)
old_path=BASE/'sim/results/full720_20261029_101002/result.json';old=read(old_path)
assert old['passed'] and old['selected_preset'] and old['shared_capture_display_ddr_modeled']
assert all(sha(BASE/n)==h for n,h in old['rtl_sha256'].items())
shutil.copy2(old_path,historical/'full720_result.json')
shutil.copy2(BASE/'evidence/baseline_20261027/manifest_image30.json',historical/'firmware_manifest.json')
summary=dict(created_at=datetime.datetime.now().astimezone().isoformat(),passed=True,hardware_programmed=False,hardware_tested=False,
 standalone_host_control_enabled=False,original_optical_parameters_preserved=True,changed_rtl=changed,
 firmware=dict(file=firm.relative_to(ROOT).as_posix(),sha256=sha(firm)),
 rollback=dict(file=rollback.relative_to(ROOT).as_posix(),sha256=sha(rollback)),
 checks=[p.relative_to(ROOT).as_posix() for p in reports],
 original_40_regressions_passed=True,full_frame_pixels_exact=921600,
 small_ab=read(ab)['cases'],full_sim_cycles=read(full)['frame_cycles'],
 historical_original_full_sim_cycles=old['frame_cycles'],
 full_sim_cycles_saved=old['frame_cycles']-read(full)['frame_cycles'],
 historical_comparison=True,live_30fps_verified=False,
 limits=['Simulation memory model, not DDR PHY measurement','External IO constraints incomplete','Original empirical optical model retained','Real image/noise/FPS need board comparison'])
console=(BUILD/'console.log').read_text(errors='replace')
summary['pds_resources']={n:int(re.findall(r'\|\s*'+n+r'\s*\|\s*(\d+)',console)[-1]) for n in ['FF','LUT','DRM','APM']}
for name,capacities in [('FF',(38700,25500)),('LUT',(25800,17000))]:
 rows=re.findall(r'\|\s*'+name+r'\s*\|\s*(\d+)\s*\|\s*(\d+)',console)
 parts={int(cap):int(used) for used,cap in rows if int(cap) in capacities}
 assert set(parts)==set(capacities)
 summary['pds_resources'][name]=sum(parts.values())
summary['pds_resources_scope']='Final routed CLMA+CLMS totals; not the pre-routing map table.'
write(ROOT/'reports/validation_summary.json',summary)
write(ROOT/'firmware/manifest.json',dict(optimized=summary['firmware'],original=summary['rollback'],hardware_programmed=False))
selected=set()
for folder in ['rtl','constr','scripts','tools','targets','sim/tb','sim/model','firmware']:
 selected.update(p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ['.pyc','.vvp'])
selected.add(ROOT/'README.md');selected.add(ROOT/'reports/validation_summary.json');selected.add(ROOT/'reports/origin.json')
selected.update(p for p in pds.rglob('*') if p.is_file());selected.update(p for p in historical.rglob('*') if p.is_file())
for f in reports:
 selected.add(f)
 selected.update(p for p in f.parent.glob('*.log') if p.is_file())
for n in ['single_uart.log','single_uart_compile.log','single_uart_84m.log','single_uart_84m_compile.log']:selected.add(ROOT/'sim/out'/n)
manifest={p.relative_to(ROOT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(selected)}
write(ROOT/'delivery_manifest.json',dict(files=manifest,manifest_self_excluded=True));selected.add(ROOT/'delivery_manifest.json')
archive=ROOT.parent/'C1_STANDALONE_PIPELINE_20261030.zip'
with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
 for p in sorted(selected):z.write(p,'C1_STANDALONE_PIPELINE/'+p.relative_to(ROOT).as_posix())
with zipfile.ZipFile(archive) as z:
 assert z.testzip() is None
 assert all(hashlib.sha256(z.read('C1_STANDALONE_PIPELINE/'+n)).hexdigest()==v['sha256'] for n,v in manifest.items())
result=dict(archive=str(archive),sha256=sha(archive),files=len(selected),bytes=archive.stat().st_size,all_zip_hashes_verified=True)
write(archive.with_suffix('.json'),result)
print(json.dumps(summary|result,ensure_ascii=False,indent=2))
