"""Analytical/synthetic checks, never physical camera evidence."""
import datetime
import json
import math
from pathlib import Path
import subprocess
import sys
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from rectify_monitor import rectify, load_image, sha
from measure_sfr import measure, save
import quality_workbench

out=ROOT/'build'/('quality_tools_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
out.mkdir()
checks=[]
def rejected(call):
    try:call()
    except (ValueError,OSError):return
    raise AssertionError('Invalid input was accepted')

# Gaussian-blurred edges have an analytical MTF50, independent of our estimator.
yy,xx=np.indices((240,240))
distance=(xx-120-.0875*(yy-120))/np.sqrt(1+.0875**2)
values=[]
for sigma in (1.,1.5,2.,3.):
    esf=.5+.5*np.vectorize(math.erf)(distance/(math.sqrt(2)*sigma))
    image=np.repeat(np.rint((.1+.8*esf)*255).astype(np.uint8)[:,:,None],3,axis=2)
    r=measure(image,[0,0,240,240])
    expected=math.sqrt(math.log(2))/(math.sqrt(2)*math.pi*sigma)
    assert abs(r['mtf50_cycles_per_pixel']/expected-1)<.08,(sigma,r['mtf50_cycles_per_pixel'],expected)
    values.append({'sigma':sigma,'expected':expected,'measured':r['mtf50_cycles_per_pixel']})
    cv2.imencode('.png',image)[1].tofile(out/f'edge_{sigma}.png')
assert all(values[i]['measured']>values[i+1]['measured'] for i in range(3))
rejected(lambda:measure(image,[-1,0,100,100]))
rejected(lambda:measure(np.zeros_like(image),[0,0,240,240]))
axis=np.zeros_like(image); axis[:,120:]=255
rejected(lambda:measure(axis,[0,0,240,240]))
edgepath=out/'中文斜边.png'; cv2.imencode('.png',image)[1].tofile(edgepath)
r=save(edgepath,[0,0,240,240],out/'sfr')
assert not r['isolated_camera_mtf_verified'] and not r['certified_iso_measurement']
rejected(lambda:save(edgepath,[0,0,240,240],out/'sfr'))
checks.append('Analytical Gaussian MTF50 within 8 percent for four blur widths; monotonicity; ROI/contrast/slant/no-overwrite guards; Chinese paths')

# A known planar screen is photographed through a projective transform.
base=sorted((ROOT/'build').glob('synthetic_calibration_*/view_00.png'))[-1].parent
phone={'fx':1200,'fy':1200,'cx':700,'cy':425,'k1':0,'k2':0,'p1':0,'p2':0,'k3':0,
       'image_size':[1400,850],'source_kind_operator_declared':'phone_direct','synthetic_test_data':True}
phonepath=out/'synthetic_phone.json'; phonepath.write_text(json.dumps(phone),encoding='utf-8')
q=np.array([[70,50],[1330,80],[1300,800],[90,780]],np.float32)
src=np.array([[0,0],[1279,0],[1279,719],[0,719]],np.float32)
matrix=cv2.getPerspectiveTransform(src,q)
photos=out/'展开集';photos.mkdir()
for i in range(12):
    im=load_image(base/f'view_{i:02d}.png')
    photo=cv2.warpPerspective(im,matrix,(1400,850))
    path=out/f'photo_{i:02d}.png';cv2.imencode('.png',photo)[1].tofile(path)
    m=rectify(path,q,photos/f'view_{i:02d}',phonepath)
    assert m['eligible_for_indirect_fit'] and m['synthetic_test_data'] and not m['direct_sensor_pixels']
    rect=load_image(photos/f'view_{i:02d}'/'screen.png')
    assert np.mean(abs(rect.astype(float)-im.astype(float)))<3
rejected(lambda:rectify(path,q,photos/'view_00',phonepath))
rejected(lambda:rectify(path,q[::-1],out/'wrong_order',phonepath))
wrong=dict(phone,image_size=[1280,720]); wrongpath=out/'wrongphone.json'; wrongpath.write_text(json.dumps(wrong))
rejected(lambda:rectify(path,q,out/'wrongsize',wrongpath))
for label,args in [('nomodel',{}),('cor',{'phone_calib':phonepath,'mode':'COR'}),
                   ('g1',{'phone_calib':phonepath,'gamma':'G1'}),('t1',{'phone_calib':phonepath,'test_mode':'T1'})]:
    assert not rectify(path,q,out/label,**args)['eligible_for_indirect_fit']
checks.append('Known homography reconstruction under 3 mean code values; corner order, model resolution, duplicate output, COR/G1/T1 and missing phone model guards')
args=[sys.executable,str(ROOT/'tools/calib_ov5640.py'),'--images',str(photos/'*'/'screen.png'),
      '--source-kind','monitor_rectified','--square','25','--out',str(out/'indirect.json')]
r=subprocess.run(args,capture_output=True,text=True)
(out/'indirect_fit.log').write_text(r.stdout+r.stderr,encoding='utf-8')
assert r.returncode==0,r.stdout+r.stderr
c=json.loads((out/'indirect.json').read_text(encoding='utf-8'))
assert c['frames_used']==12 and c['rms']<1
assert c['indirect_estimate'] and c['synthetic_test_data'] and not c['high_precision_calibration_verified']
assert c['calibration_scope']=='ov5640_indirect_monitor_estimate'
# Tampered image provenance must prevent fit.
meta=photos/'view_00'/'metadata.json';m=json.loads(meta.read_text());m['output_sha256']='0'*64;meta.write_text(json.dumps(m))
args[-1]=str(out/'tamper_must_fail.json')
bad=subprocess.run(args,capture_output=True,text=True)
assert bad.returncode and not (out/'tamper_must_fail.json').exists()
checks.append('12-view synthetic indirect fit, source/synthetic flags, four-term RMS, tamper rejection; no physical calibration claimed')
(out/'result.json').write_text(json.dumps({'passed':True,'synthetic_only':True,'checks':checks,'gaussian_mtf50':values,'gui_import_passed':True,'native_gui_visual_qa':False,
    'tool_sha256':{str(f.relative_to(ROOT)).replace('\\','/'):sha(f) for f in [ROOT/'tools/rectify_monitor.py',ROOT/'tools/measure_sfr.py',ROOT/'tools/calib_ov5640.py',ROOT/'tools/quality_workbench.py']}},indent=2),encoding='utf-8')
print('QUALITY WORKBENCH PASS',out)
