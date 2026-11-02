"""Offline guard for the FPGA 64x64 window; never sends coordinates to hardware."""
import numpy as np

def validate(c,width=1280,height=720):
    if width%16 or height%16:raise ValueError('guard requires dimensions divisible by 16')
    x,y=np.meshgrid(np.arange(width,dtype=np.int64),np.arange(height,dtype=np.int64))
    def mul(a,b):return (a*b+32768)>>16
    ux=c['A']*x+c['B']*y+c['C'];uy=c['D']*x+c['E']*y+c['F']
    if max(int(np.abs(ux).max()),int(np.abs(uy).max()))>=4*65536:
        raise ValueError('normalized coordinates exceed RTL range [-4,4)')
    r2=(ux*ux+uy*uy+32768)>>16
    qx=mul(ux,ux);qy=mul(uy,uy);qxy=mul(ux,uy)
    rad=65536+mul(c['k1'],r2)+mul(c['k2'],mul(r2,r2))
    u=mul(c['fx'],mul(ux,rad)+2*mul(c['p1'],qxy)+mul(c['p2'],r2+2*qx))+c['cx']
    v=mul(c['fy'],mul(uy,rad)+mul(c['p1'],r2+2*qy)+2*mul(c['p2'],qxy))+c['cy']
    ui=u>>16;vi=v>>16
    def corners(a):return [a[0::16,0::16],a[15::16,0::16],a[0::16,15::16],a[15::16,15::16]]
    # coord_map saturates pixel coordinates before exposing its 16-bit integer.
    us=np.clip(ui,-32768,32767);vs=np.clip(vi,-32768,32767)
    wu=np.clip((np.minimum.reduce(corners(us))-2)&~15,0,width-64)
    wv=np.clip(np.minimum.reduce(corners(vs))-2,0,height-64)
    bw=np.clip((np.maximum.reduce(corners(us))-wu+4+15)&~15,16,64)
    bh=np.clip(np.maximum.reduce(corners(vs))-wv+4,1,64)
    def expand(a):return np.repeat(np.repeat(a,16,axis=0),16,axis=1)
    wu,wv,bw,bh=map(expand,(wu,wv,bw,bh))
    valid=(u>=0)&(u<=(width-1)*65536)&(v>=0)&(v<=(height-1)*65536)
    need_x=np.minimum(ui+1,width-1);need_y=np.minimum(vi+1,height-1)
    inside=(ui>=wu)&(vi>=wv)&(need_x<wu+bw)&(need_y<wv+bh)
    missing=int(np.count_nonzero(valid&~inside))
    if missing:raise ValueError(f'{missing} valid samples exceed fetched windows: increase zoom or reduce distortion/tilt')
    return {'passed':True,'output_pixels':width*height,'valid_pixels':int(valid.sum()),
            'window_misses':missing,'coordinate_map_uploaded':False}
