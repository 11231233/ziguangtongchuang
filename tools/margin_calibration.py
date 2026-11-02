"""Geometry-bound full-window calibration and fixed-view +/-20 coverage gates.

Only verified reconstructed RAW frames are eligible. No legacy-model fallback.
"""
from pathlib import Path
import argparse,hashlib,json,math
import cv2,numpy as np
from margin_geometry import load,identity
from checkerboard_detection import detect_checkerboard

def load_verified_frame(path,geometry):
 path=Path(path);meta=json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
 if meta.get('source_kind')!='fpga_full_raw_reconstructed' or not meta.get('footer_verified'):
  raise ValueError('Requires verified full-window RAW reconstruction: '+str(path))
 if meta.get('geometry_sha256')!=identity(geometry)[0]:raise ValueError('Calibration/capture geometry mismatch: '+str(path))
 if meta.get('calibrated_model_applied') or meta.get('pc_geometry_transform_applied') or meta.get('synthetic_test_data'):
  raise ValueError('Corrected/transformed/synthetic frames cannot be deployed as real calibration')
 data=path.read_bytes();digest=hashlib.sha256(data).hexdigest()
 if meta.get('image_sha256')!=digest:raise ValueError('Raw image changed after reconstruction: '+str(path))
 image=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
 if image is None or list(image.shape[1::-1])!=geometry['source_size']:raise ValueError('Wrong full source size: '+str(path))
 group=meta.get('reconstructed_from',[])
 if len(group)!=4:raise ValueError('Missing original tagged four-page evidence: '+str(path))
 for item in group:
  raw=Path(item['path'])
  if not raw.is_file() or hashlib.sha256(raw.read_bytes()).hexdigest()!=item['sha256']:
   raise ValueError('Original RAW page changed or missing: '+str(raw))
 from reconstruct_margin_frame import reconstruct
 reconstructed,verified=reconstruct([item['path'] for item in group],geometry)
 if verified['source_frame_id']!=meta['source_frame_id'] or not np.array_equal(reconstructed,image):
  raise ValueError('Saved image does not match its frozen tagged RAW pages: '+str(path))
 return image,meta,digest

def coefficients(model,angle,raw=False):
 out=model['output_camera'];t=math.radians(angle);co=math.cos(t);si=math.sin(t);cx,cy=640.,360.
 fx,fy=out['fx'],out['fy'];ox,oy=out['cx'],out['cy']
 # Pixel-plane rotation BEFORE normalization; keeps angle/shape when fx != fy.
 values=dict(A=round(co/fx*2**24),B=round(-si/fx*2**24),
  C=round((cx-co*cx+si*cy-ox)/fx*65536),D=round(si/fy*2**24),E=round(co/fy*2**24),
  F=round((cy-si*cx-co*cy-oy)/fy*65536))
 values.update({k:round(model[k]*65536) for k in ('k1','k2','p1','p2','fx','fy','cx','cy')})
 if model.get('model_kind','poly2')=='rational5x6':
  # The radial factor comes from the ROM; the register path must stay zero so the
  # old k1/k2 polynomial cannot be added on top of the table.
  values['k1']=0;values['k2']=0
 if raw:
  for k in ('k1','k2','p1','p2'):values[k]=0
 for k,v in values.items():
  limit=2**17 if k in ('A','B','D','E','k1','k2','p1','p2') else 2**31
  if not -limit<=v<limit:raise ValueError('Coefficient exceeds RTL range: '+k)
 return values

