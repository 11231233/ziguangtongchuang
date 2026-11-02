"""Real RTL full-frame resampling test with SYNTHETIC wide-window coefficients."""
from pathlib import Path
import argparse,datetime,json,hashlib,os,subprocess,re,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'scripts'))
from test_margin_calibration import test_model
from margin_calibration import coefficients
ap=argparse.ArgumentParser();ap.add_argument('--angle',type=int,choices=range(-20,21),default=20);a=ap.parse_args()
out=ROOT/'reports'/('margin_corrected_'+str(a.angle)+'_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'));out.mkdir()
model=test_model();model.update(p1=.001,p2=-.002);c=coefficients(model,a.angle)
(out/'frame_coef.vh').write_text('\n'.join('localparam signed[31:0] '+k.upper()+'='+('-' if v<0 else '')+f"32'sd{abs(v)};" for k,v in c.items())+'\n')
y,x=np.mgrid[0:720,0:1280];x=x.astype(np.int64);y=y.astype(np.int64)
def mul(a,b):return (a*b+32768)>>16
qx=((c['A']*x+c['B']*y+128)>>8)+c['C'];qy=((c['D']*x+c['E']*y+128)>>8)+c['F']
qr=(qx*qx+qy*qy+32768)>>16;xx=mul(qx,qx);yy=mul(qy,qy);xy=mul(qx,qy)
radial=65536+mul(c['k1'],qr)+mul(c['k2'],mul(qr,qr))
u=mul(c['fx'],mul(qx,radial)+2*mul(c['p1'],xy)+mul(c['p2'],qr+2*xx))+c['cx']
v=mul(c['fy'],mul(qy,radial)+mul(c['p1'],qr+2*yy)+2*mul(c['p2'],xy))+c['cy']
assert ((u>=0)&(u<=1295*65536)&(v>=0)&(v<=971*65536)).all()
ui=u>>16;vi=v>>16;fu=(u>>8)&255;fv=(v>>8)&255
def pixel(x,y):return (((x*13+y*7)%32)<<11)|(((x+y*3)%64)<<5)|((x*3+y*5)%32)
samples=[pixel(ui,vi),pixel(np.minimum(ui+1,1295),vi),pixel(ui,np.minimum(vi+1,971)),pixel(np.minimum(ui+1,1295),np.minimum(vi+1,971))]
weights=[(256-fu)*(256-fv),fu*(256-fv),(256-fu)*fv,fu*fv]
channels=[sum(((p>>shift)&mask)*w for p,w in zip(samples,weights))>>16 for shift,mask in ((11,31),(5,63),(0,31))]
gold=(channels[0]<<11)|(channels[1]<<5)|channels[2]
(out/'full_expect.hex').write_text('\n'.join(f'{int(p):04x}' for p in gold.flat)+'\n')
s=(ROOT/'sim/tb/tb_full.v').read_text().replace('sim/out/',out.as_posix()+'/')
s=s.replace('SW=1280,SH=720,W=1280,H=720,BASE=2000000','SW=1296,SH=972,W=1280,H=720,BASE=2239488')
s=s.replace('warp_frame #(', 'warp_frame #(.AFFINE_FRAC_BITS(24),.SRC_W(SW),').replace('.SRC_STRIDE(SW/2)', '.SRC_STRIDE(768)')
s=s.replace('x=address%SW;y=address/SW;', 'x=address%1536;y=address/1536;')
s=s.replace('source_pixel=(((x*13+y*7)%32)', "source_pixel=(x>=1296)?16'h0bad:(((x*13+y*7)%32)")
s=s.replace('r_addr*2+r_beats*16>SW*SH','r_addr*2+r_beats*16>1536*SH')
tb=out/'tb.v';tb.write_text(s)
files=[p for p in (ROOT/'rtl/warp').glob('*.v') if p.name not in ['tile_fetch.v','line_ring.v']]+[ROOT/'rtl/mem/mem_hub.v',ROOT/'sim/model/video_background.v',tb]
hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'rtl').rglob('*.v')}
env=os.environ.copy();env.update(PATHEXT='.COM;.EXE;.BAT;.CMD',COMSPEC=r'C:\Windows\System32\cmd.exe')
binary=out/'test.vvp'
r=subprocess.run(['D:/iverilog/bin/iverilog.exe','-g2012','-DFULL720P','-DSHARED_DDR','-I',str(out),'-s','tb_full','-o',str(binary),*[str(p) for p in files]],cwd=ROOT,env=env,capture_output=True,text=True)
(out/'compile.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stderr
r=subprocess.run(['D:/iverilog/bin/vvp.exe',str(binary)],cwd=ROOT,env=env,capture_output=True,text=True,timeout=1200)
body=r.stdout+r.stderr;(out/'test.log').write_text(body)
ok=r.returncode==0 and 'FULL_FRAME PASS:' in body and not any(t in body for t in ['FAIL','FATAL','TIMEOUT'])
d=dict(passed=ok,angle=a.angle,pixels_compared=921600,synthetic_test_only=True,real_calibration_complete=False,hardware_tested=False,
 source_size=[1296,972],stride_pixels=1536,padding_poisoned=True,shared_ddr_modeled=True,rtl_sha256=hashes,coeff=c,
 cycles=int(re.search(r'FULL_FRAME PASS:[^\n]*cycles=\s*(\d+)',body)[1]) if ok else None)
if any(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()!=h for n,h in hashes.items()):d['passed']=False
(out/'result.json').write_text(json.dumps(d,indent=2));print(body[-1800:],flush=True);print(out);raise SystemExit(0 if d['passed'] else 1)
