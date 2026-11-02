"""Private A/B simulation. Same mapping and memory model; no hardware access."""
from pathlib import Path
import subprocess,sys,os,json,re,datetime,shutil,hashlib
ROOT=Path(__file__).resolve().parents[1]
env=os.environ.copy();env.update(PYTHONIOENCODING='utf-8',PATHEXT='.COM;.EXE;.BAT;.CMD',COMSPEC=r'C:\Windows\System32\cmd.exe')
out=ROOT/'reports'/('lookahead_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
out.mkdir()
subprocess.run([sys.executable,'tools/gen_full_reference.py'],cwd=ROOT,env=env,check=True)
for name in ('frame_coef.vh','full_expect.hex','full_src.hex'):
 shutil.copy2(ROOT/'sim/out'/name,out/name)
text=(ROOT/'sim/tb/tb_full.v').read_text().replace('sim/out/',out.as_posix()+'/')
files=[p for p in (ROOT/'rtl/warp').glob('*.v') if p.name not in ('tile_fetch.v','line_ring.v')]
rows=[]
for lookahead in (0,1):
 tb=out/('tb_'+str(lookahead)+'.v')
 tb.write_text(text.replace('.TILE(16)) dut(',f'.TILE(16),.BBOX_LOOKAHEAD({lookahead})) dut('),encoding='utf-8')
 binary=out/('case_'+str(lookahead)+'.vvp')
 command=['D:/iverilog/bin/iverilog.exe','-g2012','-I',str(out),'-s','tb_full','-o',str(binary),*[str(p) for p in files],str(tb)]
 run=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True)
 (out/f'compile_{lookahead}.log').write_text(run.stdout+run.stderr)
 assert run.returncode==0,run.stderr
 run=subprocess.run(['D:/iverilog/bin/vvp.exe',str(binary)],cwd=ROOT,env=env,capture_output=True,text=True,timeout=180)
 body=run.stdout+run.stderr;(out/f'run_{lookahead}.log').write_text(body)
 assert run.returncode==0 and 'FULL_FRAME PASS:' in body and not any(t in body for t in ('FAIL','FATAL','TIMEOUT')),body
 cycles=int(re.search(r'FULL_FRAME PASS:[^\n]*cycles=\s*(\d+)',body)[1])
 rows.append(dict(lookahead=lookahead,cycles=cycles,pixels_exact=8960))
result=dict(passed=True,simulation_only=True,same_golden_pixels=True,cases=rows,
 cycles_saved=rows[0]['cycles']-rows[1]['cycles'],
 rtl_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'rtl').rglob('*.v')})
(out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='rtl_sha256'},indent=2),flush=True)
