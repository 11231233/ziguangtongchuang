"""Synthetic CLI integration test; outputs are NOT real camera calibration."""
from pathlib import Path
import datetime,json,subprocess,sys,shutil
import cv2
import numpy as np
p=Path(__file__).resolve().parents[1]
out=p/'build'/('synthetic_calibration_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'));out.mkdir()
K=np.array([[800.,0,640],[0,810,360],[0,0,1]])
dist=np.array([-.15,.04,.001,-.0005,0.])
for i in range(12):
 image=np.full((720,1280,3),180,np.uint8)
 rv=np.array([-.25+.045*i,.12*np.sin(i),-.12+.02*i])
 tv=np.array([-.125+.02*np.sin(i),-.087+.015*np.cos(i),.45+.015*(i%4)])
 for y in range(7):
  for x in range(10):
   quad=np.array([[x,y,0],[x+1,y,0],[x+1,y+1,0],[x,y+1,0]],np.float64)*.025
   q,_=cv2.projectPoints(quad,rv,tv,K,dist)
   color=(0,0,0) if (x+y)%2==0 else (255,255,255)
   cv2.fillConvexPoly(image,np.rint(q.reshape(-1,2)).astype(np.int32),color,lineType=cv2.LINE_AA)
 cv2.imwrite(str(out/f'view_{i:02d}.png'),image)
result=out/'synthetic_result.json'
r=subprocess.run([sys.executable,str(p/'tools/calib_ov5640.py'),'--images',str(out/'view_*.png'),'--source-kind','synthetic','--out',str(result)],capture_output=True,text=True)
(out/'test.log').write_text(r.stdout+r.stderr,encoding='utf-8')
assert r.returncode==0,r.stdout+r.stderr
c=json.loads(result.read_text(encoding='utf-8'))
assert c['image_size']==[1280,720] and c['frames_used']>=6
assert c['k3']==0 and len(c['reprojection_error'])==c['frames_used'] and c['rms']<1
assert c['synthetic_test_data'] and not c['capture_provenance_verified_by_tool']
assert len(c['input_images_sha256'])==c['frames_used']
# A phone screenshot cannot silently become an OV5640 calibration. Existing
# outputs also remain immutable, even if the caller supplied a valid dataset.
for extra in [['--source-kind','phone_screen','--out',str(out/'phone_forbidden.json')],
              ['--out',str(result)]]:
 bad=subprocess.run([sys.executable,str(p/'tools/calib_ov5640.py'),'--images',str(out/'view_*.png')]+extra,capture_output=True,text=True)
 assert bad.returncode!=0
assert not (out/'phone_forbidden.json').exists()
# Mixed resolutions must be rejected rather than silently using the last size.
cv2.imwrite(str(out/'view_99_wrong.png'),np.zeros((480,640,3),np.uint8))
bad=subprocess.run([sys.executable,str(p/'tools/calib_ov5640.py'),'--images',str(out/'view_*.png'),'--out',str(out/'must_not_exist.json')],capture_output=True,text=True)
assert bad.returncode!=0 and not (out/'must_not_exist.json').exists()
bad=subprocess.run([sys.executable,str(p/'tools/calib_ov5640.py'),'--images',str(out/'view_*.png'),
                    '--source-kind','ov5640_raw_digital','--out',str(out/'wrong_digital_size.json')],capture_output=True,text=True)
assert bad.returncode!=0 and not (out/'wrong_digital_size.json').exists()
# A file copied six times is still only one physical calibration view.
duplicates=out/'duplicates';duplicates.mkdir()
for i in range(6):shutil.copy2(out/'view_00.png',duplicates/f'copy_{i}.png')
bad=subprocess.run([sys.executable,str(p/'tools/calib_ov5640.py'),'--images',str(duplicates/'*.png'),
                    '--out',str(duplicates/'must_not_exist.json')],capture_output=True,text=True)
(out/'duplicates_test.log').write_text(bad.stdout+bad.stderr,encoding='utf-8')
assert bad.returncode!=0 and not (duplicates/'must_not_exist.json').exists()
# Real user paths contain Chinese characters; exercise byte decoding via CLI.
unicode_dir=out/'中文路径';unicode_dir.mkdir()
for i in range(12):shutil.copy2(out/f'view_{i:02d}.png',unicode_dir/f'角度_{i:02d}.png')
good=subprocess.run([sys.executable,str(p/'tools/calib_ov5640.py'),'--images',str(unicode_dir/'*.png'),
                     '--source-kind','synthetic','--out',str(unicode_dir/'synthetic.json')],capture_output=True,text=True)
(out/'unicode_test.log').write_text(good.stdout+good.stderr,encoding='utf-8')
assert good.returncode==0,good.stdout+good.stderr
assert json.loads((unicode_dir/'synthetic.json').read_text(encoding='utf-8'))['frames_used']==12
print('CALIBRATION PASS: synthetic CLI, four-term fit, reprojection report, mixed-size rejection, duplicate rejection, Chinese paths; NOT actual lens data',out)
