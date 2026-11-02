from pathlib import Path
import argparse,hashlib,json,os,re,shutil,subprocess,sys,datetime
PDS_SHELL=os.environ.get('PDS_SHELL','D:/PDS/bin/pds_shell.exe')
p=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--name',required=True);ap.add_argument('--seed',type=int,default=2);ap.add_argument('--tpg',action='store_true');args=ap.parse_args()
status=json.loads((p/'targets/development_status.json').read_text(encoding='utf-8'))
if not status.get('runtime_top_integrated') or not status.get('real_calibration_approved'):
 raise SystemExit('Prototype only: new runtime top/model not approved. No formal correction bitstream can be built from this stage; see README and handoff.')
if not re.fullmatch(r'[A-Za-z0-9_\-]+',args.name):raise SystemExit('Invalid build name')
w=p/'build'/args.name
if w.exists():raise SystemExit('Build directory exists; choose a new name')
w.mkdir(parents=True);snap=w/'snapshot';snap.mkdir()
for d in ['rtl','constr']:shutil.copytree(p/d,snap/d)
# The top used to hard-code an absolute ROM path from the original workstation, so the
# project only built there. Point it at this build's own snapshot instead, which makes the
# package portable: unzip anywhere and the ROM still resolves.
_top=snap/'rtl/top/top_pangu50.v';_s=_top.read_text(encoding='utf-8')
_rom=(snap/'rtl/warp/radial_lut.hex').as_posix()
_s,_n=re.subn(r'\.RADIAL_LUT_FILE\("[^"]*"\)','.RADIAL_LUT_FILE("%s")'%_rom,_s)
if _n!=1:raise SystemExit(f'expected exactly one RADIAL_LUT_FILE, found {_n}')
_top.write_text(_s,encoding='utf-8')
if args.tpg:
 f=snap/'rtl/top/top_pangu50.v';s=f.read_text(encoding='utf-8');s,n=re.subn(r'parameter integer USE_TPG\s*=\s*0','parameter integer USE_TPG = 1',s);assert n==1;f.write_text(s,encoding='utf-8')
files=[snap/'rtl/top/top_pangu50.v']
for d in ['common','video','cam','hdmi','mem']:files.extend(sorted((snap/'rtl'/d).glob('*.v')))
files=[f for f in files if f.name!='cmos_8_16bit.v']
files.append(snap/'rtl/ddr/sync_vg.v')
files.extend(sorted(f for f in (snap/'rtl/warp').glob('*.v') if f.name not in ['line_ring.v','tile_fetch.v']))
files.extend([snap/'rtl/ip/pll/pll.v',snap/'rtl/ip/pll/pll_720p60.v',snap/'rtl/ip/ddr3/DDR3_50H.v',snap/'rtl/ip/ddr3/DDR3_50H_ddrphy_top.v'])
files.extend(sorted(f for f in (snap/'rtl/ip/ddr3/rtl').rglob('*') if f.suffix.lower() in ['.v','.vp']))
assert len(files)==len(set(files));assert all(f.is_file() for f in files)
mods={}
for f in files:
 if f.suffix=='.v':
  for m in re.findall(r'(?m)^\s*module\s+(\w+)',f.read_text(errors='replace')):
   if m in mods:raise SystemExit(f'Duplicate module {m}: {mods[m]} and {f}')
   mods[m]=str(f)
cons=[snap/'constr'/n for n in ['board_pins.fdc','ddr3_pins.fdc','timing.fdc']]
tcl=['set_arch -family Logos -device PGL50H -speedgrade -6 -package FBG484']
tcl += [f'add_design "{f.as_posix()}"' for f in files]
tcl += [f'add_constraint "{f.as_posix()}"' for f in cons]
tcl += ['compile -top_module top_pangu50','synthesize -ads -selected_syn_tool_opt 2','dev_map',f'pnr -gplace_seed {args.seed} -fix_hold_violation_iterations 30','report_timing','gen_bit_stream']
(w/'build.tcl').write_text('\n'.join(tcl)+'\n',encoding='ascii')
manifest={str(f.relative_to(snap)).replace('\\','/'):hashlib.sha256(f.read_bytes()).hexdigest() for f in files+cons}
(w/'input_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(f'BUILD {w} seed={args.seed} files={len(files)}',flush=True)
with (w/'console.log').open('w') as log:
 r=subprocess.run([PDS_SHELL,'-file',(w/'build.tcl').as_posix(),'-work_dir',w.as_posix()],stdout=log,stderr=subprocess.STDOUT,cwd=w)
errors=[]
if r.returncode:errors.append(f'PDS exit {r.returncode}')
log=(w/'console.log').read_text(errors='replace')
if re.search(r'(?m)^E:',log):errors.append('PDS E-level message')
for f in (w/'compile').rglob('error_info.txt'):
 text=f.read_text(errors='replace')
 if re.search(r'Verilog-4\d{3}|^E:',text,re.M):errors.append(str(f))
rpt=w/'report_timing/top_pangu50.rtr'
if not rpt.exists() or 'Design Summary : All Constraints Met' not in rpt.read_text(errors='replace'):errors.append('Timing did not pass all configured constraints')
if 'Executing : gen_bit_stream successfully.' not in log:errors.append('Bitstream generation not confirmed')
bit=w/'generate_bitstream/top_pangu50.sbit'
if not bit.exists():errors.append('Missing bitstream')
result={'build':args.name,'passed':not errors,'errors':errors,'seed':args.seed,'tpg':args.tpg}
(w/'validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result),flush=True)
raise SystemExit(1 if errors else 0)
