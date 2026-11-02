"""Repeatable synthetic evaluation of the adapted RGB preview filters."""
import hashlib,json,sys,time
from pathlib import Path
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from preview_denoise import PreviewDenoiser,suppress_impulses
out=ROOT/'reports/denoise_20261029';out.mkdir(exist_ok=True)
rng=np.random.default_rng(20261029)
h,w=720,1280
clean=np.full((h,w,3),100,np.uint8)
cv2.rectangle(clean,(100,100),(500,300),(190,190,190),-1)
cv2.line(clean,(50,400),(1200,550),(230,230,230),1)
cv2.putText(clean,'TEXT 720P / 1 PIXEL LINE',(80,630),cv2.FONT_HERSHEY_SIMPLEX,1.2,(220,220,220),1,cv2.LINE_AA)
clean[80,1000]=255 # Real isolated detail, intentionally ambiguous.
noisy=np.clip(clean.astype(float)+rng.normal(0,3,clean.shape),0,255).astype(np.uint8)
mask=np.zeros((h,w),bool)
ys=rng.integers(20,h-20,1200);xs=rng.integers(20,w-20,1200);mask[ys,xs]=True
values=rng.choice([0,255],size=(len(ys),1));noisy[ys,xs]=values
start=time.perf_counter();filtered,detected=suppress_impulses(noisy);impulse_ms=(time.perf_counter()-start)*1000
median=cv2.medianBlur(noisy,3)
mse=lambda a,b:float(np.mean((a.astype(float)-b.astype(float))**2))
results={'synthetic_only':True,'real_camera_image_evaluated':False,'fpga_firmware_changed':False,
         'injected_impulses':int(mask.sum()),'detected_injected_impulses':int((mask&detected).sum()),
         'replacements_outside_injected_mask':int((~mask&detected).sum()),
         'real_isolated_detail_removed':bool(detected[80,1000]),
         'mse_noisy_vs_clean':mse(noisy,clean),'mse_impulse_vs_clean':mse(filtered,clean),
         'mse_full_median_vs_clean':mse(median,clean),'impulse_processing_ms_one_run':impulse_ms}
# True independent frames, not repeated copies of one noisy image.
processor=PreviewDenoiser();times=[];raw_sum=0.;filtered_sum=0.;raw_sq=0.;filtered_sq=0.;sample_count=0
for index in range(64):
    frame=np.clip(np.rint(128+rng.normal(0,4,(h,w,3))),0,255).astype(np.uint8)
    start=time.perf_counter();temporal=processor.process(frame,'temporal');times.append((time.perf_counter()-start)*1000)
    if index>=16:
        a=frame.astype(np.float64)-128;b=temporal.astype(np.float64)-128
        raw_sum+=float(a.sum());filtered_sum+=float(b.sum())
        raw_sq+=float(np.sum(a*a));filtered_sq+=float(np.sum(b*b));sample_count+=a.size
results.update(independent_temporal_frames=64,temporal_burn_in_frames=16,
               temporal_input_sigma=float(np.sqrt(raw_sq/sample_count-(raw_sum/sample_count)**2)),
               temporal_output_sigma=float(np.sqrt(filtered_sq/sample_count-(filtered_sum/sample_count)**2)),
               temporal_output_bias=filtered_sum/sample_count,temporal_input_mse=raw_sq/sample_count,
               temporal_output_mse=filtered_sq/sample_count,
               temporal_processing_ms_median=float(np.median(times)),
               temporal_note='RGB8 adaptation keeps Q8 fractional frame history and rounds only display output. Preview arrival rate is not FPGA throughput.')
results['source_sha256']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['tools/preview_denoise.py','scripts/evaluate_preview_denoise.py']}
for name,image in [('clean_synthetic.png',clean),('noisy_synthetic.png',noisy),('impulse_synthetic.png',filtered),('median_synthetic.png',median)]:
    data=cv2.imencode('.png',image)[1].tobytes();(out/name).write_bytes(data)
    results[name+'_sha256']=hashlib.sha256(data).hexdigest()
# Crop enlarges a representative synthetic region only; full images retained.
views=[('SYNTHETIC: noisy',noisy),('Isolated-point filter',filtered),('Full 3x3 median',median)]
canvas=np.full((390,1200,3),245,np.uint8)
for i,(title,image) in enumerate(views):
    crop=image[160:340,560:800]
    enlarged=cv2.resize(crop,(400,300),interpolation=cv2.INTER_NEAREST)
    canvas[50:350,i*400:(i+1)*400]=enlarged
    cv2.putText(canvas,title,(i*400+10,30),cv2.FONT_HERSHEY_SIMPLEX,.55,(20,20,20),1,cv2.LINE_AA)
cv2.putText(canvas,'Software test only - NOT an actual camera or FPGA result',(15,378),cv2.FONT_HERSHEY_SIMPLEX,.65,(0,0,150),1,cv2.LINE_AA)
cv2.imencode('.png',canvas)[1].tofile(out/'synthetic_comparison.png')
(out/'synthetic_evaluation.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(results,ensure_ascii=False,indent=2))
