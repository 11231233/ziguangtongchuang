"""Read-only calibration diagnosis; never relax gates, delete frames or deploy."""
from pathlib import Path
import argparse,datetime,json,hashlib,sys
import cv2,numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from margin_geometry import load
from margin_calibration import load_verified_frame,spatial_coverage
from checkerboard_detection import detect_checkerboard

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--dataset',type=Path,required=True);ap.add_argument('--result',type=Path,required=True);a=ap.parse_args()
 model=json.loads((a.result/'calibration.json').read_text(encoding='utf-8'))
 out=a.dataset/'diagnostics'/('calibration_audit_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'));out.mkdir()
 g=load();pattern=tuple(model['pattern']);square=model['square_mm'];groups={};records=[];images=[]
 for split in ('train','validation'):
  items=[]
  for path in sorted((a.dataset/split).glob('*.png'),key=lambda p:p.stat().st_mtime):
   image,meta,digest=load_verified_frame(path,g);found=detect_checkerboard(image,pattern);pts=found['points'].reshape(-1,1,2).astype(np.float32)
   item=dict(file=str(path),sha256=digest,points=pts,method=found['method'],source_frame_id=meta['source_frame_id']);items.append(item)
   xy=pts.reshape(-1,2);record={k:v for k,v in item.items() if k!='points'}
   record.update(split=split,index=len(items),bounds=[float(v) for v in (*xy.min(axis=0),*xy.max(axis=0))],
    edge_points={name:int(mask.sum()) for name,mask in [('left',xy[:,0]<194.4),('right',xy[:,0]>1101.6),('top',xy[:,1]<145.8),('bottom',xy[:,1]>826.2)]},
    max_overlap_mean_abs=max(v['mean_abs'] for v in meta['overlap_checks']))
   records.append(record);images.append((record,image,xy));print(split,len(items),path.name,flush=True)
  groups[split]=items
 obj=np.zeros((pattern[0]*pattern[1],3),np.float32);obj[:,:2]=np.mgrid[0:pattern[0],0:pattern[1]].T.reshape(-1,2)*square
 models=[]
 for name,flags in [('rtl_k1k2p1p2',cv2.CALIB_FIX_K3),('diagnostic_k3',0),('diagnostic_rational',cv2.CALIB_RATIONAL_MODEL)]:
  try:
   rms,K,d,rvs,tvs=cv2.calibrateCamera([obj]*len(groups['train']),[v['points'] for v in groups['train']],tuple(g['source_size']),None,None,flags=flags)
   rows=[]
   for split in ('train','validation'):
    for n,item in enumerate(groups[split]):
     if split=='train':rv,tv=rvs[n],tvs[n]
     else:
      ok,rv,tv=cv2.solvePnP(obj,item['points'],K,d)
      if not ok:raise ValueError('Pose fit failed')
     e=np.linalg.norm(cv2.projectPoints(obj,rv,tv,K,d)[0]-item['points'],axis=2).ravel()
     rows.append(dict(file=item['file'],split=split,index=n+1,rms_px=float(np.sqrt(np.mean(e*e))),p95_px=float(np.percentile(e,95))))
   models.append(dict(name=name,train_rms_px=float(rms),heldout_rms_px=float(np.sqrt(np.mean([v['rms_px']**2 for v in rows if v['split']=='validation']))),K=K.tolist(),d=d.ravel().tolist(),per_view=rows,deployable=False))
   if name=='rtl_k1k2p1p2':
    scores={v['file']:v['rms_px'] for v in rows}
    for record in records:record['rms_px']=scores[record['file']]
  except Exception as exc:models.append(dict(name=name,error=str(exc),deployable=False))
 # Fisheye comparison is diagnostic only; it is not supported by current RTL.
 try:
  obs=[v['points'].astype(np.float64).reshape(1,-1,2) for v in groups['train']];objs=[obj.astype(np.float64).reshape(1,-1,3)]*len(obs)
  K=np.array([[400.,0,648],[0,400.,486],[0,0,1.]])
  # OpenCV 5 exposes the unified calibration flags on cv2 rather than fisheye.
  flag_owner=cv2.fisheye if hasattr(cv2.fisheye,'CALIB_FIX_SKEW') else cv2
  rms,K,d,_,_=cv2.fisheye.calibrate(objs,obs,tuple(g['source_size']),K,np.zeros((4,1)),
   flags=flag_owner.CALIB_USE_INTRINSIC_GUESS|flag_owner.CALIB_RECOMPUTE_EXTRINSIC|flag_owner.CALIB_FIX_SKEW,
   criteria=(cv2.TERM_CRITERIA_COUNT+cv2.TERM_CRITERIA_EPS,150,1e-8))
  rows=[]
  for split in ('train','validation'):
   for n,item in enumerate(groups[split]):
    normalized=cv2.fisheye.undistortPoints(item['points'].astype(np.float64).reshape(1,-1,2),K,d).reshape(-1,1,2)
    ok,rv,tv=cv2.solvePnP(obj,normalized,np.eye(3),None)
    if not ok:raise ValueError('Fisheye held-out pose failed')
    proj=cv2.fisheye.projectPoints(obj.astype(np.float64).reshape(1,-1,3),rv,tv,K,d)[0].reshape(-1,2)
    e=np.linalg.norm(proj-item['points'].reshape(-1,2),axis=1)
    rows.append(dict(file=item['file'],split=split,index=n+1,rms_px=float(np.sqrt(np.mean(e*e)))))
  models.append(dict(name='diagnostic_fisheye',train_rms_px=float(rms),heldout_rms_px=float(np.sqrt(np.mean([v['rms_px']**2 for v in rows if v['split']=='validation']))),K=K.tolist(),d=d.ravel().tolist(),per_view=rows,deployable=False))
 except Exception as exc:models.append(dict(name='diagnostic_fisheye',error=str(exc),deployable=False))
 font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',16)
 for split in ('train','validation'):
  selected=[v for v in images if v[0]['split']==split];sheet=Image.new('RGB',(4*336,((len(selected)+3)//4)*282),'white');draw=ImageDraw.Draw(sheet)
  coverage=Image.new('RGB',(1296,972),'white');cd=ImageDraw.Draw(coverage)
  for n,(record,image,xy) in enumerate(selected):
   x0=(n%4)*336;y0=(n//4)*282;im=Image.fromarray(cv2.cvtColor(image,cv2.COLOR_BGR2RGB)).resize((324,243));sheet.paste(im,(x0,y0+35))
   draw.text((x0+3,y0+3),f'{split} {n+1:02d} F{record["source_frame_id"]} RMS {record["rms_px"]:.2f}',fill='black',font=font)
   for x,y in xy:cd.ellipse((x-3,y-3,x+3,y+3),fill=('#245cff' if split=='train' else '#e55b20'))
  for x in [194.4,1101.6]:cd.line((x,0,x,971),fill='red',width=3)
  for y in [145.8,826.2]:cd.line((0,y,1295,y),fill='red',width=3)
  sheet.save(out/f'{split}_contact_sheet.png');coverage.save(out/f'{split}_coverage.png')
 report=dict(dataset=str(a.dataset),original_result=str(a.result),source_images_verified=len(records),records=records,
  spatial_coverage={split:spatial_coverage([v['points'] for v in groups[split]],g['source_size']) for split in groups},
  model_comparisons=models,diagnostic_only=True,models_deployed=False,original_files_changed=False,
  note='Existing validation was used diagnostically for model comparison; a selected new model needs fresh held-out validation and full hardware compatibility checks.')
 (out/'diagnosis.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 np.savez_compressed(out/'verified_corners.npz',object_points=obj,train=np.stack([v['points'] for v in groups['train']]),validation=np.stack([v['points'] for v in groups['validation']]))
 print('REPORT',out,flush=True)
 print(json.dumps([{k:v for k,v in m.items() if k not in ('K','d','per_view')} for m in models],indent=2),flush=True)
if __name__=='__main__':main()
