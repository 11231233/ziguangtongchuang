from pathlib import Path
import datetime,json,hashlib,shutil
import cv2
from margin_geometry import load,identity
from reconstruct_margin_frame import reconstruct
from checkerboard_detection import detect_checkerboard
def stamp():return datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
def create(parent):
 folder=Path(parent)/('wide_C1_'+stamp());folder.mkdir()
 for name in ('train','validation','raw_groups','diagnostics','results'):(folder/name).mkdir()
 (folder/'dataset.json').write_text(json.dumps(dict(schema='margin_dataset_v1',geometry_sha256=identity(load())[0],
  source_size=load()['source_size'],same_firmware_boot_required=True,real_calibration_complete=False),indent=2),encoding='utf-8')
 return folder
def validate(folder):
 folder=Path(folder);d=json.loads((folder/'dataset.json').read_text(encoding='utf-8'))
 if d.get('schema')!='margin_dataset_v1' or d.get('geometry_sha256')!=identity(load())[0]:raise ValueError('This is not a matching full-window dataset; do not mix old 720P calibration')
 return folder
def save(folder,pages,split,pattern):
 folder=validate(folder)
 if split not in ('train','validation'):raise ValueError('Invalid split')
 image,meta=reconstruct(pages);fid=meta['source_frame_id']
 for part in ('train','validation'):
  for path in (folder/part).glob('*.json'):
   if json.loads(path.read_text(encoding='utf-8')).get('source_frame_id')==fid:raise ValueError('This frozen frame was already saved; release freeze, change board pose, then freeze again')
 try:detect_checkerboard(image,pattern)
 except ValueError:
  path=folder/'diagnostics'/('board_not_found_'+stamp()+'.png');cv2.imencode('.png',image)[1].tofile(path)
  raise ValueError('No complete board in reconstructed frame. Diagnostic image saved: '+str(path))
 group=folder/'raw_groups'/('frame_'+str(fid)+'_'+stamp());group.mkdir()
 copied=[]
 for i,path in enumerate(pages):
  target=group/f'capture_{i}.png';shutil.copy2(path,target);copied.append(target)
  sidecar=Path(path).with_suffix('.json')
  if sidecar.exists():
   evidence=json.loads(sidecar.read_text(encoding='utf-8'))
   if evidence.get('schema')=='margin_transport_restore_v1':
    original=group/f'transport_original_{i}.png';shutil.copy2(evidence['original'],original)
    evidence['original']=str(original.resolve())
    target.with_suffix('.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
 image,meta=reconstruct(copied)
 out=folder/split/('full_'+str(fid)+'_'+stamp()+'.png');data=cv2.imencode('.png',image)[1].tobytes();out.write_bytes(data)
 meta['image_sha256']=hashlib.sha256(data).hexdigest();meta['dataset_split']=split
 out.with_suffix('.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
 return out
