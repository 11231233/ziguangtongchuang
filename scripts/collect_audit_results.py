"""Collect consistent audit evidence; does not claim board measurements."""
from pathlib import Path
import hashlib,json,re,shutil

root=Path(__file__).resolve().parents[1]
build=root/'build/audit_opt_fast_20261027'
assert json.loads((build/'validation.json').read_text())['passed']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
inputs=json.loads((build/'input_manifest.json').read_text())
assert all(sha(root/n)==v for n,v in inputs.items())
parent=Path(r'F:\codex_jibian_fps27_stability')
baseline=json.loads((root/'reports/parent_source_sha256.json').read_text())
assert all(sha(parent/n)==v for n,v in baseline.items())

def resources(path):
    text=path.read_text(errors='replace')
    result={}
    for name in ['FF','LUT','Distributed RAM','DRM','APM']:
        m=re.search(r'^\|\s*'+re.escape(name)+r'\s*\|\s*(\d+)\s*\|',text,re.M)
        assert m,name
        result[name]=int(m[1])
    return result
old=resources(root/'reports/baseline_device_map.dmr')
new=resources(build/'device_map/top_pangu50.dmr')
assert new['FF']<old['FF'] and new['DRM']==old['DRM']
top=(root/'rtl/top/top_pangu50.v').read_text(encoding='utf-8')
width=int(re.search(r'H_ACT\s*=\s*(\d+)',top)[1]);height=int(re.search(r'V_ACT\s*=\s*(\d+)',top)[1])
slots=int(re.search(r'\.SLOT_COUNT\((\d+)\)',top)[1])
base=int(re.search(r'CORR_BASE\s*=\s*(\d+)',top)[1]);words=width*height//2
assert (width,height,slots,base)==(1280,720,3,3*words)
source=[]
for s in range(slots):
    for y in range(height):
        for chunk in range(width//256):
            start=s*words+(height-1-y)*(width//2)+chunk*128
            source.append((start,start+128))
dest=[]
for s in range(2):
    for ty in range(0,height,16):
        for tx in range(0,width,16):
            for row in range(16):
                if ty+row<height:
                    start=base+s*words+(ty+row)*(width//2)+tx//2
                    dest.append((start,start+8))
intervals=sorted(source+dest)
assert intervals[0][0]==0 and intervals[-1][1]==5*words
assert all(a[1]==b[0] for a,b in zip(intervals,intervals[1:])), 'Address gaps/overlap'
layout=dict(passed=True,static_address_enumeration=True,source_slots=slots,result_slots=2,
    source_bursts=len(source),result_packets=len(dest),byte_addressed_end=5*words*4,
    source_and_result_disjoint=True,whole_frame_coverage=True)
(root/'reports/memory_layout.json').write_text(json.dumps(layout,indent=2),encoding='utf-8')

current=max((root/'sim/results').glob('full720_*/result.json'),key=lambda p:p.stat().st_mtime)
previous=max((root/'validation/baseline/sim/results').glob('full720_*/result.json'),key=lambda p:p.stat().st_mtime)
c=json.loads(current.read_text());p=json.loads(previous.read_text())
assert all(sha(root/n)==h for n,h in c['rtl_sha256'].items())
assert c['passed'] and p['passed'] and c['exact_compared_pixels']==p['exact_compared_pixels']==921600
assert c['selected_preset'] and p['selected_preset'] and c['shared_capture_display_ddr_modeled'] and p['shared_capture_display_ddr_modeled']
for tag,file in [('candidate',current),('baseline',previous)]:
    d=root/'reports/performance'/tag;d.mkdir(parents=True,exist_ok=True)
    for name in ['result.json','full720.log','full720_compile.log','frame_coef.vh']:
        shutil.copy2(file.parent/name,d/name)
report=dict(passed=True,resources_before=old,resources_after=new,
    resource_deltas={n:new[n]-old[n] for n in old},FF_reduction_percent=(old['FF']-new['FF'])/old['FF']*100,
    DDR_image_bytes_before=8*words*4,DDR_image_bytes_after=5*words*4,DDR_reduction_percent=37.5,
    full720_baseline_cycles=p['frame_cycles'],full720_candidate_cycles=c['frame_cycles'],
    cycle_improvement_percent=(p['frame_cycles']-c['frame_cycles'])/p['frame_cycles']*100,
    output_pixels_bit_exact=921600,hardware_speedup_measured=False,
    note='Same abstract DDR workload, no DDR PHY. Request-wait counters changed semantics with exact ready; compare total cycles.')
(root/'reports/resource_performance_comparison.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
summaries=[]
for file in (root/'sim/results').glob('*/summary.json'):
    value=json.loads(file.read_text())
    if len(value.get('tests',[]))==40 and value.get('complete') and value['passed']:summaries.append(file)
reg=max(summaries,key=lambda f:f.stat().st_mtime)
for name,h in json.loads(reg.read_text())['rtl_sha256'].items():assert sha(root/name)==h
shutil.copy2(reg,root/'reports/rtl_regression_summary.json')
coord=max((root/'sim/results').glob('coord_cases_*/summary.json'),key=lambda f:f.stat().st_mtime)
assert json.loads(coord.read_text())['passed']
shutil.copy2(coord,root/'reports/coordinate_cases_summary.json')
for oldname,newname in [('validation.json','PDS_validation.json'),('input_manifest.json','PDS_input_manifest.json'),
 ('report_timing/top_pangu50.rtr','PDS_timing.rtr'),('device_map/top_pangu50.dmr','PDS_device_map.dmr')]:
    shutil.copy2(build/oldname,root/'reports'/newname)
shutil.copy2(root/'sim/out/top_structure.json',root/'reports/top_structure.json')
print(json.dumps(report,indent=2))
