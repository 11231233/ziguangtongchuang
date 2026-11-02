from pathlib import Path
from fractions import Fraction
import hashlib,json,subprocess,re
from verify import env,test
p=Path(__file__).resolve().parents[1];out=p/'sim/out';out.mkdir(exist_ok=True)
model=Path('D:/PDS/arch/vendor/pango/verilog/simulation/GTP_PLL_E3.v')
files=['rtl/ip/pll/pll.v','rtl/ip/pll/pll_720p60.v','sim/tb/tb_clock_720p60.v']
r=subprocess.run(['D:/iverilog/bin/iverilog.exe','-g2012','-s','tb_clock_720p60','-o',str(out/'clock_720p60.vvp')]+[str(p/f) for f in files]+[str(model)],cwd=p,env=env,text=True,capture_output=True)
(out/'clock_720p60_compile.log').write_text(r.stdout+r.stderr,encoding='utf-8')
if r.returncode:raise SystemExit(r.stdout+r.stderr)
r=subprocess.run(['D:/iverilog/bin/vvp.exe',str(out/'clock_720p60.vvp')],cwd=p,env=env,text=True,capture_output=True,timeout=60)
(out/'clock_720p60.log').write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr)
ok=r.returncode==0 and 'CLOCK_720P60 PASS' in r.stdout and not re.search(r'error:|illegal',r.stdout,re.I)
need_sources=files+['rtl/ddr/sync_vg.v','rtl/top/top_pangu50.v','rtl/video/metrics_osd.v','constr/timing.fdc','sim/tb/tb_raster_720p60.v']
ok = test('raster_720p60','tb_raster_720p60',['rtl/ddr/sync_vg.v','sim/tb/tb_raster_720p60.v'],timeout=180) and ok
pixel=Fraction(50_000_000*30,2*10)*Fraction(99,10*10)
assert pixel==74_250_000 and pixel/(1650*750)==60
top=(p/'rtl/top/top_pangu50.v').read_text(encoding='utf-8')
assert 'if (!locked || !pixel_locked)' in top and 'PIXEL_HZ=74250000' in top
assert '.DEBOUNCE_CYCLES(PIXEL_HZ/100),.LONG_CYCLES(PIXEL_HZ),.PULSE_CYCLES(PIXEL_HZ/50)' in top
(p/'reports/clock_720p60_test.json').write_text(json.dumps({'passed':ok,'simulation_only':True,'vendor_PLL_model_used':True,'vendor_PLL_model_sha256':hashlib.sha256(model.read_bytes()).hexdigest(),'nominal_pixel_hz':int(pixel),'horizontal_total':1650,'vertical_total':750,'nominal_HDMI_refresh_hz':60,'physical_frequency_measured':False,'source_sha256':{f:hashlib.sha256((p/f).read_bytes()).hexdigest() for f in need_sources}},indent=2),encoding='utf-8')
raise SystemExit(0 if ok else 1)
