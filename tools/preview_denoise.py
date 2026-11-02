"""RGB8 software preview experiment inspired by the supplied RAW denoising model.
It never modifies capture pixels, FPGA output or calibration files.
"""
import cv2
import numpy as np

MODES = {'关闭':'off', '小斑点修复（新版）':'small_spots', '保边柔和降噪':'bilateral',
         '孤立光点抑制':'impulse', '自适应时域降噪':'temporal',
         '光点抑制＋时域':'combined', '3×3中值（较强）':'median'}


def check_image(image):
    if not isinstance(image, np.ndarray) or image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError('expected uint8 BGR image')


def repair_small_spots(image, threshold=48, max_area=9, ring_spread=32):
    """Stateless small-component repair, including 2x2/3x3 resampling blobs.
    Only modify compact outliers with a flat surrounding ring. Real isolated
    small features remain fundamentally ambiguous; this is not a defect map.
    """
    check_image(image)
    if not 1 <= threshold <= 255 or not 1 <= max_area <= 9 or not 0 <= ring_spread <= 255:
        raise ValueError('invalid small-spot parameters')
    background=cv2.medianBlur(image,5)
    residual=cv2.absdiff(image,background)
    candidate=cv2.bitwise_not(cv2.inRange(residual,(0,0,0),(threshold,)*3))
    output=image.copy();repaired=np.zeros(image.shape[:2],bool)
    # Heavy texture or widespread corruption is not a sparse-defect case.
    if np.count_nonzero(candidate) > candidate.size*.02:
        return output,repaired
    count,labels,stats,_=cv2.connectedComponentsWithStats(candidate,connectivity=8)
    height,width=image.shape[:2]
    x,y,w,h,area=stats.T
    cx=x+(w-1)//2;cy=y+(h-1)//2
    eligible=(area<=max_area)&(w<=3)&(h<=3)&(cx>=3)&(cy>=3)&(cx+3<width)&(cy+3<height)
    eligible[0]=False
    ids=np.flatnonzero(eligible)
    if not len(ids):return output,repaired
    if len(ids)<=16:
        # A few tiny patches are cheaper than full-frame ring morphology.
        for index in ids:
            xx,yy,ww,hh=map(int,(x[index],y[index],w[index],h[index]))
            patch=image[yy-2:yy+hh+2,xx-2:xx+ww+2]
            ring_mask=np.ones(patch.shape[:2],bool);ring_mask[2:2+hh,2:2+ww]=False
            samples=patch[ring_mask]
            if np.any(samples.max(axis=0).astype(np.int16)-samples.min(axis=0).astype(np.int16)>ring_spread):
                continue
            local_mask=labels[yy:yy+hh,xx:xx+ww]==index
            output[yy:yy+hh,xx:xx+ww][local_mask]=np.median(samples,axis=0).astype(np.uint8)
            repaired[yy:yy+hh,xx:xx+ww]|=local_mask
        return output,repaired
    # Evaluate a two-pixel ring around each 3x3 center in OpenCV, instead of
    # a Python loop and a separate median allocation for every component.
    ring=np.ones((7,7),np.uint8);ring[2:5,2:5]=0
    low=cv2.erode(image,ring,borderType=cv2.BORDER_REPLICATE)
    high=cv2.dilate(image,ring,borderType=cv2.BORDER_REPLICATE)
    span=high[cy[ids],cx[ids]].astype(np.int16)-low[cy[ids],cx[ids]].astype(np.int16)
    ids=ids[np.all(span<=ring_spread,axis=1)]
    accepted=np.zeros(count,bool);accepted[ids]=True
    repaired=accepted[labels]
    colors=np.zeros((count,3),np.uint8)
    colors[ids]=background[cy[ids],cx[ids]]
    output[repaired]=colors[labels[repaired]]
    return output,repaired


def gentle_bilateral(image):
    """Small spatial window and mild color range, no temporal persistence."""
    check_image(image)
    return cv2.bilateralFilter(image,5,12,1.5,borderType=cv2.BORDER_REPLICATE)