def coverage(model,geometry,angles=range(-20,21),step=1):
 sw,sh=geometry['source_size'];rows=[]
 y,x=np.mgrid[0:720:step,0:1280:step];x=x.astype(np.int64);y=y.astype(np.int64)
 out=model['output_camera'];fx,fy=out['fx'],out['fy'];ox,oy=out['cx'],out['cy']
 def mul(a,b):return (a*b+32768)>>16
 for angle in angles:
  c=coefficients(model,angle);t=math.radians(angle);co=math.cos(t);si=math.sin(t)
  ux=(co*(x-640)-si*(y-360)+640-ox)/fx;uy=(si*(x-640)+co*(y-360)+360-oy)/fy
  r2=ux*ux+uy*uy;s=1+model['k1']*r2+model['k2']*r2*r2
  u=model['fx']*(ux*s+2*model['p1']*ux*uy+model['p2']*(r2+2*ux*ux))+model['cx']
  v=model['fy']*(uy*s+model['p1']*(r2+2*uy*uy)+2*model['p2']*ux*uy)+model['cy']
  qx=((c['A']*x+c['B']*y+128)>>8)+c['C'];qy=((c['D']*x+c['E']*y+128)>>8)+c['F']
  qr=(qx*qx+qy*qy+32768)>>16;xx=mul(qx,qx);yy=mul(qy,qy);xy=mul(qx,qy)
  radial=65536+mul(c['k1'],qr)+mul(c['k2'],mul(qr,qr))
  qu=mul(c['fx'],mul(qx,radial)+2*mul(c['p1'],xy)+mul(c['p2'],qr+2*xx))+c['cx']
  qv=mul(c['fy'],mul(qy,radial)+mul(c['p1'],qr+2*yy)+2*mul(c['p2'],xy))+c['cy']
  good=(u>=1)&(u<=sw-2)&(v>=1)&(v<=sh-2)&(qu>=65536)&(qu<=(sw-2)*65536)&(qv>=65536)&(qv<=(sh-2)*65536)
  good &= (np.abs(qx)<=262144)&(np.abs(qy)<=262144)
  quant=float(np.hypot(qu/65536-u,qv/65536-v).max())
  dsdx=2*ux*(model['k1']+2*model['k2']*r2);dsdy=2*uy*(model['k1']+2*model['k2']*r2)
  j00=s+ux*dsdx+2*model['p1']*uy+6*model['p2']*ux
  j01=ux*dsdy+2*model['p1']*ux+2*model['p2']*uy
  j10=uy*dsdx+2*model['p1']*ux+2*model['p2']*uy
  j11=s+uy*dsdy+6*model['p1']*uy+2*model['p2']*ux
  min_det=float((j00*j11-j01*j10).min());misses=0
  if step==1:
   ui=qu>>16;vi=qv>>16
   # Same corner bbox, alignment, 2-pixel guard and 64x64 cap as warp_frame.
   uc=np.stack([ui[0::16,0::16],ui[0::16,15::16],ui[15::16,0::16],ui[15::16,15::16]])
   vc=np.stack([vi[0::16,0::16],vi[0::16,15::16],vi[15::16,0::16],vi[15::16,15::16]])
   wu=np.minimum(np.maximum(((uc.min(axis=0)-2)//16)*16,0),sw-64)
   wv=np.minimum(np.maximum(vc.min(axis=0)-2,0),sh-64)
   bw=np.clip(((uc.max(axis=0)-wu+4+15)//16)*16,16,64);bh=np.clip(vc.max(axis=0)-wv+4,1,64)
   wu=np.repeat(np.repeat(wu,16,axis=0),16,axis=1);wv=np.repeat(np.repeat(wv,16,axis=0),16,axis=1)
   bw=np.repeat(np.repeat(bw,16,axis=0),16,axis=1);bh=np.repeat(np.repeat(bh,16,axis=0),16,axis=1)
   lu=ui-wu;lv=vi-wv;nu=lu+(ui!=sw-1);nv=lv+(vi!=sh-1)
   in_window=(lu>=0)&(lv>=0)&(nu<bw)&(nv<bh)&((lu<63)|(ui==sw-1))&((lv<63)|(vi==sh-1))
   misses=int((good&~in_window).sum())
  rows.append(dict(angle=int(angle),pixels=int(x.size),invalid_pixels=int((~good).sum()),window_misses=misses,
    max_fixed_error_px=quant,min_jacobian_det=min_det,passed=bool(good.all() and quant<=.25 and min_det>0 and misses==0)))
 return dict(passed=all(r['passed'] for r in rows),full_pixel_audit=step==1,angle_range=[min(angles),max(angles)],
  output_camera_fixed=True,auto_zoom=False,rows=rows)

def effective_region(path=None):
 """Measured optical effective area (targets/effective_area.json). None = full frame.

 The sensor's outermost band on this C1 assembly carries no usable signal, so corners
 cannot be observed there and a board pushed into it is clipped, which the dataset
 format rejects. Coverage is therefore evaluated inside the measured region. Precision
 thresholds are unchanged; only the domain is corrected.
 """
 p=Path(path) if path else Path(__file__).resolve().parents[1]/'targets/effective_area.json'
 if not p.is_file():return None
 d=json.loads(p.read_text(encoding='utf-8'))
 rect=[int(v) for v in d.get('effective_rect',[])]
 if len(rect)!=4 or rect[2]<=rect[0] or rect[3]<=rect[1]:
  raise ValueError('Invalid effective area rectangle: '+str(p))
 return rect

def spatial_coverage(points,size,region=None):
 w,h=size
 x0,y0,x1,y1=region if region else (0,0,w-1,h-1)
 rw,rh=x1-x0+1,y1-y0+1
 all_points=np.vstack(points).reshape(-1,2);edges={};corners={}
 pts2=[np.asarray(p).reshape(-1,2) for p in points]
 for name,get in [('left',lambda p:p[:,0]<x0+.15*rw),('right',lambda p:p[:,0]>x1-.15*rw),
                  ('top',lambda p:p[:,1]<y0+.15*rh),('bottom',lambda p:p[:,1]>y1-.15*rh)]:
  counts=[int(get(p).sum()) for p in pts2]
  edges[name]=dict(points=sum(counts),views=sum(n>0 for n in counts))
 for name,left,top in [('tl',True,True),('tr',False,True),('bl',True,False),('br',False,False)]:
  mask=((all_points[:,0]<x0+.25*rw) if left else (all_points[:,0]>x1-.25*rw)) & \
       ((all_points[:,1]<y0+.25*rh) if top else (all_points[:,1]>y1-.25*rh))
  corners[name]=int(mask.sum())
 return dict(passed=all(v['views']>=2 and v['points']>=8 for v in edges.values()) and all(v>0 for v in corners.values()),region=[x0,y0,x1,y1],edges=edges,corners=corners)

def calibrate(folder,out,pattern,square_mm,confirmed):
 g=load();folder=Path(folder);out=Path(out)
 if out.exists():raise ValueError('Choose a new result directory; existing data is preserved')
 if not confirmed:raise ValueError('Confirm the full-window capture and fixed lens/imaging mode before calibration')
 if not math.isfinite(square_mm) or square_mm<=0 or min(pattern)<3:raise ValueError('Invalid physical board dimensions')
 groups={};hashes=set();raw_hashes=set();frame_ids=set()
 for split,minimum in [('train',20),('validation',6)]:
  items=[]
  for path in sorted((folder/split).glob('*.png')):
   image,meta,digest=load_verified_frame(path,g)
   group_hashes={v['sha256'] for v in meta['reconstructed_from']}
   if digest in hashes or raw_hashes&group_hashes or meta['source_frame_id'] in frame_ids:raise ValueError('Training/validation duplicates the same frozen capture: '+str(path))
   hashes.add(digest);raw_hashes.update(group_hashes);frame_ids.add(meta['source_frame_id'])
   pts=detect_checkerboard(image,pattern)['points'].astype(np.float32).reshape(-1,1,2)
   items.append(dict(path=str(path),sha256=digest,meta=meta,points=pts))
  if len(items)<minimum:raise ValueError(f'{split} needs at least {minimum} verified complete-board frames; found {len(items)}')
  groups[split]=items
 obj=np.zeros((pattern[0]*pattern[1],3),np.float32);obj[:,:2]=np.mgrid[0:pattern[0],0:pattern[1]].T.reshape(-1,2)*square_mm
 train=groups['train'];validation=groups['validation']
 rms,K,d,_,_=cv2.calibrateCamera([obj]*len(train),[v['points'] for v in train],tuple(g['source_size']),None,None,flags=cv2.CALIB_FIX_K3)
 d=d.ravel();model=dict(fx=float(K[0,0]),fy=float(K[1,1]),cx=float(K[0,2]),cy=float(K[1,2]),
  k1=float(d[0]),k2=float(d[1]),p1=float(d[2]),p2=float(d[3]),k3=0.,camera='C1',image_size=g['source_size'],
  geometry_sha256=identity(g)[0],source_kind='verified_margin_raw_calibration',synthetic_test_data=False,
  source_kind_operator_confirmed=True,full_window_operator_confirmed=True,pattern=list(pattern),square_mm=square_mm,
  training_frames=len(train),validation_frames=len(validation),train_rms_px=float(rms))
 rx,ry,_,_=g['reference_roi'];model['output_camera']=dict(fx=model['fx'],fy=model['fy'],cx=model['cx']-rx,cy=model['cy']-ry,width=1280,height=720,
  selection='fixed central virtual view at source pixel scale; never adjusted with rotation')
 errors=[];edge_errors={name:[] for name in ('left','right','top','bottom')};sw,sh=g['source_size']
 region=effective_region()
 rx0,ry0,rx1,ry1=region if region else (0,0,sw-1,sh-1)
 rw,rh=rx1-rx0+1,ry1-ry0+1
 for item in validation:
  ok,rvec,tvec=cv2.solvePnP(obj,item['points'],K,d)
  if not ok:raise ValueError('Held-out pose fitting failed: '+item['path'])
  projected=cv2.projectPoints(obj,rvec,tvec,K,d)[0]
  e=np.linalg.norm(projected-item['points'],axis=2).ravel()
  observed=item['points'].reshape(-1,2)
  for name,mask in [('left',observed[:,0]<rx0+.15*rw),('right',observed[:,0]>rx1-.15*rw),
                    ('top',observed[:,1]<ry0+.15*rh),('bottom',observed[:,1]>ry1-.15*rh)]:
   edge_errors[name].extend(float(v) for v in e[mask])
  errors.append(dict(file=item['path'],rms_px=float(np.sqrt(np.mean(e*e))),p95_px=float(np.percentile(e,95)),max_px=float(e.max())))
 heldout_rms=float(np.sqrt(np.mean([r['rms_px']**2 for r in errors])))
 spatial=spatial_coverage([v['points'] for v in train],g['source_size'],region)
 report=dict(geometry_sha256=identity(g)[0],operator_full_window_confirmed=confirmed,training_frames=len(train),validation_frames=len(validation),train_rms_px=float(rms),
  heldout_rms_px=heldout_rms,per_view=errors,spatial_coverage=spatial,
  effective_area=dict(region=region,source='targets/effective_area.json',
   note='coverage domain only; precision thresholds unchanged'),
  error_thresholds=dict(train_rms_px=1.,heldout_rms_px=1.,max_view_rms_px=1.5),hardware_tested=False,
  source_images=[dict(file=v['path'],sha256=v['sha256']) for v in train+validation])
 report['heldout_edge_errors']={name:dict(points=len(v),rms_px=float(np.sqrt(np.mean(np.square(v)))) if v else None,
  p95_px=float(np.percentile(v,95)) if v else None) for name,v in edge_errors.items()}
 reasons=[]
 if rms>1 or heldout_rms>1 or max(v['rms_px'] for v in errors)>1.5:reasons.append('Independent image residual threshold failed; inspect data/model, do not force coefficients')
 if not spatial['passed']:reasons.append('Full-window edges/corners lack independent training observations')
 if any(v['points']<8 or v['rms_px'] is None or v['rms_px']>1 or v['p95_px']>2 for v in report['heldout_edge_errors'].values()):
  reasons.append('Independent validation edges lack observations or exceed outer-ring residual limits')
 try:report['mapping_coverage']=coverage(model,g)
 except (ValueError,OverflowError) as exc:report['mapping_coverage']=dict(passed=False,error=str(exc))
 if not report['mapping_coverage']['passed']:reasons.append('Fixed-view +/-20 degrees lacks real source coverage, hardware precision or safe fetch windows')
 report['ready_for_runtime']=not reasons;report['reasons']=reasons
 out.mkdir(parents=True);data=json.dumps(model,indent=2).encode('utf-8');(out/'calibration.json').write_bytes(data)
 report['model_sha256']=hashlib.sha256(data).hexdigest();(out/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 return report

def require_runtime_model(model_path,report_path):
 path=Path(model_path);model=json.loads(path.read_text(encoding='utf-8'));r=json.loads(Path(report_path).read_text(encoding='utf-8'));g=load()
 if model.get('synthetic_test_data') or model.get('source_kind')!='verified_margin_raw_calibration':raise ValueError('Only new verified real full-window calibration may be deployed')
 if model.get('geometry_sha256')!=identity(g)[0] or r.get('geometry_sha256')!=identity(g)[0]:raise ValueError('Geometry changed: reacquire/recalibrate, do not reuse old parameters')
 if r.get('model_sha256')!=hashlib.sha256(path.read_bytes()).hexdigest():raise ValueError('Model differs from the independently validated artifact')
 if not r.get('ready_for_runtime') or not r.get('mapping_coverage',{}).get('full_pixel_audit'):raise ValueError('Calibration/coverage not ready: '+str(r.get('reasons')))
 if abs(model.get('k3',0))>1e-12 and model.get('model_kind','poly2')!='rational5x6':raise ValueError('This RTL has no k3 term; unsupported model cannot be silently truncated')
 if model.get('model_kind','poly2')=='rational5x6' and not any(abs(model.get(k,0))>1e-12 for k in ('k4','k5','k6')):raise ValueError('Rational model without denominator terms; refusing to deploy')
 return model,r

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--dataset',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
 ap.add_argument('--cols',type=int,default=6);ap.add_argument('--rows',type=int,default=9);ap.add_argument('--square-mm',type=float,required=True)
 ap.add_argument('--full-window-confirmed',action='store_true');a=ap.parse_args()
 r=calibrate(a.dataset,a.out,(a.cols,a.rows),a.square_mm,a.full_window_confirmed)
 print(json.dumps({k:v for k,v in r.items() if k not in ('source_images','mapping_coverage','per_view')},indent=2))
 print('Result',a.out)
if __name__=='__main__':main()
