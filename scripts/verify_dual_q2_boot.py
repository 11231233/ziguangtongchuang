from pathlib import Path
import hashlib,json,subprocess
from verify import env
p=Path(__file__).resolve().parents[1];out=p/'sim/out';out.mkdir(exist_ok=True)
files=[p/'rtl/top/top_pangu50.v']
for d in ['common','video','cam','hdmi','mem']:files.extend(sorted((p/'rtl'/d).glob('*.v')))
files=[f for f in files if f.name!='cmos_8_16bit.v']+[p/'rtl/ddr/sync_vg.v']
files.extend(sorted(f for f in (p/'rtl/warp').glob('*.v') if f.name not in ['line_ring.v','tile_fetch.v']))
files.append(p/'sim/tb/tb_dual_q2_boot.v')
r=subprocess.run(['D:/iverilog/bin/iverilog.exe','-g2012','-i','-s','tb_dual_q2_boot','-o',str(out/'dual_q2_boot.vvp')]+[str(f) for f in files],capture_output=True,text=True,env=env,cwd=p)
(out/'dual_q2_boot_compile.log').write_text(r.stdout+r.stderr,encoding='utf-8')
if r.returncode:raise SystemExit(r.stdout+r.stderr)
r=subprocess.run(['D:/iverilog/bin/vvp.exe',str(out/'dual_q2_boot.vvp')],capture_output=True,text=True,timeout=30,env=env,cwd=p)
(out/'dual_q2_boot.log').write_text(r.stdout+r.stderr,encoding='utf-8')
ok=r.returncode==0 and 'DUAL_Q2_BOOT PASS' in r.stdout
(p/'reports/dual_q2_boot_test.json').write_text(json.dumps({'passed':ok,'vendor_IP_black_boxes':True,
 'scope':'actual top control reset and key integration only; not physical cameras or DDR',
 'source_sha256':{f.relative_to(p).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in files}},indent=2),encoding='utf-8')
print(r.stdout+r.stderr);raise SystemExit(0 if ok else 1)
