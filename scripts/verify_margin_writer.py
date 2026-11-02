from pathlib import Path
import argparse,datetime,os,subprocess,hashlib,json
ROOT=Path(__file__).resolve().parents[1];ap=argparse.ArgumentParser();ap.add_argument('--full',action='store_true');a=ap.parse_args()
out=ROOT/'reports'/('margin_writer_'+('full_' if a.full else 'small_')+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'));out.mkdir()
env=os.environ.copy();env.update(PATHEXT='.COM;.EXE;.BAT;.CMD',COMSPEC=r'C:\Windows\System32\cmd.exe')
files=[ROOT/'rtl/common/async_fifo.v',ROOT/'rtl/mem/frame_writer.v',ROOT/'sim/tb/tb_margin_writer.v'];binary=out/'test.vvp'
cmd=['D:/iverilog/bin/iverilog.exe','-g2012','-s','tb_margin_writer','-o',str(binary)]
if not a.full:cmd+=['-Ptb_margin_writer.HEIGHT=4']
r=subprocess.run(cmd+[str(p) for p in files],cwd=ROOT,env=env,capture_output=True,text=True)
(out/'compile.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stderr
r=subprocess.run(['D:/iverilog/bin/vvp.exe',str(binary)],cwd=ROOT,env=env,capture_output=True,text=True,timeout=300)
(out/'test.log').write_text(r.stdout+r.stderr);ok=r.returncode==0 and 'MARGIN_WRITER PASS' in r.stdout
(out/'result.json').write_text(json.dumps(dict(passed=ok,width=1296,height=972 if a.full else 4,hardware_tested=False,source_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}),indent=2))
print(r.stdout+r.stderr);print(out);raise SystemExit(0 if ok else 1)
