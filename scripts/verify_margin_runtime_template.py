"""Test generated real-time control with a SYNTHETIC model and certificate=0."""
from pathlib import Path
import datetime,subprocess,sys,json,os,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'scripts'))
from test_margin_calibration import test_model
from prepare_margin_runtime import render_controls,packed,_write_project
from margin_calibration import coefficients
out=ROOT/'reports'/('runtime_template_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'));out.mkdir()
model=test_model();model.update(p1=.001,p2=-.002)
(out/'synthetic_model.json').write_text(json.dumps(model));(out/'synthetic_validation.json').write_text(json.dumps(dict(synthetic_test_data=True)))
project=out/'SYNTHETIC_NOT_FOR_HARDWARE';record=_write_project(model,out/'synthetic_model.json',out/'synthetic_validation.json',project,True)
assert not record['certified_real_model']
source=project/'rtl/common/margin_runtime_controls.v'
expected=[packed(coefficients(model,angle,raw)) for raw in (False,True) for angle in range(-20,21)]
(out/'expected.hex').write_text('\n'.join(f'{v:0112x}' for v in expected)+'\n')
tb=r'''
`timescale 1ns/1ps
module tb_runtime;
reg clk=0,rstn=0,frame=0;always #5 clk=~clk;reg[3:0]keys=15;
wire[447:0]coeff;wire enabled,toggle,certified;wire signed[9:0]angle;wire[12:0]bcd;
margin_runtime_controls #(.DEBOUNCE(3),.REPEAT_DELAY(20),.REPEAT_PERIOD(3),.RESET_HOLD(40)) dut(
.clk(clk),.rstn(rstn),.frame_start(frame),.key_n(keys),.coeff(coeff),.active_enabled(enabled),.active_angle(angle),.angle_bcd(bcd),.angle_toggle(toggle),.certified(certified));
reg[447:0]expected[0:81],previous;reg[5:0]idx;integer n;
task commit;begin repeat(5)@(negedge clk);frame=1;@(negedge clk);frame=0;end endtask
initial begin
 $readmemh("EXPECTED",expected);repeat(5)@(negedge clk);rstn=1;repeat(6)@(negedge clk);
 if(certified!==0)$fatal(1,"Synthetic model became hardware-certified");
 for(n=0;n<41;n=n+1)begin
  idx=n;previous=coeff;force dut.wanted_index=idx;repeat(5)@(negedge clk);
  if(coeff!==previous)$fatal(1,"Mid-frame parameter change");
  commit();if(coeff!==expected[n] || angle!==n-20)$fatal(1,"Corrected ROM setting %0d",n);
 end
 release dut.wanted_index;keys[0]=0;repeat(12)@(negedge clk);keys[0]=1;repeat(12)@(negedge clk);commit();
 if(enabled!==0 || coeff!==expected[81] || angle!==20)$fatal(1,"RAW changes angle/focal or retains distortion");
 keys[2]=0;repeat(130)@(negedge clk);keys[2]=1;repeat(15)@(negedge clk);commit();if(angle!==20)$fatal(1,"Exceeded +20");
 keys[3:2]=0;repeat(70)@(negedge clk);keys[2]=1;repeat(15)@(negedge clk);keys[3]=1;repeat(15)@(negedge clk);commit();
 if(angle!==0 || !enabled || coeff!==expected[20])$fatal(1,"Geometry reset");
 keys[3]=0;repeat(130)@(negedge clk);keys[3]=1;repeat(15)@(negedge clk);commit();if(angle!==-20)$fatal(1,"Exceeded -20");
 $display("RUNTIME_TEMPLATE PASS 41 COR settings, fixed camera, p1/p2, RAW isolation, +/-20 clamp, chord reset, frame-atomic commit and synthetic certificate blocked");$finish;
end
initial begin #1000000;$fatal(1,"Timeout");end
endmodule
'''.replace('EXPECTED',(out/'expected.hex').as_posix())
(out/'tb.v').write_text(tb)
env=os.environ.copy();env.update(PATHEXT='.COM;.EXE;.BAT;.CMD',COMSPEC=r'C:\Windows\System32\cmd.exe')
binary=out/'test.vvp';r=subprocess.run(['D:/iverilog/bin/iverilog.exe','-g2012','-s','tb_runtime','-o',str(binary),str(source),str(out/'tb.v')],env=env,cwd=ROOT,capture_output=True,text=True)
(out/'compile.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stderr
r=subprocess.run(['D:/iverilog/bin/vvp.exe',str(binary)],env=env,cwd=ROOT,capture_output=True,text=True,timeout=60)
(out/'test.log').write_text(r.stdout+r.stderr);assert r.returncode==0 and 'RUNTIME_TEMPLATE PASS' in r.stdout,r.stdout+r.stderr
gate=r'''
`timescale 1ns/1ps
module tb_gate;
reg clk=0,rstn=0;always #5 clk=~clk;
top_pangu50 dut(.sys_clk(clk),.host_rx(1'b1),.key0(1'b1),.key1(1'b1),.key2(1'b1),.key3(1'b1),.key4(1'b1),.key5(1'b1),.key6(1'b1),.key7(1'b1),.cam_pclk(clk),.cam_hs(1'b0),.cam_vs(1'b0),.cam_d(8'd0));
initial begin
 force dut.ddr_clk=clk;force dut.clk_pix=clk;force dut.ddr_init_done=rstn;force dut.rstn_pix=rstn;
 force dut.cam_cfg_done=1'b1;force dut.cam_fault=1'b0;force dut.fw_frame_valid=1'b1;force dut.fw_frame_seq=32'd42;
 repeat(6)@(negedge clk);rstn=1;repeat(40)@(negedge clk);
 if(dut.runtime_certified!==0 || dut.runtime_capture_ok!==0 || dut.accept_source!==0)$fatal(1,"Uncertified synthetic project accepts live frames");
 if(dut.u_warp_frame.V_ACT!=720 || dut.u_warp_frame.SRC_W!=1296 || dut.u_warp_frame.SRC_STRIDE!=768)$fatal(1,"Runtime source/output geometry changed");
 $display("RUNTIME_GATE PASS uncertified model cannot produce corrected frames; true 1296x972 source and fixed 720P output wired");$finish;
end
endmodule
'''
(out/'gate_tb.v').write_text(gate)
files=[project/'rtl/top/top_pangu50.v']
for folder in ['common','video','cam','hdmi','mem']:files += [p for p in (project/'rtl'/folder).glob('*.v') if p.name!='cmos_8_16bit.v']
files += [project/'rtl/ddr/sync_vg.v']+[p for p in (project/'rtl/warp').glob('*.v') if p.name not in ['tile_fetch.v','line_ring.v']]+[out/'gate_tb.v']
r=subprocess.run(['D:/iverilog/bin/iverilog.exe','-g2012','-i','-s','tb_gate','-o',str(out/'gate.vvp'),*[str(p) for p in files]],env=env,cwd=ROOT,capture_output=True,text=True)
(out/'gate_compile.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stderr
r=subprocess.run(['D:/iverilog/bin/vvp.exe',str(out/'gate.vvp')],env=env,cwd=ROOT,capture_output=True,text=True,timeout=60)
(out/'gate.log').write_text(r.stdout+r.stderr);assert r.returncode==0 and 'RUNTIME_GATE PASS' in r.stdout,r.stdout+r.stderr
result=dict(passed=True,synthetic_test_only=True,physical_calibration_complete=False,hardware_tested=False,
  checks=['41 COR angle words','RAW zero distortion','fixed output K','clamp +/-20','frame atomicity','source geometry wiring','uncertified gate'])
(out/'result.json').write_text(json.dumps(result,indent=2));print((out/'test.log').read_text()+r.stdout);print(out)
