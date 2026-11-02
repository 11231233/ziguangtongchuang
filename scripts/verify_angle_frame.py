"""Independent rotated raster golden, with real pipeline and modeled DDR."""
from pathlib import Path
import argparse,datetime,json,hashlib,os,subprocess,re
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--angle',type=int,default=15);ap.add_argument('--small',action='store_true');args=ap.parse_args()
assert -180<=args.angle<=179
out=ROOT/'reports'/('angle_frame_'+str(args.angle)+'_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'));out.mkdir()
W,H=(128,70) if args.small else (1280,720)
a=126;c0=-80660;f0=-45371;t=np.deg2rad(args.angle);co=np.cos(t);si=np.sin(t)
old=np.array([[a/65536,0,c0/65536],[0,a/65536,f0/65536],[0,0,1.]])
rotation=np.array([[co,-si,640-co*640+si*360],[si,co,360-si*640-co*360],[0,0,1.]])
matrix=old@rotation
values=[int(np.rint(matrix[r,col]*(2**(24 if col<2 else 16)))) for r in range(2) for col in range(3)]
coeff=dict(zip(['A','B','C','D','E','F'],values));coeff.update(k1=-21061,k2=7082,p1=0,p2=0,fx=34078720,fy=34078720,cx=41943040,cy=23592960)
(out/'frame_coef.vh').write_text('\n'.join('localparam signed [31:0] '+k.upper()+'='+('-' if v<0 else '')+f"32'sd{abs(v)};" for k,v in coeff.items())+'\n')
y,x=np.mgrid[0:H,0:W];x=x.astype(np.int64);y=y.astype(np.int64)
ux=((coeff['A']*x+coeff['B']*y+128)>>8)+coeff['C'];uy=((coeff['D']*x+coeff['E']*y+128)>>8)+coeff['F']
def mul(a,b):return (a*b+32768)>>16
r2=(ux*ux+uy*uy+32768)>>16
radial=65536+mul(coeff['k1'],r2)+mul(coeff['k2'],mul(r2,r2))
u=mul(coeff['fx'],mul(ux,radial))+coeff['cx'];v=mul(coeff['fy'],mul(uy,radial))+coeff['cy']
valid=(u>=0)&(u<=1279*65536)&(v>=0)&(v<=719*65536)
u0=np.clip(u>>16,0,1279);v0=np.clip(v>>16,0,719);fu=(u>>8)&255;fv=(v>>8)&255
def source(x,y):return (((x*13+y*7)%32)<<11)|(((x+y*3)%64)<<5)|((x*3+y*5)%32)
samples=[source(u0,v0),source(np.minimum(u0+1,1279),v0),source(u0,np.minimum(v0+1,719)),source(np.minimum(u0+1,1279),np.minimum(v0+1,719))]
weights=[(256-fu)*(256-fv),fu*(256-fv),(256-fu)*fv,fu*fv]
channels=[sum(((p>>shift)&mask)*w for p,w in zip(samples,weights))>>16 for shift,mask in ((11,31),(5,63),(0,31))]
expected=(channels[0]<<11)|(channels[1]<<5)|channels[2];expected[~valid]=0
(out/'full_expect.hex').write_text('\n'.join(f'{int(p):04x}' for p in expected.flat)+'\n')
text=(ROOT/'sim/tb/tb_full.v').read_text().replace('sim/out/',out.as_posix()+'/').replace('warp_frame #(', 'warp_frame #(.AFFINE_FRAC_BITS(24),')
if args.small:text=text.replace('W=1280,H=720,BASE=2000000',f'W={W},H={H},BASE=2000000')
tb=out/'tb.v';tb.write_text(text)
files=[p for p in (ROOT/'rtl/warp').glob('*.v') if p.name not in ('tile_fetch.v','line_ring.v')]+[ROOT/'rtl/mem/mem_hub.v',ROOT/'sim/model/video_background.v',tb]
hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'rtl').rglob('*.v')}
env=os.environ.copy();env.update(PYTHONIOENCODING='utf-8',PATHEXT='.COM;.EXE;.BAT;.CMD',COMSPEC=r'C:\Windows\System32\cmd.exe')
binary=out/'test.vvp'
r=subprocess.run(['D:/iverilog/bin/iverilog.exe','-g2012','-DFULL720P','-DSHARED_DDR','-I',str(out),'-s','tb_full','-o',str(binary),*[str(p) for p in files]],cwd=ROOT,env=env,capture_output=True,text=True)
(out/'compile.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stderr
r=subprocess.run(['D:/iverilog/bin/vvp.exe',str(binary)],cwd=ROOT,env=env,capture_output=True,text=True,timeout=1200)
body=r.stdout+r.stderr;(out/'test.log').write_text(body)
ok=r.returncode==0 and 'FULL_FRAME PASS:' in body and not any(s in body for s in ['FAIL','FATAL','TIMEOUT'])
result=dict(passed=ok,angle=args.angle,width=W,height=H,pixels_compared=W*H,valid_sample_pixels=int(valid.sum()),
 hardware_tested=False,shared_ddr_modeled=True,coeff=coeff,rtl_sha256=hashes,
 cycles=int(re.search(r'FULL_FRAME PASS:[^\n]*cycles=\s*(\d+)',body)[1]) if ok else None,
 source_changed=[n for n,h in hashes.items() if hashlib.sha256((ROOT/n).read_bytes()).hexdigest()!=h])
if result['source_changed']:result['passed']=False
(out/'result.json').write_text(json.dumps(result,indent=2));print(body[-1800:],flush=True);print('REPORT',out,flush=True)
raise SystemExit(0 if result['passed'] else 1)
