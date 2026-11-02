from pathlib import Path
import subprocess,os,json,hashlib
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'reports/angle_osd';out.mkdir(exist_ok=True)
env=os.environ.copy();env.update(PATHEXT='.COM;.EXE;.BAT;.CMD',COMSPEC=r'C:\Windows\System32\cmd.exe')
files=[ROOT/'rtl/video/metrics_osd.v',ROOT/'sim/tb/tb_angle_osd.v'];binary=out/'test.vvp'
r=subprocess.run(['D:/iverilog/bin/iverilog.exe','-g2012','-s','tb_angle_osd','-o',str(binary),*[str(p) for p in files]],cwd=ROOT,env=env,capture_output=True,text=True)
(out/'compile.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stderr
r=subprocess.run(['D:/iverilog/bin/vvp.exe',str(binary)],cwd=ROOT,env=env,capture_output=True,text=True,timeout=30)
(out/'test.log').write_text(r.stdout+r.stderr);ok=r.returncode==0 and 'ANGLE_OSD PASS' in r.stdout
(out/'result.json').write_text(json.dumps(dict(passed=ok,hardware_tested=False,source_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}),indent=2))
print(r.stdout+r.stderr);raise SystemExit(0 if ok else 1)
