"""Publish only a source-matched, timing-clean candidate; never flashes hardware."""
from pathlib import Path
import hashlib
import json
import shutil
import re
import zipfile

root=Path(__file__).resolve().parents[1]
build=root/'build/c1_q2_rgb565_fps30_20261027_c'
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
validation=json.loads((build/'validation.json').read_text())
assert validation['passed'],validation
inputs=json.loads((build/'input_manifest.json').read_text())
for name,sha in inputs.items():
    assert digest(root/name)==sha,'Source drift: '+name
for name in ['fps30_test.json','single_uart_84m_test.json','sensor_diag_test.json','c2_checked_test.json','osd_pipeline_test.json','display_pipeline_test.json']:
    assert json.loads((root/'reports'/name).read_text())['passed'],name
structure=json.loads((root/'sim/out/top_structure.json').read_text())
assert structure['passed']
summary_path=max((root/'sim/results').glob('*/summary.json'),key=lambda p:p.stat().st_mtime)
summary=json.loads(summary_path.read_text())
assert summary['passed'] and summary['complete'] and len(summary['tests'])==40
for name,sha in summary['rtl_sha256'].items():assert digest(root/name)==sha
parent=Path(r'F:\codex_jibian_completion')
baseline=json.loads((root/'reports/parent_source_sha256.json').read_text())
assert all(digest(parent/name)==sha for name,sha in baseline.items()),'Parent changed'
rollback=root/'firmware/ROLLBACK_C1_15FPS_720P60.sbit'
assert digest(rollback)=='3ce8255b7d7cbc87d85c40bfd0b4bfdc0b44145b61b44e486bdc380987043deb'
timing=build/'report_timing/top_pangu50.rtr'
timing_text=timing.read_text(errors='replace')
assert 'Design Summary : All Constraints Met' in timing_text
slacks={}
for clock in ['clk_pix','ddrphy_clkin','cam_pclk']:
    row=re.search(r'^\s*'+clock+r'\s+\d+\.\d+ MHz\s+\d+\.\d+ MHz\s+\d+\.\d+\s+\d+\.\d+\s+(-?\d+\.\d+)',timing_text,re.M)
    assert row,clock
    slacks[clock]=float(row[1])
shutil.copy2(timing,root/'reports/PDS_timing.rtr')
shutil.copy2(build/'validation.json',root/'reports/PDS_validation.json')
shutil.copy2(build/'input_manifest.json',root/'reports/PDS_input_manifest.json')
shutil.copy2(summary_path,root/'reports/rtl_regression_summary.json')
shutil.copy2(root/'sim/out/top_structure.json',root/'reports/top_structure.json')
bit=root/'firmware/OV5640_C1_RGB565_FPS30_720P60.sbit'
shutil.copy2(build/'generate_bitstream/top_pangu50.sbit',bit)
assert bit.stat().st_size==2101696
changed=[name for name,sha in baseline.items() if digest(root/name)!=sha]
assert set(changed)=={'rtl/cam/ov5640_checked_config.v','rtl/top/top_pangu50.v','rtl/video/metrics_osd.v'},changed
manifest=dict(date='2026-10-27',bitstream=bit.name,bytes=bit.stat().st_size,sha256=digest(bit),
    rollback=rollback.name,rollback_sha256=digest(rollback),build=validation,
    parent_sources_unchanged=True,modified_parent_files=changed,RGB565_preserved=True,
    output_size=[1280,720],HDMI_refresh_hz=60,theoretical_sensor_fps=29.9982858122393,
    theoretical_camera_byte_clock_mhz=84,critical_PLL_readback=True,
    setup_slack_ns=slacks,
    OSD_additional_pipeline_cycles=1,OSD_alignment_test_points=67200,
    real_lens_calibration_complete=False,physical_high_speed_tested=False,
    external_DVP_input_delay_constraints_complete=False,rtl_tests_passed=40)
(root/'firmware/manifest_fps30.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
files=[]
for p in root.rglob('*'):
    rel=p.relative_to(root)
    if not p.is_file() or rel.parts[0]=='build' or '__pycache__' in rel.parts or rel.parts[:2]==('sim','out') or p.suffix=='.zip' or p.name in ['delivery_manifest.json','SHA256SUMS.txt']:
        continue
    files.append((p,rel.as_posix()))
inventory=[dict(path=name,sha256=digest(p),bytes=p.stat().st_size) for p,name in files]
(root/'delivery_manifest.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf-8')
archive=root/'OV5640_C1_RGB565_FPS30_20261027.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p,name in files:z.write(p,name)
    z.write(root/'delivery_manifest.json','delivery_manifest.json')
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for item in inventory:assert hashlib.sha256(z.read(item['path'])).hexdigest()==item['sha256']
(root/'SHA256SUMS.txt').write_text(digest(archive)+'  '+archive.name+'\n'+digest(bit)+'  firmware/'+bit.name+'\n',encoding='utf-8')
print(json.dumps(manifest,ensure_ascii=False,indent=2))
print('ZIP verified:',archive,digest(archive))
