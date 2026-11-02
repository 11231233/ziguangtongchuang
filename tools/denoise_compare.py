"""File-only denoising comparison. No camera/serial devices are opened."""
import argparse
import json
import time
from pathlib import Path
import cv2
import numpy as np
from calibration_workflow import read_image,digest
from preview_denoise import PreviewDenoiser


def main():
    p=argparse.ArgumentParser(description=__doc__)
    source=p.add_mutually_exclusive_group(required=True)
    source.add_argument('--image',type=Path);source.add_argument('--video',type=Path)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--mode',choices=['impulse','median','temporal','combined','small_spots','bilateral'],default='small_spots')
    p.add_argument('--max-frames',type=int,default=120)
    a=p.parse_args()
    if a.out.exists():p.error('output exists; choose a new directory')
    if a.max_frames<1:p.error('max-frames must be positive')
    if a.image and a.mode in ('temporal','combined'):
        p.error('temporal modes require a real multi-frame video; one still image is not a sequence')
    processor=PreviewDenoiser();times=[];modified=[];cap=None;frame=None;result=None
    try:
        if a.image:frames=iter([read_image(a.image)])
        else:
            if not a.video.is_file():p.error('video does not exist')
            cap=cv2.VideoCapture(str(a.video))
            if not cap.isOpened():p.error('cannot decode video')
            def sequence():
                for _ in range(a.max_frames):
                    ok,image=cap.read()
                    if not ok:return
                    yield image
            frames=sequence()
        for frame in frames:
            before=time.perf_counter();result=processor.process(frame,a.mode,use_temporal=bool(a.video))
            times.append((time.perf_counter()-before)*1000)
            modified.append(int(np.count_nonzero(np.any(result!=frame,axis=2))))
    finally:
        if cap is not None:cap.release()
    if frame is None:raise SystemExit('no decoded frames')
    a.out.mkdir(parents=True)
    report=dict(mode=a.mode,input=str(a.image or a.video),input_sha256=digest((a.image or a.video).read_bytes()),
                frames=len(times),image_size=[frame.shape[1],frame.shape[0]],
                processing_ms_median=float(np.median(times)),processing_ms_max=max(times),
                modified_pixels_last_frame=modified[-1],actual_quality_improved=None,
                fpga_denoise_applied=False,real_board_30fps_verified=False,
                note='Software processing timings only; no clean reference. Modification count is not a quality score.')
    for name,image in [('original.png',frame),('denoised.png',result),('difference_x4.png',cv2.convertScaleAbs(cv2.absdiff(frame,result),alpha=4))]:
        ok,data=cv2.imencode('.png',image)
        if not ok:raise RuntimeError('PNG encode failed')
        (a.out/name).write_bytes(data.tobytes());report[name+'_sha256']=digest(data.tobytes())
    (a.out/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
