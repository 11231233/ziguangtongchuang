"""Independent ROM math and board-button RTL checks; no hardware opens."""
from pathlib import Path
import numpy as np,subprocess,sys,os,datetime,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'reports'/('key_angles_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'));out.mkdir()
rows=[]
for zoom,(a,c,f) in enumerate([(126,-80660,-45371),(101,-64528,-36297),(82,-52429,-29491)]):
 for angle in range(-180,180):
  t=np.deg2rad(angle);co=np.cos(t);si=np.sin(t)
  old=np.array([[a/65536,0,c/65536],[0,a/65536,f/65536],[0,0,1.]])
  rotate=np.array([[co,-si,640-co*640+si*360],[si,co,360-si*640-co*360],[0,0,1.]])
  matrix=old@rotate
  coeff=[int(np.rint(matrix[r,col]*(2**(24 if col<2 else 16)))) for r in range(2) for col in range(3)]
  n=abs(angle);bcd=((angle<0)<<12)|((n//100)<<8)|(((n//10)%10)<<4)|(n%10)
  packed=sum((v&0xffffffff)<<(32*(5-i)) for i,v in enumerate(coeff));rows.append((packed<<13)|bcd)
(out/'expected.hex').write_text('\n'.join(f'{v:052x}' for v in rows)+'\n')
tb=r'''
`timescale 1ns/1ps
module tb_key_angles;
reg clk=0,rstn=0,frame=0,zoom_n=1;always #5 clk=~clk;
reg[3:0]keys=15;wire signed[31:0] A,B,C,D,E,F,fx,fy,cx,cy,k1,k2;
wire en,toggle,restore;wire[1:0]strength,zoom;wire signed[9:0]angle;wire[12:0]bcd;
key_angle_controls #(.DEBOUNCE_CYCLES(3),.REPEAT_DELAY(60),.REPEAT_PERIOD(15),.RESET_HOLD(100)) dut(
.clk(clk),.rstn(rstn),.frame_start(frame),.key_n(keys),.zoom_n(zoom_n),
.A(A),.B(B),.C(C),.D(D),.E(E),.F(F),.fx(fx),.fy(fy),.cx(cx),.cy(cy),.k1(k1),.k2(k2),
.active_enabled(en),.active_strength(strength),.active_zoom(zoom),.active_angle(angle),.angle_bcd(bcd),.angle_toggle(toggle),.restore_defaults(restore));
reg[207:0]expected[0:1079];reg[191:0]before_coeff;integer n;reg[8:0]idx;reg[1:0]z;
task commit;begin repeat(6)@(negedge clk);frame=1;@(negedge clk);frame=0;end endtask
task tap(input integer bitno);begin keys[bitno]=0;repeat(12)@(negedge clk);keys[bitno]=1;repeat(12)@(negedge clk);end endtask
initial begin
 $readmemh("EXPECTED",expected);repeat(5)@(negedge clk);rstn=1;
 repeat(10)@(negedge clk);commit();
 if({A,B,C,D,E,F}!=={32'd32256,32'd0,-32'sd80660,32'd0,32'd32256,-32'sd45371} || angle!==0 || !en || strength!==2 || zoom!==0)$fatal(1,"Boot differs from original");
 before_coeff={A,B,C,D,E,F};tap(2);
 if(angle!==0 || {A,B,C,D,E,F}!==before_coeff)$fatal(1,"Angle changed outside frame boundary");
 commit();if(angle!==1 || bcd!==13'h001 || B>=0 || D<=0)$fatal(1,"Plus key or direction");
 tap(3);commit();if(angle!==0)$fatal(1,"Minus key");
 keys[2]=0;repeat(125)@(negedge clk);keys[2]=1;repeat(12)@(negedge clk);
 commit();if(angle<4)$fatal(1,"Hold repeat missing");
 keys[3:2]=0;repeat(24)@(negedge clk);commit();if(angle!==0)$fatal(1,"Chord zero");
 keys[2]=1;repeat(25)@(negedge clk);keys[3]=1;repeat(25)@(negedge clk);commit();if(angle!==0)$fatal(1,"Chord release generated angle");
 tap(0);tap(1);zoom_n=0;repeat(3)@(negedge clk);zoom_n=1;commit();
 if(en!==0 || strength!==3 || zoom!==1 || k1!==0)$fatal(1,"RAW/strength/zoom");
 keys[3:2]=0;repeat(125)@(negedge clk);keys[3:2]=3;repeat(20)@(negedge clk);commit();
 if(!en || strength!==2 || zoom!==0 || angle!==0 || k1!==-21061)$fatal(1,"Held chord reset");
 // Exhaust all settings, preserving the public output until each frame edge.
 for(n=0;n<1080;n=n+1)begin
  idx=n%360;z=n/360;before_coeff={A,B,C,D,E,F};
  force dut.wanted_angle=idx;force dut.wanted_zoom=z;
  repeat(5)@(negedge clk);
  if({A,B,C,D,E,F}!==before_coeff)$fatal(1,"Non-atomic coefficients");
  commit();
  if({A,B,C,D,E,F,bcd}!==expected[n][204:0] || angle!==$signed({1'b0,idx})-180 || zoom!==z)$fatal(1,"Setting %0d metadata/coeff mismatch",n);
 end
 release dut.wanted_angle;release dut.wanted_zoom;
 force dut.wanted_angle=9'd359;repeat(6)@(negedge clk);release dut.wanted_angle;tap(2);commit();if(angle!==-180)$fatal(1,"Positive wrap");
 tap(3);commit();if(angle!==179)$fatal(1,"Negative wrap");
 $display("KEY_ANGLES PASS: original boot, signed direction, repeat, chord/release, reset, RAW/strength/zoom, 1080 exact settings, wrap and frame atomicity");$finish;
end
initial begin #1000000;$fatal(1,"Timeout");end
endmodule
'''
tb=tb.replace('EXPECTED',(out/'expected.hex').as_posix());(out/'tb.v').write_text(tb)
env=os.environ.copy();env.update(PYTHONIOENCODING='utf-8',PATHEXT='.COM;.EXE;.BAT;.CMD',COMSPEC=r'C:\Windows\System32\cmd.exe')
files=[ROOT/'rtl/common/key_angle_controls.v',ROOT/'rtl/common/key_angle_rom.v',out/'tb.v']
binary=out/'test.vvp'
r=subprocess.run(['D:/iverilog/bin/iverilog.exe','-g2012','-s','tb_key_angles','-o',str(binary),*[str(p) for p in files]],env=env,cwd=ROOT,capture_output=True,text=True)
(out/'compile.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stderr
r=subprocess.run(['D:/iverilog/bin/vvp.exe',str(binary)],env=env,cwd=ROOT,capture_output=True,text=True,timeout=60)
(out/'test.log').write_text(r.stdout+r.stderr);ok=r.returncode==0 and 'KEY_ANGLES PASS' in r.stdout
result=dict(passed=ok,hardware_tested=False,settings_compared=1080,source_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files[:2]})
(out/'result.json').write_text(json.dumps(result,indent=2));print(r.stdout+r.stderr);print(out)
raise SystemExit(0 if ok else 1)
