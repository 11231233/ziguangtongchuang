"""Private 720P selected-original-preset regression with shared DDR traffic."""
from pathlib import Path
import subprocess,sys,os,json,re,datetime,shutil,hashlib
ROOT=Path(__file__).resolve().parents[1]
env=os.environ.copy();env.update(PYTHONIOENCODING='utf-8',PATHEXT='.COM;.EXE;.BAT;.CMD',COMSPEC=r'C:\Windows\System32\cmd.exe')
out=ROOT/'reports'/('standalone_full_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'));out.mkdir()
gen=out/'generator';(gen/'tools').mkdir(parents=True);(gen/'targets').mkdir();(gen/'sim').mkdir()
for name in ('gen_full_reference.py','warp_model.py'):shutil.copy2(ROOT/'tools'/name,gen/'tools'/name)
shutil.copy2(ROOT/'targets/selected_empirical_profile.json',gen/'targets/selected_empirical_profile.json')
subprocess.run([sys.executable,str(gen/'tools/gen_full_reference.py'),'--720p','--selected-preset'],cwd=gen,env=env,check=True)
for name in ('frame_coef.vh','full_expect.hex'):shutil.copy2(gen/'sim/out'/name,out/name)
tb=out/'tb_full_private.v';tb.write_text((ROOT/'sim/tb/tb_full.v').read_text().replace('sim/out/',out.as_posix()+'/'),encoding='utf-8')
binary=out/'full.vvp'
files=[p for p in (ROOT/'rtl/warp').glob('*.v') if p.name not in ('tile_fetch.v','line_ring.v')]+[ROOT/'rtl/mem/mem_hub.v',ROOT/'sim/model/video_background.v',tb]
hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'rtl').rglob('*.v')}
r=subprocess.run(['D:/iverilog/bin/iverilog.exe','-g2012','-DFULL720P','-DSHARED_DDR','-I',str(out),'-s','tb_full','-o',str(binary),*[str(p) for p in files]],env=env,cwd=ROOT,capture_output=True,text=True)
(out/'compile.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stderr
r=subprocess.run(['D:/iverilog/bin/vvp.exe',str(binary)],env=env,cwd=ROOT,capture_output=True,text=True,timeout=1200)
body=r.stdout+r.stderr;(out/'full.log').write_text(body)
ok=r.returncode==0 and 'FULL_FRAME PASS:' in body and not any(t in body for t in ('FAIL','FATAL','TIMEOUT'))
cycles=int(re.search(r'FULL_FRAME PASS:[^\n]*cycles=\s*(\d+)',body)[1]) if ok else None
result=dict(passed=ok,hardware_tested=False,simulation_only=True,selected_original_preset=True,
 exact_compared_pixels=921600 if ok else 0,frame_cycles=cycles,shared_capture_display_ddr_modeled=True,
 rtl_sha256=hashes,rtl_changed=[n for n,h in hashes.items() if hashlib.sha256((ROOT/n).read_bytes()).hexdigest()!=h])
if result['rtl_changed']:result['passed']=False
(out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(body[-1800:],flush=True);print('REPORT',out,flush=True)
raise SystemExit(0 if result['passed'] else 1)
