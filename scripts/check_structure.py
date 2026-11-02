from pathlib import Path
import hashlib,json,os,subprocess
p=Path(__file__).resolve().parents[1]
files=[p/'rtl/top/top_pangu50.v']
for d in ['common','video','cam','hdmi','mem']:files.extend(sorted((p/'rtl'/d).glob('*.v')))
files=[f for f in files if f.name!='cmos_8_16bit.v']+[p/'rtl/ddr/sync_vg.v']
files.extend(sorted(f for f in (p/'rtl/warp').glob('*.v') if f.name not in ['line_ring.v','tile_fetch.v']))
env=os.environ.copy();env['PATHEXT']='.COM;.EXE;.BAT;.CMD'
out=p/'sim/out';out.mkdir(exist_ok=True);results=[]
for mode in [0,1]:
 name='top_structure_'+str(mode)
 r=subprocess.run(['D:/iverilog/bin/iverilog.exe','-g2012','-i','-Wall','-s','top_pangu50','-Ptop_pangu50.USE_TPG='+str(mode),'-o',str(out/(name+'.vvp'))]+[str(f) for f in files],capture_output=True,text=True,env=env)
 (out/(name+'.log')).write_text('Custom RTL structural elaboration. Vendor PLL/DDR/primitives are black boxes. This is not PDS timing or vendor IP validation.\n'+r.stdout+r.stderr+f'\nEXIT_CODE={r.returncode}\n',encoding='utf-8')
 results.append({'USE_TPG':mode,'passed':r.returncode==0});print(name,'PASS' if r.returncode==0 else 'FAIL',flush=True)
 if r.returncode:print(r.stdout+r.stderr)
report={'passed':all(t['passed'] for t in results),'vendor_ip_black_boxes':True,'tests':results,'rtl_sha256':{f.relative_to(p).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in files}}
(out/'top_structure.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
raise SystemExit(0 if report['passed'] else 1)
