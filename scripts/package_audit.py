"""Release only source-matched, tested, timing-clean audit artifacts."""
from pathlib import Path
import hashlib,json,re,shutil,zipfile

root=Path(__file__).resolve().parents[1]
build=root/'build/audit_opt_fast_20261027'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def load(path):return json.loads((root/path).read_text(encoding='utf-8-sig'))
validation=load('reports/PDS_validation.json');assert validation['passed']
assert validation['build']=='audit_opt_fast_20261027'
inputs=load('reports/PDS_input_manifest.json')
assert all(sha(root/n)==h for n,h in inputs.items())
checks=['audit_tests.json','rtl_regression_summary.json','coordinate_cases_summary.json','top_structure.json',
        'single_uart_84m_test.json','sensor_diag_test.json','display_pipeline_test.json','osd_pipeline_test.json',
        'fps27_test.json','simulation_lock_test.json','software_checks/summary.json','memory_layout.json',
        'resource_performance_comparison.json']
for name in checks:
    value=load('reports/'+name);assert value['passed'],name
    hashes=value.get('source_sha256',value.get('rtl_sha256',{}))
    for n,h in hashes.items():assert sha(root/n)==h,name+': stale source '+n
assert len(load('reports/rtl_regression_summary.json')['tests'])==40
assert len(load('reports/audit_tests.json')['tests'])==5
assert load('reports/performance/candidate/result.json')['exact_compared_pixels']==921600
baseline=load('reports/parent_source_sha256.json')
parent=Path(r'F:\codex_jibian_fps27_stability')
assert all(sha(parent/n)==h for n,h in baseline.items())
changed=[n for n,h in baseline.items() if sha(root/n)!=h]
assert {n for n in changed if n.startswith('rtl/')}=={
 'rtl/common/async_fifo.v','rtl/common/warp_config.v','rtl/mem/frame_writer.v','rtl/mem/mem_hub.v',
 'rtl/top/top_pangu50.v','rtl/warp/warp_frame.v','rtl/warp/warp_tile_stream.v'}
rollback=root/'firmware/ROLLBACK_KNOWN_C1_FPS15_720P60.sbit'
assert sha(rollback)=='3ce8255b7d7cbc87d85c40bfd0b4bfdc0b44145b61b44e486bdc380987043deb'
timing=(root/'reports/PDS_timing.rtr').read_text(errors='replace')
assert 'Design Summary : All Constraints Met' in timing
slacks={}
for name in ['clk_pix','ddrphy_clkin','cam_pclk']:
    row=re.search(r'^\s*'+name+r'\s+\d+\.\d+ MHz\s+\d+\.\d+ MHz\s+\d+\.\d+\s+\d+\.\d+\s+(-?\d+\.\d+)',timing,re.M)
    assert row,name
    slacks[name]=float(row[1])
bit=root/'firmware/OV5640_C1_AUDIT_OPT_720P60.sbit'
shutil.copy2(build/'generate_bitstream/top_pangu50.sbit',bit)
assert bit.stat().st_size==2101696
manifest=dict(date='2026-10-27',bitstream=bit.name,bytes=bit.stat().st_size,sha256=sha(bit),build=validation,
    parent='F:/codex_jibian_fps27_stability',parent_sources_preserved=True,modified_existing_files=changed,
    camera='C1 only',pixel_format='RGB565',image_size=[1280,720],source_slots=3,result_slots=2,
    nominal_camera_pclk_mhz=76.8,nominal_camera_fps=27.427004171190216,HDMI_refresh_hz=60,
    setup_slack_ns=slacks,tests_checked=checks,comparison=load('reports/resource_performance_comparison.json'),
    hardware_tested=False,external_DVP_input_delay_constraints_complete=False,real_lens_calibration_complete=False,
    rollback=rollback.name,rollback_sha256=sha(rollback))
(root/'firmware/manifest_audit.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
files=[]
for p in root.rglob('*'):
    rel=p.relative_to(root)
    if not p.is_file() or rel.parts[0] in ['build','validation'] or '__pycache__' in rel.parts:
        continue
    if rel.parts[:2] in [('sim','out'),('sim','results')] or 'synthetic_session' in rel.parts or p.suffix in ['.zip','.lock']:
        continue
    if p.name in ['delivery_manifest.json','SHA256SUMS.txt','release_verification.log']:continue
    files.append((p,rel.as_posix()))
inventory=[dict(path=name,sha256=sha(p),bytes=p.stat().st_size) for p,name in files]
(root/'delivery_manifest.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf-8')
archive=root/'OV5640_C1_AUDIT_OPT_20261027.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p,name in files:z.write(p,name)
    z.write(root/'delivery_manifest.json','delivery_manifest.json')
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for item in inventory:assert hashlib.sha256(z.read(item['path'])).hexdigest()==item['sha256']
(root/'SHA256SUMS.txt').write_text(sha(archive)+'  '+archive.name+'\n'+sha(bit)+'  firmware/'+bit.name+'\n',encoding='utf-8')
print(json.dumps(dict(passed=True,bitstream=bit.name,sha256=sha(bit),setup_slack_ns=slacks,files=len(inventory),
    archive=str(archive),archive_sha256=sha(archive),comparison=manifest['comparison']),ensure_ascii=False,indent=2))
