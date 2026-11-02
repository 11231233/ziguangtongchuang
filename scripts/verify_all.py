from pathlib import Path
import argparse,datetime,hashlib,json,shutil,subprocess,sys
from verify import test,env
p=Path(__file__).resolve().parents[1]
from sim_lock import acquire
_simulation_lock=acquire(p)
ap=argparse.ArgumentParser();ap.add_argument('--quick',action='store_true');a=ap.parse_args()
run=p/'sim/results'/datetime.datetime.now().strftime('%Y%m%d_%H%M%S');run.mkdir(parents=True)
manifest={str(f.relative_to(p)).replace('\\','/'):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted((p/'rtl').rglob('*.v'))}
results=[]
def call(name,top,files):
 ok=test(name,top,files)
 for suffix in ['.log','_compile.log']:shutil.copy2(p/'sim/out'/(name+suffix),run/(name+suffix))
 results.append({'name':name,'passed':ok})
 (run/'summary.json').write_text(json.dumps({'passed':False,'complete':False,'tests':results,'rtl_sha256':manifest},indent=2),encoding='utf-8')
 if not ok:raise SystemExit('FAILED '+name)
for f in ['gen_coord_vectors.py','gen_bilin_vectors.py','gen_host_vectors.py','gen_stereo_vectors.py']:subprocess.run([sys.executable,str(p/'tools'/f)],check=True,env=env)
warp=['rtl/warp/coord_map.v','rtl/warp/bilinear_2x2.v','rtl/warp/warp_tile.v']
call('key_short_long','tb_key_short_long',['rtl/common/key_short_long.v','rtl/common/stereo_controls.v','rtl/common/adaptive_gamma.v','sim/tb/tb_key_short_long.v'])
call('freeze_toggle','tb_freeze_toggle',['rtl/common/freeze_toggle.v','sim/tb/tb_freeze_toggle.v'])
call('warp_scheduler','tb_warp_scheduler',['rtl/common/warp_scheduler.v','sim/tb/tb_warp_scheduler.v'])
call('freeze_capture','tb_freeze_capture',['rtl/common/async_fifo.v','rtl/mem/frame_writer.v','rtl/common/warp_scheduler.v','sim/tb/tb_freeze_capture.v'])
call('coord','tb_coord',['rtl/warp/coord_map.v','sim/tb/tb_coord.v'])
call('bilin','tb_bilin',['rtl/warp/bilinear_2x2.v','sim/tb/tb_bilin.v'])
call('tile','tb_warp_tile',warp+['sim/tb/tb_warp_tile.v'])
call('tile_fast','tb_warp_tile_fast',['rtl/warp/coord_map.v','rtl/warp/bilinear_2x2.v','rtl/warp/warp_tile_fast.v','sim/tb/tb_warp_tile_fast.v'])
call('stereo_fusion','tb_stereo_fusion',['rtl/warp/stereo_fusion.v','sim/tb/tb_stereo_fusion.v'])
call('stereo_controls','tb_stereo_controls',['rtl/common/stereo_controls.v','sim/tb/tb_stereo_controls.v'])
call('stereo_pair','tb_stereo_pair',['rtl/common/stereo_pair_select.v','sim/tb/tb_stereo_pair.v'])
call('burst_arb','tb_burst_arb',['rtl/mem/burst_arb2.v','sim/tb/tb_burst_arb.v'])
call('dual_dvp','tb_dual_dvp',['rtl/common/async_fifo.v','rtl/cam/dvp_capture.v','rtl/common/camera_select.v','sim/tb/tb_dual_dvp.v'])
call('camera_select','tb_camera_select',['rtl/common/camera_select.v','sim/tb/tb_camera_select.v'])
call('controls','tb_controls',['rtl/common/warp_controls.v','sim/tb/tb_controls.v'])
call('host','tb_host',['rtl/common/uart_rx.v','rtl/common/uart_tx.v','rtl/common/warp_config.v','rtl/common/warp_telemetry.v','sim/tb/tb_host.v'])
call('pclk_meter','tb_pclk_meter',['rtl/common/pclk_meter.v','sim/tb/tb_pclk_meter.v'])
call('focus','tb_focus_meter',['rtl/common/focus_meter.v','sim/tb/tb_focus_meter.v'])
call('gamma','tb_gamma',['rtl/common/adaptive_gamma.v','sim/tb/tb_gamma.v'])
call('gamma_capture','tb_gamma_capture',['rtl/common/adaptive_gamma.v','rtl/common/async_fifo.v','rtl/mem/frame_writer.v','sim/tb/tb_gamma_capture.v'])
call('metrics','tb_metrics',['rtl/common/video_metrics.v','rtl/video/metrics_osd.v','sim/tb/tb_metrics.v'])
call('fifo_full','tb_fifo_full',['rtl/common/async_fifo.v','sim/tb/tb_fifo_full.v'])
call('pack','tb_pack',['rtl/warp/out_pack.v','sim/tb/tb_pack.v'])
call('slots','tb_slots',['rtl/common/async_fifo.v','rtl/mem/frame_writer.v','sim/tb/tb_slots.v'])
call('frame_recovery','tb_frame_recovery',['rtl/common/async_fifo.v','rtl/mem/frame_writer.v','sim/tb/tb_frame_recovery.v'])
call('capture_overflow','tb_capture_overflow',['rtl/common/async_fifo.v','rtl/mem/frame_writer.v','sim/tb/tb_capture_overflow.v'])
call('cam_start','tb_cam_start',['rtl/cam/power_on_delay.v','rtl/cam/reg_config.v','rtl/cam/i2c_com.v','sim/tb/tb_cam_start.v'])
call('dvp','tb_dvp',['rtl/common/async_fifo.v','rtl/cam/dvp_capture.v','sim/tb/tb_dvp.v'])
call('display_retire','tb_display_retire',['rtl/common/async_fifo.v','rtl/mem/disp_reader.v','sim/tb/tb_display_retire.v'])
call('display','tb_display',['rtl/common/async_fifo.v','rtl/mem/disp_reader.v','rtl/ddr/sync_vg.v','sim/tb/tb_display.v'])
mem=['rtl/common/async_fifo.v','rtl/mem/axi_ddr_master.v','rtl/mem/mem_hub.v','rtl/mem/frame_writer.v','rtl/mem/disp_reader.v','sim/model/axi_mem_model.v','sim/tb/tb_mem.v']
call('mem','tb_mem',mem)
files=[str(f.relative_to(p)) for f in (p/'rtl/warp').glob('*.v') if f.name not in ['tile_fetch.v','line_ring.v']]+['sim/tb/tb_full.v']
cases=[(0,0)] if a.quick else [(0,0),(31.5,0),(90,0),(180,0),(0,-80)]
for roll,shift in cases:
 subprocess.run([sys.executable,str(p/'tools/gen_full_reference.py'),'--roll',str(roll),'--shift',str(shift)],check=True,env=env)
 name='full_'+str(roll).replace('.','p')+'_'+str(shift).replace('-','m')
 call(name,'tb_full',files)
 for f in ['frame_coef.vh','full_expect.hex']:shutil.copy2(p/'sim/out'/f,run/(name+'_'+f))
