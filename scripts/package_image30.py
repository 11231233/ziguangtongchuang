"""Gate a reproducible release on current sources, regressions and final PDS timing."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import zipfile

root=Path(__file__).resolve().parents[1]
build=root/'build/image30_final_20261027'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

parent=read(root/'reports/parent_manifest.json')
changed=[]
for name,digest in parent['files'].items():
    assert sha(Path(parent['parent'])/name)==digest, 'Parent modified: '+name
    if sha(root/name)!=digest:changed.append(name)
assert set(changed)=={'rtl/cam/ov5640_checked_config.v','rtl/video/quality_display.v','rtl/top/top_pangu50.v'},changed
assert read(root/'reports/image30_regression.json')['passed']
assert read(root/'reports/image30_regression.json')['complete']
assert read(root/'reports/image30_check_test.json')['passed']
for name in ['image30_config_test','quality_natural_test','quality_display_test',
             'quality_controls_test','single_uart_test','single_uart_84m_test',
             'display_pipeline_test','sensor_diag_test','audit_tests','fps30_test']:
    report=read(root/'reports'/f'{name}.json')
    assert report['passed'],name
    for n,h in report.get('source_sha256',{}).items():assert sha(root/n)==h,(name,n)
reg=max((root/'sim/results').glob('*/summary.json'),key=lambda f:f.stat().st_mtime)
regression=read(reg)
assert regression['passed'] and regression['complete'] and len(regression['tests'])==40
for n,h in regression['rtl_sha256'].items():assert sha(root/n)==h,n
shutil.copy2(reg,root/'reports/rtl_regression_summary.json')
full=max((root/'sim/results').glob('full720_*/result.json'),key=lambda f:f.stat().st_mtime)
frame=read(full)
assert frame['passed'] and frame['exact_compared_pixels']==921600
assert frame['selected_preset'] and frame['shared_capture_display_ddr_modeled']
for n,h in frame['rtl_sha256'].items():assert sha(root/n)==h,n
dest=root/'reports/full720';dest.mkdir(exist_ok=True)
for name in ['result.json','full720.log','full720_compile.log','frame_coef.vh']:shutil.copy2(full.parent/name,dest/name)
validation=read(build/'validation.json')
assert validation['passed'],validation
inputs=read(build/'input_manifest.json')
for n,h in inputs.items():assert sha(root/n)==h,n
assert 'Design Summary : All Constraints Met' in (build/'report_timing/top_pangu50.rtr').read_text(errors='replace')
for a,b in [('validation.json','PDS_validation.json'),('input_manifest.json','PDS_input_manifest.json'),
            ('report_timing/top_pangu50.rtr','PDS_timing.rtr'),('device_map/top_pangu50.dmr','PDS_device_map.dmr')]:
    shutil.copy2(build/a,root/'reports'/b)
resources={}
dmr=(build/'device_map/top_pangu50.dmr').read_text(errors='replace')
for name in ['FF','LUT','Distributed RAM','DRM','APM']:
    m=re.search(r'^\|\s*'+re.escape(name)+r'\s*\|\s*(\d+)\s*\|',dmr,re.M)
    assert m,name
    resources[name]=int(m[1])
firmware=root/'firmware/OV5640_C1_IMAGE30_720P60.sbit'
assert (build/'generate_bitstream/top_pangu50.sbit').stat().st_size==2101696
shutil.copy2(build/'generate_bitstream/top_pangu50.sbit',firmware)
manifest=dict(passed=True,base_project=parent['parent'],changed_rtl=changed,
    build=validation,firmware=firmware.name,firmware_sha256=sha(firmware),
    input_sha256=inputs,mapped_resources=resources,
    camera_format='1280x720 RGB565 8-bit DVP',camera_pclk_mhz=84,
    hts=1892,vts=740,nominal_sensor_fps=84000000/(2*1892*740),
    hdmi_refresh_hz=60,default_enhancement='Q2 natural',
    real_board_tested=False,real_stable_30fps_verified=False,
    input_delay_constraints_complete=False,physical_image_quality_verified=False,
    full720_simulation_compared_pixels=frame['exact_compared_pixels'],
    full720_simulation_cycles=frame['frame_cycles'],
    note='Simulation and configured-constraint PDS checks passed. No automatic flashing or real camera performance claim.')
(root/'firmware/manifest_image30.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
skip={'build','validation','__pycache__','out','results','.git'}
exclude={'delivery_manifest.json','SHA256SUMS.txt','.vectors.lock','packaging_console.log'}
files=[f for f in root.rglob('*') if f.is_file() and not(set(f.relative_to(root).parts)&skip)
       and f.name not in exclude and f.suffix.lower()!='.zip']
inventory={f.relative_to(root).as_posix():sha(f) for f in sorted(files)}
(root/'delivery_manifest.json').write_text(json.dumps(dict(files=inventory,firmware_sha256=sha(firmware)),indent=2),encoding='utf-8')
archive=root/'OV5640_C1_IMAGE30_20261027.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
    for name in inventory:z.write(root/name,name)
    z.write(root/'delivery_manifest.json','delivery_manifest.json')
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for name,h in inventory.items():assert hashlib.sha256(z.read(name)).hexdigest()==h,name
for name,h in inventory.items():assert sha(root/name)==h,name
(root/'SHA256SUMS.txt').write_text(f'{sha(firmware)}  firmware/{firmware.name}\n{sha(archive)}  {archive.name}\n',encoding='ascii')
print(json.dumps(dict(passed=True,firmware=str(firmware),sha256=sha(firmware),archive=str(archive),files=len(inventory),resources=resources),indent=2))
