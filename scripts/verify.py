from pathlib import Path
import subprocess,os,sys,time
p=Path(__file__).resolve().parents[1];os.chdir(p)
env=os.environ.copy();env['PATHEXT']='.COM;.EXE;.BAT;.CMD';env['COMSPEC']=r'C:\Windows\System32\cmd.exe'
def test(name,top,files,timeout=180,plusargs=None):
 out=p/'sim/out';out.mkdir(exist_ok=True)
 plusargs=plusargs or []
 r=subprocess.run(['D:/iverilog/bin/iverilog.exe','-g2012','-I',str(out),'-I',str(p/'sim/tb'),'-s',top,'-o',str(out/(name+'.vvp'))]+files,env=env,capture_output=True,text=True,stdin=subprocess.DEVNULL)
 (out/(name+'_compile.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
 if r.returncode:
  (out/(name+'.log')).write_text(f'COMPILE_FAILED EXIT_CODE={r.returncode}\n',encoding='utf-8')
  print(r.stdout+r.stderr,flush=True);return False
 started=time.monotonic()
 try:
  r=subprocess.run(['D:/iverilog/bin/vvp.exe',str(out/(name+'.vvp'))]+plusargs,env=env,capture_output=True,text=True,timeout=timeout)
 except subprocess.TimeoutExpired as e:
  body=(e.stdout or b'')+(e.stderr or b'')
  if isinstance(body,bytes):body=body.decode(errors='replace')
  (out/(name+'.log')).write_text(body+f'\nTIMEOUT after {timeout} seconds\n',encoding='utf-8')
  print(name,'TIMEOUT',flush=True);return False
 (out/(name+'.log')).write_text(r.stdout+r.stderr+f'\nSIM_EXIT_CODE={r.returncode} ELAPSED_SECONDS={time.monotonic()-started:.3f}\n',encoding='utf-8')
 print(r.stdout[-2200:],flush=True)
 return r.returncode==0 and 'PASS' in r.stdout and not any(t in r.stdout for t in ['FAIL','TIMEOUT','MISMATCH'])
if __name__=='__main__':
 subprocess.run([sys.executable,'tools/gen_coord_vectors.py'],check=True,env=env)
 subprocess.run([sys.executable,'tools/gen_bilin_vectors.py'],check=True,env=env)
 tests=[('tile','tb_warp_tile',['rtl/warp/coord_map.v','rtl/warp/bilinear_2x2.v','rtl/warp/warp_tile.v','sim/tb/tb_warp_tile.v']),('coord','tb_coord',['rtl/warp/coord_map.v','sim/tb/tb_coord.v']),('bilin','tb_bilin',['rtl/warp/bilinear_2x2.v','sim/tb/tb_bilin.v'])]
 ok=[test(*t) for t in tests]
 if not all(ok):raise SystemExit(1)
