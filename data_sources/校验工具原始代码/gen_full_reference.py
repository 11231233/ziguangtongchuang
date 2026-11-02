from pathlib import Path
import sys,json, numpy as np
import argparse
ap=argparse.ArgumentParser();ap.add_argument("--roll",type=float,default=0);ap.add_argument("--shift",type=float,default=0);ap.add_argument("--raw",action="store_true");ap.add_argument('--720p',dest='full720',action='store_true');ap.add_argument('--selected-preset',action='store_true');ap.add_argument('--matched-raw',action='store_true');ap.add_argument('--axis-scale',type=float);ap.add_argument('--axis-x',type=int,default=0);ap.add_argument('--axis-y',type=int,default=0);arg=ap.parse_args()
if arg.axis_scale is not None and (not np.isfinite(arg.axis_scale) or not 0<arg.axis_scale<=4 or arg.raw or arg.selected_preset or arg.roll or arg.shift):ap.error('axis-scale is a positive standalone linear test case, up to 4')
if arg.matched_raw and not arg.selected_preset:ap.error('--matched-raw requires --selected-preset')
if arg.selected_preset and (not arg.full720 or arg.raw or arg.roll or arg.shift):ap.error('--selected-preset requires plain --720p without raw/rotation/shift')
sys.path.insert(0,str(Path(__file__).resolve().parent))
from warp_model import CamParams,OutGeom,WarpParams,s32
p=Path(__file__).resolve().parents[1]/'sim/out';p.mkdir(exist_ok=True)
sw,sh,ow,oh=(1280,720,1280,720) if arg.full720 else (192,96,128,70)
cam=CamParams(fx=520,fy=520,cx=640,cy=360,k1=-.28,k2=.08,p1=0,p2=0) if arg.full720 else CamParams(fx=60,fy=60,cx=96,cy=48,k1=-.25,k2=.06,p1=.0005,p2=-.0005)
cam.cx+=arg.shift
w=WarpParams(cam=cam,out=OutGeom(width=ow,height=oh,fx=520 if arg.full720 else 90,fy=520 if arg.full720 else 90,cx=ow/2,cy=oh/2),roll_deg=arg.roll)
c={k:s32(v) for k,v in w.coeffs().items()}
if arg.selected_preset:
 c=json.loads((Path(__file__).resolve().parents[1]/'targets/selected_empirical_profile.json').read_text(encoding='utf-8'))['signed_q16_coefficients']
if arg.matched_raw:c['k1']=0;c['k2']=0
if arg.raw:c=dict(A=128,B=0,C=0,D=0,E=128,F=0,k1=0,k2=0,p1=0,p2=0,fx=33554432,fy=33554432,cx=0,cy=0)
if arg.axis_scale is not None:c=dict(A=round(arg.axis_scale*128),B=0,C=0,D=0,E=round(arg.axis_scale*128),F=0,k1=0,k2=0,p1=0,p2=0,fx=33554432,fy=33554432,cx=arg.axis_x*65536,cy=arg.axis_y*65536)
with (p/'frame_coef.vh').open('w') as f:
 for k,v in c.items(): f.write("localparam signed [31:0] %s = %s32'sd%d;\n"%(k.upper(),'-' if v<0 else '',abs(v)))
src=np.zeros((sh,sw),np.uint16)
for y in range(sh):
 for x in range(sw): src[y,x]=(((x*13+y*7)%32)<<11)|(((x+y*3)%64)<<5)|((x*3+y*5)%32)
(p/'full_src.hex').write_text('\n'.join(f'{x:04x}' for x in src.flat))
def mul(a,b):return (a*b+32768)>>16
def point(x,y):
 ux=c['A']*x+c['B']*y+c['C'];uy=c['D']*x+c['E']*y+c['F']
 xx=ux*ux;yy=uy*uy;r2=(xx+yy+32768)>>16;qxy=mul(ux,uy);qx=(xx+32768)>>16;qy=(yy+32768)>>16
 rad=65536+mul(c['k1'],r2)+mul(c['k2'],mul(r2,r2))
 xd=mul(ux,rad)+2*mul(c['p1'],qxy)+mul(c['p2'],r2+2*qx)
 yd=mul(uy,rad)+mul(c['p1'],r2+2*qy)+2*mul(c['p2'],qxy)
 return mul(c['fx'],xd)+c['cx'],mul(c['fy'],yd)+c['cy']
def sample(u,v):
 if not(0<=u<=(sw-1)*65536 and 0<=v<=(sh-1)*65536):return 0
 x=u>>16;y=v>>16;fu=(u>>8)&255;fv=(v>>8)&255
 ps=[int(src[y,x]),int(src[y,min(x+1,sw-1)]),int(src[min(y+1,sh-1),x]),int(src[min(y+1,sh-1),min(x+1,sw-1)])]
 wt=[(256-fu)*(256-fv),fu*(256-fv),(256-fu)*fv,fu*fv]
 vals=[sum(((p>>s)&m)*t for p,t in zip(ps,wt))>>16 for s,m in [(11,31),(5,63),(0,31)]]
 return (vals[0]<<11)|(vals[1]<<5)|vals[2]
(p/'full_expect.hex').write_text('\n'.join(f'{sample(*point(x,y)):04x}' for y in range(oh) for x in range(ow)))
print(f'generated independent fixed-point golden: {ow*oh} RGB565 pixels;', 'exact raw identity' if arg.raw else 'four-term distortion')
