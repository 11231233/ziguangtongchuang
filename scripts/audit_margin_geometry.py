"""Numerical feasibility audit; old model is illustrative, never a new calibration."""
from pathlib import Path
import json,math,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from margin_geometry import load,identity
g=load();sha,gid=identity(g)
k1=-21061/65536;k2=7082/65536
scale_min=-k1/(2*k2);displacement_max=-3*k1/(5*k2)
tmin=-3*k1/(10*k2);radius_deriv_min=1+3*k1*tmin+5*k2*tmin*tmin
y,x=np.mgrid[0:720,0:1280];nx=(126*x-80660)/65536.;ny=(126*y-45371)/65536.
rows=[]
for angle in range(-20,21):
 t=math.radians(angle);co=math.cos(t);si=math.sin(t)
 ux=(126*(co*(x-640)-si*(y-360)+640)-80660)/65536.
 uy=(126*(si*(x-640)+co*(y-360)+360)-45371)/65536.
 r2=ux*ux+uy*uy;s=1+k1*r2+k2*r2*r2
 u=520*ux*s+648;v=520*uy*s+486
 valid=(u>=0)&(u<=1295)&(v>=0)&(v<=971)
 rows.append(dict(angle=angle,valid_pixels=int(valid.sum()),invalid_pixels=int((~valid).sum()),u_range=[float(u.min()),float(u.max())],v_range=[float(v.min()),float(v.max())]))
result=dict(geometry_sha256=sha,geometry_id=gid,source_size=g['source_size'],output_size=g['output_size'],
 real_calibration=False,calibration_required=True,formal_correction_released=False,
 radial=dict(k1=k1,k2=k2,scale_min_r_squared=scale_min,absolute_displacement_max_r_squared=displacement_max,
 radius_map_derivative_min=radius_deriv_min,radius_map_is_monotonic_for_this_radial_only_polynomial=radius_deriv_min>0),
 corner_r_estimates=dict(old=math.hypot(640,360)/520,wide=math.hypot(648,486)/520),
 model_assumption='OLD EMPIRICAL MODEL ONLY; centered source shift +8/+126 is not a measured geometry transform',
 angle_coverage_illustrative=rows,
 linear_no_distortion_required_size_at_20deg=[1280*math.cos(math.radians(20))+720*math.sin(math.radians(20)),1280*math.sin(math.radians(20))+720*math.cos(math.radians(20))],
 padded_source_ddr_bytes_per_frame=1536*972*2,source_write_MBps_at_30=1536*972*2*30/1e6,
 sensor_rate_estimate_ratio_if_other_timing_unchanged=740/1000,
 sensor_timing_physically_verified=False,
 sources=['https://dl.sipeed.com/MAIX/HDK/Chip_DS/OV5640-datasheet.pdf','https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html'])
(ROOT/'reports/geometry_audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='angle_coverage_illustrative'},indent=2))
print('Illustrative full coverage across +/-20:',all(r['invalid_pixels']==0 for r in rows),'not a calibrated guarantee')
