"""Check effective sensor registers and ACK/readback failure at 84 MHz profile."""
from pathlib import Path
import hashlib
import json
import re
from verify import test

root=Path(__file__).resolve().parents[1]
files=['rtl/cam/ov5640_reg_rom.v','rtl/cam/sccb_checked_master.v',
       'rtl/cam/ov5640_checked_config.v','sim/model/sccb_sensor_model.v','sim/tb/tb_fps30_checked.v']
assert test('fps30_checked','tb_fps30_checked',files)
assert test('fps30_rom','tb_fps30_rom',['rtl/cam/ov5640_reg_rom.v','sim/tb/tb_fps30_rom.v'])
regs={}
for word in re.findall(r'^REG ([0-9a-fA-F]{6})$',(root/'sim/out/fps30_rom.log').read_text(),re.M):
    value=int(word,16);regs[value>>8]=value&255
assert regs[0x3035]==0x21 and regs[0x3036]==0x69
assert regs[0x4300]==0x60 and regs[0x501f]==1
assert [regs[a] for a in [0x3a09,0x3a0b,0x3a0e,0x3a0d]]==[0xde,0xb8,3,4]
width=regs[0x3808]*256+regs[0x3809];height=regs[0x380a]*256+regs[0x380b]
hts=regs[0x380c]*256+regs[0x380d];vts=regs[0x380e]*256+regs[0x380f]
assert (width,height)==(1280,720)
vco=24*regs[0x3036]/(regs[0x3037]&15)
sysclk=vco/(regs[0x3035]>>4)/(((regs[0x3037]>>4)&1)+1)*2/((regs[0x3034]&15)//2)/(2**(regs[0x3108]&3))
pclk=2*sysclk;fps=pclk*1e6/(2*hts*vts)
assert abs(pclk-84)<.001 and 29.9<fps<30.1
top=(root/'rtl/top/top_pangu50.v').read_text(encoding='utf-8')
assert "ov5640_checked_config #(.PLL_MULTIPLIER(8'h69),.VERIFY_PLL(1),.IMAGE_PROFILE(1)) u_cam_cfg" in top
timing=(root/'constr/timing.fdc').read_text(encoding='utf-8')
assert 'create_clock -name cam_pclk -period 11.905' in timing
report=dict(passed=True,simulation_only=True,physical_high_speed_tested=False,
    camera_format='RGB565, DVP 8-bit bus, two bytes per pixel',
    width=width,height=height,hts=hts,vts=vts,vco_mhz=vco,
    theoretical_pclk_mhz=pclk,theoretical_sensor_fps=fps,
    active_pixel_payload_mbytes_per_second=width*height*2*fps/1e6,
    critical_pll_readback_gates_capture=True,bad_pll_readback_latches_fault=True,
    source_sha256={f:hashlib.sha256((root/f).read_bytes()).hexdigest() for f in files},
    registers={f'{a:04x}':f'{v:02x}' for a,v in sorted(regs.items())})
(root/'reports/fps30_test.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ['registers','source_sha256']},indent=2))