if not a.quick:
 subprocess.run([sys.executable,str(p/'tools/gen_full_reference.py'),'--roll','0','--shift','0'],check=True,env=env)
 call('full_stall','tb_full',['-DSTALL_OUTPUT']+files)
 for f in ['frame_coef.vh','full_expect.hex']:shutil.copy2(p/'sim/out'/f,run/('full_stall_'+f))
if not a.quick:
 subprocess.run([sys.executable,str(p/'tools/gen_full_reference.py'),'--raw'],check=True,env=env)
 call('full_raw','tb_full',files)
 for f in ['frame_coef.vh','full_expect.hex']:shutil.copy2(p/'sim/out'/f,run/('full_raw_'+f))
 call('full_repeat','tb_full',['-DREPEAT_FRAME']+files)
 for f in ['frame_coef.vh','full_expect.hex']:shutil.copy2(p/'sim/out'/f,run/('full_repeat_'+f))
 call('full_shared','tb_full',['-DSHARED_DDR','rtl/mem/mem_hub.v','sim/model/video_background.v']+files)
 for f in ['frame_coef.vh','full_expect.hex']:shutil.copy2(p/'sim/out'/f,run/('full_shared_'+f))
changed=[name for name,digest in manifest.items() if hashlib.sha256((p/name).read_bytes()).hexdigest()!=digest]
if changed:raise SystemExit('RTL changed during regression; rerun with stable sources: '+', '.join(changed))
(run/'summary.json').write_text(json.dumps({'passed':all(r['passed'] for r in results),'complete':True,'tests':results,'rtl_sha256':manifest},indent=2),encoding='utf-8')
print('ALL PASS' ,len(results),'tests; evidence:',run,flush=True)
