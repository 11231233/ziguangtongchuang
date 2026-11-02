"""Engineering slanted-edge SFR; not an ISO-certified camera MTF measurement."""
import argparse
import csv
import json
from pathlib import Path
import cv2
import numpy as np
from rectify_monitor import load_image, sha


def measure(image, roi, exponent=1.0):
    x, y, w, h = map(int, roi)
    if min(w, h) < 32 or min(x, y) < 0 or x+w > image.shape[1] or y+h > image.shape[0]:
        raise ValueError('ROI must be inside image and at least 32 by 32 pixels')
    if not np.isfinite(exponent) or not 0.1 <= exponent <= 5:
        raise ValueError('Invalid explicit signal linearization exponent')
    gray = cv2.cvtColor(image[y:y+h, x:x+w], cv2.COLOR_BGR2GRAY).astype(float)/255
    gray = gray**exponent
    if np.mean(np.abs(np.diff(gray, axis=0))) > np.mean(np.abs(np.diff(gray, axis=1))):
        gray = gray.T
    height, width = gray.shape
    grad = np.abs(np.diff(gray, axis=1))
    peaks = np.argmax(grad, axis=1)
    if np.any(peaks < 8) or np.any(peaks > width-10):
        raise ValueError('Edge must remain away from ROI borders')
    centers = []
    for row, peak in zip(grad, peaks):
        ids = np.arange(max(0, peak-4), min(width-1, peak+5))
        weights = row[ids]
        if weights.sum() < 0.03:
            raise ValueError('Insufficient edge contrast')
        centers.append(float(np.sum((ids+0.5)*weights)/weights.sum()))
    slope, intercept = np.polyfit(np.arange(height), centers, 1)
    angle = float(np.degrees(np.arctan(abs(slope))))
    if not 2 <= angle <= 12:
        raise ValueError('Use a single edge slanted 2 to 12 degrees from vertical or horizontal')
    residual = float(np.sqrt(np.mean((np.asarray(centers)-(slope*np.arange(height)+intercept))**2)))
    if residual > 0.5:
        raise ValueError('Edge is curved, noisy or contains multiple edges; fit residual exceeds 0.5 px')
    yy, xx = np.indices(gray.shape)
    distance = (xx-(slope*yy+intercept))/np.sqrt(1+slope*slope)
    radius = min(32, int(min(np.min(centers), width-1-max(centers)))-3)
    if radius < 10:
        raise ValueError('ROI lacks room on both sides of edge')
    step = 0.25
    bins = np.floor((distance+radius)/step).astype(int)
    n = radius*8
    valid = (bins >= 0) & (bins < n)
    count = np.bincount(bins[valid], minlength=n)
    if np.any(count == 0):
        raise ValueError('Insufficient slant sampling; enlarge ROI along edge')
    esf = np.bincount(bins[valid], weights=gray[valid], minlength=n)/count
    contrast = abs(float(np.mean(esf[-12:])-np.mean(esf[:12])))
    if contrast < 0.1:
        raise ValueError('Edge contrast below 10 percent')
    lsf = np.diff(esf)/step
    lsf *= np.hamming(len(lsf))
    spectrum = abs(np.fft.rfft(lsf))
    if spectrum[0] < 1e-8:
        raise ValueError('Invalid edge response')
    freq = np.fft.rfftfreq(len(lsf), step)
    # Forward difference transfer: 2*sin(pi*f*step)/step, relative to ideal derivative.
    correction = np.ones_like(freq)
    nz = freq > 0
    correction[nz] = np.pi*freq[nz]*step/np.sin(np.pi*freq[nz]*step)
    mtf = spectrum/spectrum[0]*correction
    keep = freq <= 0.5
    freq, mtf = freq[keep], mtf[keep]
    crossing = np.where(mtf <= 0.5)[0]
    mtf50 = None
    if len(crossing) and crossing[0] > 0:
        i = crossing[0]
        mtf50 = float(np.interp(0.5, [mtf[i], mtf[i-1]], [freq[i], freq[i-1]]))
    return {'mtf50_cycles_per_pixel': mtf50, 'edge_slant_degrees': angle,
            'edge_fit_rms_pixels': residual, 'linearization_exponent': exponent,
            'contrast_linear_signal': contrast, 'oversampling': 4,
            'certified_iso_measurement': False, 'frequency': freq.tolist(), 'sfr': mtf.tolist(),
            'esf_distance': ((np.arange(n)+0.5)*step-radius).tolist(), 'esf': esf.tolist()}


def save(image_path, roi, out, source='phone_screen', exponent=1.0):
    out = Path(out)
    if out.exists():
        raise ValueError('Output exists; choose a new directory')
    result = measure(load_image(image_path), roi, exponent)
    result.update(image=str(Path(image_path).resolve()), image_sha256=sha(image_path), roi=list(roi),
                  source_operator_declared=source, physical_provenance_verified=False,
                  isolated_camera_mtf_verified=False,
                  scope='Combined camera/display/phone response' if source != 'digital_hdmi' else
                        'Digital video processing chain; optical isolation unverified',
                  limitations=['Engineering estimator, not ISO certification',
                               'Phone screen includes display scaling, phone lens, moire and processing',
                               'Unknown tone curve and sharpening can bias SFR; exponent is operator specified',
                               'Compare matching edge size, exposure, sampling and ROI; FOC is not MTF50'])
    out.mkdir(parents=True)
    (out/'sfr.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    with (out/'sfr.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f); writer.writerow(['cycles_per_pixel', 'sfr'])
        writer.writerows(zip(result['frequency'], result['sfr']))
    im = load_image(image_path)
    x,y,w,h = map(int,roi); cv2.rectangle(im,(x,y),(x+w,y+h),(0,0,255),2)
    cv2.imencode('.png',im)[1].tofile(out/'roi.png')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image',required=True); p.add_argument('--roi',type=int,nargs=4,required=True)
    p.add_argument('--out',required=True)
    p.add_argument('--source',choices=['phone_screen','monitor_rectified','digital_hdmi'],default='phone_screen')
    p.add_argument('--linearization-exponent',type=float,default=1.0)
    a=p.parse_args()
    try:
        r=save(a.image,a.roi,a.out,a.source,a.linearization_exponent)
    except (ValueError,OSError) as e:
        p.error(str(e))
    print(json.dumps({'mtf50_cycles_per_pixel':r['mtf50_cycles_per_pixel'],'scope':r['scope']}))


if __name__=='__main__': main()
