"""Validate four tagged, frozen, unscaled views and reconstruct a full raw frame."""
from pathlib import Path
import argparse,binascii,hashlib,json,struct
import cv2,numpy as np
from margin_geometry import load,identity

def read_image(path):
 image=cv2.imdecode(np.frombuffer(Path(path).read_bytes(),np.uint8),cv2.IMREAD_COLOR)
 if image is None:raise ValueError('Cannot read capture PNG: '+str(path))
 return image

def transport_evidence(path,image):
 sidecar=Path(path).with_suffix('.json')
 if not sidecar.exists():return None
 meta=json.loads(sidecar.read_text(encoding='utf-8'))
 if meta.get('schema')!='margin_transport_restore_v1':return None
 original=Path(meta['original'])
 if meta.get('normalization')!='vertical' or not original.is_file():raise ValueError('Missing original transport evidence')
 if hashlib.sha256(original.read_bytes()).hexdigest()!=meta['original_sha256'] or hashlib.sha256(Path(path).read_bytes()).hexdigest()!=meta['canonical_sha256']:
  raise ValueError('Transport orientation evidence changed')
 if not np.array_equal(cv2.flip(read_image(original),0),image):raise ValueError('Transport restoration differs from its original frame')
 return meta

def decode(image,geometry=None,require_ready=True):
 g=geometry or load();sha,gid=identity(g)
 if image.shape[:2]!=(720,1280):raise ValueError('Capture must be an unscaled 1280x720 digital frame')
 gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
 samples=np.array([gray[706:718,4*i+1:4*i+3].mean() for i in range(256)])
 low,high=np.percentile(samples,[10,90]);threshold=(low+high)/2
 if high-low<100 or np.min(np.abs(samples-threshold))<25:raise ValueError('Footer has insufficient contrast or ambiguous bits')
 data=np.packbits(samples>threshold).tobytes()
 if data[:4]!=b'WRAW' or data[4]!=1 or data[30:]!=b'OK':raise ValueError('Not a tagged full-window RAW acquisition frame')
 if binascii.crc_hqx(data[:28],0xffff)!=int.from_bytes(data[28:30],'big'):raise ValueError('Footer CRC failed')
 if require_ready and data[5]!=0x7f:raise ValueError(f'RAW/frozen/config/overflow/Gamma/Q/bar conditions unverified: flags={data[5]:02x}; freeze until H1/RAW1')
 if data[7]!=0 or int.from_bytes(data[8:12],'big')!=gid:raise ValueError('Capture geometry identity does not match this project')
 sw,sh,x,y,w,h=struct.unpack('>6H',data[12:24]);page=data[6]
 if [sw,sh]!=g['source_size'] or [w,h]!=g['raw_view_size']:raise ValueError('Capture dimensions mismatch')
 if page not in range(4) or [x,y]!=g['raw_view_offsets'][page]:raise ValueError('ROI/page mismatch')
 return dict(page=page,x=x,y=y,width=w,height=h,source_frame_id=int.from_bytes(data[24:28],'big'),
             geometry_sha256=sha,geometry_id=gid,flags=data[5],footer_crc_verified=True)

def canonical_capture(image,geometry=None):
 """Restore whole HDMI transport orientation using CRC tags, never scene guesses.

 The source-coordinate ROI is unchanged: only an upside-down complete HDMI
 transport raster is restored. Unfrozen tags may identify orientation but cannot
 be saved as calibration data; decode() still requires all flags by default.
 """
 for flip in (False,True):
  candidate=cv2.flip(image,0) if flip else image
  try:tag=decode(candidate,geometry,require_ready=False)
  except ValueError:continue
  return candidate,tag,('vertical' if flip else 'identity')
 raise ValueError('未识别到有效的新窗口标签；请使用1280×720原始数字输入，保留完整底栏。请勿自行旋转、缩放或裁切。')

def reconstruct(paths,geometry=None):
 g=geometry or load();items=[]
 for path in paths:
  image=read_image(path);tag=decode(image,g)
  evidence=transport_evidence(path,image)
  if evidence is not None:tag['transport_restoration']=evidence
  items.append((tag,image,path))
 if len(items)!=4 or {v[0]['page'] for v in items}!=set(range(4)):raise ValueError('Need exactly four different pages 0,1,2,3')
 if len({v[0]['source_frame_id'] for v in items})!=1:raise ValueError('Pages came from different source frames; freeze and recapture all four')
 sw,sh=g['source_size'];result=np.zeros((sh,sw,3),np.uint8);covered=np.zeros((sh,sw),bool);overlaps=[]
 for tag,image,path in sorted(items,key=lambda item:item[0]['page']):
  x,y,w,h=[tag[k] for k in ('x','y','width','height')];roi=image[:h,:w];mask=covered[y:y+h,x:x+w]
  old=result[y:y+h,x:x+w]
  if mask.any():
   err=np.abs(old.astype(np.int16)-roi.astype(np.int16))[mask]
   stats=dict(page=tag['page'],mean_abs=float(err.mean()),p99=float(np.percentile(err,99)))
   overlaps.append(stats)
   if stats['mean_abs']>8 or stats['p99']>64:raise ValueError('Overlapping views do not align; check resizing, direction, freeze and capture quality: '+str(stats))
  old[:]=roi;mask[:]=True
 if not covered.all():raise ValueError('Full active source is not covered')
 meta=dict(schema='verified_margin_raw_v1',source_kind='fpga_full_raw_reconstructed',camera='C1',image_size=[sw,sh],
  geometry_sha256=identity(g)[0],geometry_id=identity(g)[1],source_frame_id=items[0][0]['source_frame_id'],
  footer_verified=True,pc_geometry_transform_applied=False,source_size_verified_by_tag=True,
  reconstructed_from=[dict(path=str(path),sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),tag=tag) for tag,_,path in items],
  overlap_checks=overlaps,capture_compression_independently_verified=False,
  calibrated_model_applied=False,physical_lens_calibration_complete=False)
 return result,meta

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--pages',nargs=4,type=Path,required=True);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
 if args.out.suffix.lower()!='.png':ap.error('--out must be PNG')
 if args.out.exists() or args.out.with_suffix('.json').exists():ap.error('Output exists; choose a new filename')
 image,meta=reconstruct(args.pages);ok,encoded=cv2.imencode('.png',image)
 if not ok:raise ValueError('PNG encode failed')
 args.out.parent.mkdir(parents=True,exist_ok=True);data=encoded.tobytes();args.out.write_bytes(data)
 meta['image_sha256']=hashlib.sha256(data).hexdigest();args.out.with_suffix('.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
 print('Full raw reconstructed:',args.out,image.shape)

if __name__=='__main__':main()
