from pathlib import Path
import argparse,datetime,hashlib,json,re,shutil,subprocess,sys
from verify import test,env
p=Path(__file__).resolve().parents[1]
from sim_lock import acquire
_simulation_lock=acquire(p)
ap=argparse.ArgumentParser();ap.add_argument('--roll',type=float,default=0);ap.add_argument('--shared',action='store_true');ap.add_argument('--selected-preset',action='store_true');ap.add_argument('--matched-raw',action='store_true');args=ap.parse_args()
if args.matched_raw and not args.selected_preset:ap.error('--matched-raw requires --selected-preset')
if args.selected_preset and args.roll:ap.error('selected preset uses its exact zero-rotation coefficients')
out=p/'sim/results'/('full720_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'));out.mkdir(parents=True)
manifest={f.relative_to(p).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in (p/'rtl').rglob('*.v')}
subprocess.run([sys.executable,str(p/'tools/gen_full_reference.py'),'--720p','--roll',str(args.roll)]+(['--selected-preset'] if args.selected_preset else [])+(['--matched-raw'] if args.matched_raw else []),check=True,env=env)
files=['-DFULL720P']+[f.relative_to(p).as_posix() for f in (p/'rtl/warp').glob('*.v') if f.name not in ['tile_fetch.v','line_ring.v']]+['sim/tb/tb_full.v']
if args.shared:files=['-DSHARED_DDR']+files+['rtl/mem/mem_hub.v','sim/model/video_background.v']
ok=test('full720','tb_full',files,timeout=900)
changed=[n for n,h in manifest.items() if hashlib.sha256((p/n).read_bytes()).hexdigest()!=h]
if changed:ok=False;print('RTL changed during full720 verification:',changed,flush=True)
for name in ['full720.log','full720_compile.log','frame_coef.vh']:shutil.copy2(p/'sim/out'/name,out/name)
log=(out/'full720.log').read_text();cycles=re.findall(r'FULL_FRAME PASS:[^\n]*;\s*cycles=\s*(\d+)',log)
cycles=int(cycles[-1]) if ok else None
data={'passed':ok,'simulation_only':True,'width':1280,'height':720,'roll':args.roll,'exact_compared_pixels':921600 if ok else 0,
 'frame_cycles':cycles,'clock_hz':100000000,'isolated_engine_fps':100000000/cycles if ok else None,
 'meets_60fps_in_this_model':bool(ok and cycles<=100000000/60),
 'shared_capture_display_ddr_modeled':args.shared,
 'background_profile':'16-beat read and write bursts each 463 clocks (average 720P60 RGB565 payload)' if args.shared else None,
 'ddr_phy_model':False,'hardware_measured':False,'selected_preset':args.selected_preset,'matched_raw':args.matched_raw,'rtl_changed_during_run':changed,'rtl_sha256':manifest}
if args.selected_preset:data['preset_sha256']=hashlib.sha256((p/'targets/selected_empirical_profile.json').read_bytes()).hexdigest()
perf=re.findall(r'^PERF (.+)$',log,re.M)
if perf:data['performance_counters']={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',perf[-1])}
data['performance_counters_scope']='Simulation observations. Counters overlap and do not partition total cycles. Not board measurements.'
(out/'result.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
print(json.dumps(data|{'rtl_sha256':'see result.json'}),flush=True)
raise SystemExit(0 if ok else 1)
