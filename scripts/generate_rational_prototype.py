"""Generate a diagnostic ROM from the measured rational candidate, no release."""
from pathlib import Path
import sys,json,argparse,hashlib
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from rational_lut import candidate_from_audit,build_table,write_rom,factor_float,factor_fixed
from margin_geometry import load,identity
ap=argparse.ArgumentParser();ap.add_argument('--audit',type=Path,required=True);a=ap.parse_args()
out=ROOT/'prototype';out.mkdir(exist_ok=True)
m=candidate_from_audit(a.audit,identity(load())[0]);table=build_table(m)
write_rom(out/'radial_factor.hex',table);(out/'candidate.json').write_text(json.dumps(m,indent=2),encoding='utf-8')
t=np.linspace(0,32,131073);q=np.rint(t*65536).astype(np.int64);factor,_=factor_fixed(table,q)
n=1+t*(m['k1']+t*(m['k2']+t*m['k3']));d=1+t*(m['k4']+t*(m['k5']+t*m['k6']))
dn=m['k1']+2*m['k2']*t+3*m['k3']*t*t;dd=m['k4']+2*m['k5']*t+3*m['k6']*t*t
derivative=n/d+2*t*(dn*d-n*dd)/(d*d)
r=dict(cells=2048,domain_r_squared=[0,32],rom_word_bits=64,base_delta_fraction_bits=24,output_fraction_bits=16,
 max_factor_error=float(np.max(np.abs(factor/65536-factor_float(m,q/65536)))),
 min_radius_map_derivative=float(derivative.min()),rom_sha256=hashlib.sha256((out/'radial_factor.hex').read_bytes()).hexdigest(),
 model_sha256=hashlib.sha256((out/'candidate.json').read_bytes()).hexdigest(),deployment_allowed=False,real_calibration_approved=False)
(out/'rom_report.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r,indent=2))
