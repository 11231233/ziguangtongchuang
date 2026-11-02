"""Count default 720P tile-window traffic analytically, not on hardware."""
import argparse
import json
from pathlib import Path
import numpy as np
from inspect_sampling_geometry import mapping

ROOT=Path(__file__).resolve().parents[1]


def traffic(c, optimized):
    x,y=np.meshgrid(np.arange(0,1280,16,dtype=np.int64),np.arange(0,720,16,dtype=np.int64))
    u,v=mapping(c,x[:,:,None]+np.array([0,15,0,15]),y[:,:,None]+np.array([0,0,15,15]))
    ui,vi=u>>16,v>>16
    mn_u,mx_u=ui.min(axis=2),ui.max(axis=2)
    mn_v,mx_v=vi.min(axis=2),vi.max(axis=2)
    axis=(all(c[k]==0 for k in ['k1','k2','p1','p2','B','D']) and all(c[k]>0 for k in ['A','E','fx','fy']))
    if optimized and axis:
        u0=np.clip(mn_u&~15,0,1264)
        v0=np.clip(mn_v,0,719)
        width=np.minimum(np.clip((mx_u-u0+2+15)&~15,16,64),1280-u0)
        height=np.minimum(np.clip(mx_v-v0+2,1,64),720-v0)
    else:
        u0=np.clip((mn_u-2)&~15,0,1216)
        v0=np.clip(mn_v-2,0,656)
        width=np.clip((mx_u-u0+4+15)&~15,16,64)
        height=np.clip(mx_v-v0+4,1,64)
    assert (width%16==0).all() and (u0+width<=1280).all() and (v0+height<=720).all()
    # The actually requested row bursts, each beat carrying 16 RGB565 pixels.
    requests=int(height.sum());beats=int((height*(width//16)).sum())
    return {'tiles':int(x.size),'read_requests':requests,'read_beats_256bit':beats,
            'read_bytes':beats*32,'optimized_axis_branch':bool(optimized and axis)}


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    if a.out.exists():ap.error('输出目录已存在')
    c=json.loads((ROOT/'targets/selected_empirical_profile.json').read_text(encoding='utf-8'))['signed_q16_coefficients']
    result={'simulation_only':True,'hardware_measured':False,'modes':{}}
    for name,p in [('RAW',dict(c,k1=0,k2=0,p1=0,p2=0)),('COR',c)]:
        old,new=traffic(p,False),traffic(p,True)
        result['modes'][name]={'before':old,'after':new,
            'read_requests_reduction_percent':100*(old['read_requests']-new['read_requests'])/old['read_requests'],
            'read_bytes_reduction_percent':100*(old['read_bytes']-new['read_bytes'])/old['read_bytes']}
    assert result['modes']['RAW']['after']['read_bytes']<result['modes']['RAW']['before']['read_bytes']
    assert result['modes']['COR']['after']['read_bytes']==result['modes']['COR']['before']['read_bytes']
    a.out.mkdir(parents=True)
    (a.out/'window_traffic.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
