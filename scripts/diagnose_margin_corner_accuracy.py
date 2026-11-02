"""Read-only SB accuracy experiment on already verified images. No deployment."""
from pathlib import Path
import argparse,json,hashlib,sys,datetime
import cv2,numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from reconstruct_margin_frame import read_image
from checkerboard_detection import _checked_points,detect_checkerboard
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--audit',type=Path,required=True);a=ap.parse_args()
 report=json.loads((a.audit/'diagnosis.json').read_text(encoding='utf-8'))
 model=json.loads((Path(report['original_result'])/'calibration.json').read_text(encoding='utf-8'));pattern=tuple(model['pattern'])
 groups={'train':[],'validation':[]};rows=[]
 for item in report['records']:
  path=Path(item['file']);assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256']
  image=read_image(path);gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
  ok,pts=cv2.findChessboardCornersSB(gray,pattern,flags=cv2.CALIB_CB_NORMALIZE_IMAGE|cv2.CALIB_CB_ACCURACY)
  pts=_checked_points(pts,pattern,gray.shape) if ok else None
  method='sb_accuracy'
  if pts is None:
   ok,pts=cv2.findChessboardCornersSB(gray,pattern,flags=cv2.CALIB_CB_NORMALIZE_IMAGE|cv2.CALIB_CB_ACCURACY|cv2.CALIB_CB_EXHAUSTIVE)
   pts=_checked_points(pts,pattern,gray.shape) if ok else None;method='sb_accuracy_exhaustive'
  if pts is None:pts=detect_checkerboard(image,pattern)['points'];method='original_detector_fallback'
  groups[item['split']].append(pts.astype(np.float32).reshape(-1,1,2));rows.append(dict(file=str(path),sha256=item['sha256'],split=item['split'],method=method,points=pts.tolist()))
  print(item['split'],len(groups[item['split']]),path.name,flush=True)
 obj=np.zeros((pattern[0]*pattern[1],3),np.float32);obj[:,:2]=np.mgrid[0:pattern[0],0:pattern[1]].T.reshape(-1,2)*model['square_mm']
 comparisons=[]
 for name,flags in [('rtl_k1k2p1p2_accuracy',cv2.CALIB_FIX_K3),('rational_accuracy',cv2.CALIB_RATIONAL_MODEL)]:
  rms,K,d,_,_=cv2.calibrateCamera([obj]*len(groups['train']),groups['train'],tuple(model['image_size']),None,None,flags=flags,criteria=(3,200,1e-10))
  errors=[]
  for pts in groups['validation']:
   ok,rv,tv=cv2.solvePnP(obj,pts,K,d);assert ok
   e=np.linalg.norm(cv2.projectPoints(obj,rv,tv,K,d)[0]-pts,axis=2)
   errors.append(float(np.sqrt(np.mean(e*e))))
  comparisons.append(dict(name=name,train_rms_px=float(rms),validation_rms_px=float(np.sqrt(np.mean(np.square(errors)))),per_validation=errors,K=K.tolist(),d=d.ravel().tolist(),deployable=False))
 out=dict(created_at=datetime.datetime.now().astimezone().isoformat(),diagnostic_only=True,source_images_changed=False,detector='SB NORMALIZE + ACCURACY, exhaustive/original fallback; all images retained',comparisons=comparisons,records=rows)
 (a.audit/'corner_accuracy_experiment.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
 print(json.dumps([{k:v for k,v in m.items() if k not in ['K','d']} for m in comparisons],indent=2),flush=True)
if __name__=='__main__':main()