def suppress_impulses(image, threshold=32, neighbor_spread=24, defect_mask=None):
    """Replace calibrated defects or isolated extrema in flat 8-neighborhoods.
    The heuristic cannot distinguish a genuine isolated detail from a hot pixel.
    Borders are retained. A supplied defect mask is explicit operator input.
    """
    check_image(image)
    if not 1 <= threshold <= 255 or not 0 <= neighbor_spread <= 255:
        raise ValueError('invalid 8-bit impulse thresholds')
    if defect_mask is not None:
        mask = np.asarray(defect_mask, dtype=bool)
        if mask.shape != image.shape[:2]: raise ValueError('defect mask size mismatch')
        mask = mask.copy()
    else:
        kernel = np.ones((3,3),np.uint8);kernel[1,1]=0
        minimum = cv2.erode(image,kernel,borderType=cv2.BORDER_REPLICATE)
        maximum = cv2.dilate(image,kernel,borderType=cv2.BORDER_REPLICATE)
        bright = cv2.inRange(cv2.subtract(image, maximum),(0,0,0),(threshold,)*3)
        dark = cv2.inRange(cv2.subtract(minimum, image),(0,0,0),(threshold,)*3)
        flat = cv2.inRange(cv2.subtract(maximum,minimum),(0,0,0),(neighbor_spread,)*3)
        mask = cv2.bitwise_and(cv2.bitwise_not(cv2.bitwise_and(bright,dark)),flat)>0
    mask[[0,-1],:] = False;mask[:,[0,-1]] = False
    output = image.copy()
    ys,xs=np.nonzero(mask)
    if len(ys):
        samples=np.stack([image[ys+dy,xs+dx] for dy in (-1,0,1) for dx in (-1,0,1)])
        output[ys,xs]=np.partition(samples,4,axis=0)[4]
    return output, mask


def temporal_step(current, previous, motion_threshold=32, alpha_min=32):
    """Shared RGB motion decision; UQ1.8 alpha, floor shift like the RAW model."""
    check_image(current)
    if not 1 <= motion_threshold <= 255 or not 1 <= alpha_min <= 256:
        raise ValueError('invalid temporal parameters')
    if previous is None or previous.shape != current.shape:
        return current.copy()
    check_image(previous)
    x=current.astype(np.int32);yp=previous.astype(np.int32)
    difference=np.max(np.abs(x-yp),axis=2)
    gain=65536//motion_threshold
    alpha=np.clip((difference*gain)>>8,alpha_min,256)
    alpha[difference>=motion_threshold]=256
    result=yp+(((x-yp)*alpha[:,:,None])>>8)
    return np.clip(result,0,255).astype(np.uint8)


def temporal_q8_step(current, previous_q8):
    """Keep fractional history for RGB8; otherwise per-frame flooring darkens it.
    Motion uses the largest channel difference; alpha remains UQ1.8.
    """
    x=current.astype(np.int32)<<8
    if previous_q8 is None or previous_q8.shape != current.shape:
        return current.copy(),x
    delta=x-previous_q8
    difference=np.max(np.abs(delta),axis=2)>>8
    alpha=np.clip((difference*2048)>>8,32,256)
    alpha[difference>=32]=256
    state=np.clip(previous_q8+((delta*alpha[:,:,None])>>8),0,255<<8)
    return np.clip((state+128)>>8,0,255).astype(np.uint8),state


class PreviewDenoiser:
    def __init__(self): self.reset()
    def reset(self):
        self.previous=None;self.last_input=None;self.last_output=None
        self.mode=None;self.temporal_enabled=None;self.corrected_pixels=0
    def process(self, image, mode='off', use_temporal=True):
        check_image(image)
        if mode not in set(MODES.values()): raise ValueError('unknown denoise mode')
        if self.mode != mode or self.temporal_enabled != use_temporal:
            self.reset();self.mode=mode;self.temporal_enabled=use_temporal
        # Window resizes or repeated rendering of one capture frame must not
        # advance the recursion and pretend that another frame was acquired.
        if self.last_input is image:
            return self.last_output
        self.corrected_pixels=0
        if mode in ('impulse','combined'):
            result,mask=suppress_impulses(image);self.corrected_pixels=int(mask.sum())
        elif mode=='median': result=cv2.medianBlur(image,3)
        elif mode=='small_spots':
            result,mask=repair_small_spots(image);self.corrected_pixels=int(mask.sum())
        elif mode=='bilateral': result=gentle_bilateral(image)
        else: result=image.copy()
        if mode in ('temporal','combined') and use_temporal:
            result,self.previous=temporal_q8_step(result,self.previous)
        else: self.previous=None
        self.last_input=image;self.last_output=result
        return result
