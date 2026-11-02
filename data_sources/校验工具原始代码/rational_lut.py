"""Rational radial LUT prototype. This module never certifies a calibration."""
from pathlib import Path
import hashlib,json,math
import numpy as np
CELLS=2048;STEP_Q16=1024;MAX_R2_Q16=2097152

def factor_float(model,t):
 t=np.asarray(t,np.float64)
 n=1+t*(model['k1']+t*(model['k2']+t*model['k3']))
 d=1+t*(model['k4']+t*(model['k5']+t*model['k6']))
 return n/d

def build_table(model):
 t=np.linspace(0,32,CELLS+1);value=factor_float(model,t)
 denominator=1+t*(model['k4']+t*(model['k5']+t*model['k6']))
 if not np.isfinite(value).all() or (value<=0).any() or (denominator<=0).any():
  raise ValueError('Nonpositive radial factor or denominator in LUT domain')
 q=np.rint(value*2**24).astype(np.int64);delta=np.diff(q)
 if (np.abs(q)>=2**31).any() or (np.abs(delta)>=2**31).any():raise ValueError('LUT Q24 overflow')
 return np.stack([q[:-1],delta],axis=1)

def factor_fixed(table,r2):
 r2=np.asarray(r2,np.int64);index=np.clip(r2>>10,0,CELLS-1)
 fraction=np.where(r2>=MAX_R2_Q16,1024,r2&1023)
 value=((table[index,0]<<10)+table[index,1]*fraction+131072)>>18
 return value,(r2>=0)&(r2<=MAX_R2_Q16)

def coefficients(model,angle):
 out=model['output_camera'];t=math.radians(angle);co=math.cos(t);si=math.sin(t)
 c=dict(A=round(co/out['fx']*2**24),B=round(-si/out['fx']*2**24),
 C=round((640-co*640+si*360-out['cx'])/out['fx']*65536),
 D=round(si/out['fy']*2**24),E=round(co/out['fy']*2**24),
 F=round((360-si*640-co*360-out['cy'])/out['fy']*65536))
 c.update({n:round(model[n]*65536) for n in ('k1','k2','p1','p2','fx','fy','cx','cy')})
 for n,v in c.items():
  bits=18 if n in ('A','B','D','E','k1','k2','p1','p2') else 32
  if not -(2**(bits-1))<=v<2**(bits-1):raise ValueError('Coefficient overflow: '+n)
 return c

def coordinates_fixed(model,table,angle,x,y,enabled=True):
 c=coefficients(model,angle);x=np.asarray(x,np.int64);y=np.asarray(y,np.int64)
 def mul(a,b):return (a*b+32768)>>16
 qx=((c['A']*x+c['B']*y+128)>>8)+c['C'];qy=((c['D']*x+c['E']*y+128)>>8)+c['F']
 qr=(qx*qx+qy*qy+32768)>>16;xx=mul(qx,qx);yy=mul(qy,qy);xy=mul(qx,qy)
 radial,domain=factor_fixed(table,qr)
 p1,p2=c['p1'],c['p2']
 if not enabled:radial=np.full_like(qr,65536);p1=p2=0;domain=np.ones_like(qr,dtype=bool)
 u=mul(c['fx'],mul(qx,radial)+2*mul(p1,xy)+mul(p2,qr+2*xx))+c['cx']
 v=mul(c['fy'],mul(qy,radial)+mul(p1,qr+2*yy)+2*mul(p2,xy))+c['cy']
 u=np.clip(u,-2**31,2**31-1);v=np.clip(v,-2**31,2**31-1)
 valid=domain&(np.abs(qx)<=262144)&(np.abs(qy)<=262144)&(u>=0)&(u<=1295*65536)&(v>=0)&(v<=971*65536)
 return u,v,valid

def coordinates_float(model,angle,x,y,enabled=True):
 o=model['output_camera'];a=math.radians(angle);co=math.cos(a);si=math.sin(a)
 nx=(co*(x-640)-si*(y-360)+640-o['cx'])/o['fx']
 ny=(si*(x-640)+co*(y-360)+360-o['cy'])/o['fy'];t=nx*nx+ny*ny
 f=factor_float(model,t) if enabled else 1.;p1=model['p1'] if enabled else 0.;p2=model['p2'] if enabled else 0.
 return (model['fx']*(nx*f+2*p1*nx*ny+p2*(t+2*nx*nx))+model['cx'],
         model['fy']*(ny*f+p1*(t+2*ny*ny)+2*p2*nx*ny)+model['cy'])

def write_rom(path,table):
 Path(path).write_text('\n'.join(f'{int(a)&0xffffffff:08x}{int(b)&0xffffffff:08x}' for a,b in table)+'\n',encoding='ascii')

def candidate_from_audit(audit,geometry_sha):
 path=Path(audit);d=json.loads(path.read_text(encoding='utf-8'))
 row=next(v for v in d['model_comparisons'] if v['name']=='diagnostic_rational')
 K=np.asarray(row['K']);v=row['d']
 if any(abs(n)>1e-12 for n in v[8:]):raise ValueError('Thin prism/tilt coefficients unsupported by radial LUT')
 m=dict(schema='rational_lut_prototype_v1',source_kind='diagnostic_rational_candidate',synthetic_test_data=False,
   fx=float(K[0,0]),fy=float(K[1,1]),cx=float(K[0,2]),cy=float(K[1,2]),
   **dict(zip(('k1','k2','p1','p2','k3','k4','k5','k6'),v[:8])),
   geometry_sha256=geometry_sha,image_size=[1296,972],train_rms_px=row['train_rms_px'],validation_rms_px=row['heldout_rms_px'],
   source_audit=str(path.resolve()),source_audit_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
   source_images=[{n:v[n] for n in ('file','sha256','split')} for v in d['records']],
   ready_for_runtime=False,deployment_allowed=False,reason='Precision, spatial/optical coverage and fresh independent validation remain incomplete')
 m['output_camera']=dict(fx=m['fx'],fy=m['fy'],cx=m['cx']-8,cy=m['cy']-126,width=1280,height=720)
 return m
