from pathlib import Path
import json,sys,numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from warp_model import CamParams,OutGeom,WarpParams,s32
from validate_coefficients import validate
p=Path(__file__).resolve().parents[1]
x,y=np.meshgrid(np.arange(1280,dtype=np.int64),np.arange(720,dtype=np.int64))
def mul(a,b):return (a*b+32768)>>16
rows=[]
def check(label,c):
 coverage=validate(c)
 ux=c['A']*x+c['B']*y+c['C'];uy=c['D']*x+c['E']*y+c['F']
 r2=(ux*ux+uy*uy+32768)>>16;qx=mul(ux,ux);qy=mul(uy,uy);qxy=mul(ux,uy)
 rad=65536+mul(c['k1'],r2)+mul(c['k2'],mul(r2,r2))
 u=mul(c['fx'],mul(ux,rad)+2*mul(c['p1'],qxy)+mul(c['p2'],r2+2*qx))+c['cx']
 v=mul(c['fy'],mul(uy,rad)+mul(c['p1'],r2+2*qy)+2*mul(c['p2'],qxy))+c['cy']
 ui=u>>16;vi=v>>16
 mnu=np.minimum.reduce([ui[0::16,0::16],ui[15::16,0::16],ui[0::16,15::16],ui[15::16,15::16]])
 mnv=np.minimum.reduce([vi[0::16,0::16],vi[15::16,0::16],vi[0::16,15::16],vi[15::16,15::16]])
 wu=np.repeat(np.repeat(np.clip((mnu-2)&~15,0,1216),16,axis=0),16,axis=1)
 wv=np.repeat(np.repeat(np.clip(mnv-2,0,656),16,axis=0),16,axis=1)
 valid=(u>=0)&(u<=1279*65536)&(v>=0)&(v<=719*65536)
 inside=(ui>=wu)&(vi>=wv)&((ui-wu<63)|(ui==1279))&((vi-wv<63)|(vi==719))
 missing=int(np.count_nonzero(valid&~inside))
 row={'case':label,'output_pixels':int(u.size),'valid_pixels':int(valid.sum()),'valid_pixels_outside_fetched_window':missing,
      'adaptive_fetch_window_misses':coverage['window_misses']}
 assert missing==0,row
 rows.append(row);print('GEOMETRY PASS',row,flush=True)
for angle in [0,31.5,45,90,180]:
 wp=WarpParams(cam=CamParams(fx=520,fy=520,cx=640,cy=360,k1=-.28,k2=.08),out=OutGeom(width=1280,height=720,fx=520,fy=520,cx=640,cy=360),roll_deg=angle)
 check('roll_'+str(angle),{k:s32(v) for k,v in wp.coeffs().items()})
for strength,(k1,k2) in enumerate([(-7864,1311),(-18350,5243),(-21061,7082),(-32768,10486)]):
 for zoom,(a,c,f) in enumerate([(126,-80660,-45371),(101,-64528,-36297),(82,-52429,-29491)]):
  check(f'preset_{strength}_zoom_{zoom}',dict(A=a,B=0,C=c,D=0,E=a,F=f,k1=k1,k2=k2,p1=0,p2=0,fx=34078720,fy=34078720,cx=41943040,cy=23592960))
check('raw_exact',dict(A=128,B=0,C=0,D=0,E=128,F=0,k1=0,k2=0,p1=0,p2=0,fx=33554432,fy=33554432,cx=0,cy=0))
for angle in [-179.5,-90,-31.5,12.25,89.5,135,270,359.5]:
 wp=WarpParams(cam=CamParams(fx=520,fy=520,cx=640,cy=360,k1=-.28,k2=.08,p1=.001,p2=-.0005),
  out=OutGeom(fx=520,fy=520),roll_deg=angle)
 check('host_roll_'+str(angle),{k:s32(v) for k,v in wp.coeffs().items()})
for yaw,pitch in [(5,0),(0,-5),(10,-10)]:
 wp=WarpParams(cam=CamParams(fx=520,fy=520,cx=640,cy=360,k1=-.28,k2=.08,p1=.001,p2=-.0005),
  out=OutGeom(fx=520,fy=520),yaw_deg=yaw,pitch_deg=pitch)
 check(f'host_affine_tilt_{yaw}_{pitch}',{k:s32(v) for k,v in wp.coeffs().items()})
(p/'sim/results/production_geometry.json').write_text(json.dumps({'passed':True,'cases':rows},indent=2),encoding='utf-8')
