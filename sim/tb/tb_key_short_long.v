`timescale 1ns/1ps
module tb_key_short_long;
 reg clk=0,rstn=0,key_n=1,mode_n=1,vs=0,de=0;always #5 clk=~clk;
 wire sn,ln;wire [1:0] mode,fmt;wire en;wire [1:0] test_mode;
 key_short_long #(.DEBOUNCE_CYCLES(3),.LONG_CYCLES(40),.PULSE_CYCLES(16)) keys(.clk(clk),.rstn(rstn),.key_n(key_n),.short_n(sn),.long_n(ln));
 stereo_controls #(.DEBOUNCE_CYCLES(3),.DEFAULT_MODE(1)) ctl(.clk(clk),.rstn(rstn),.key_mode_n(mode_n),.key_format_n(sn),.mode(mode),.format2(fmt));
 adaptive_gamma #(.WIDTH(8),.HEIGHT(4),.DEBOUNCE_CYCLES(3)) gamma(.clk(clk),.rstn(rstn),.vs(vs),.de(de),.pixel(16'h2104),.key_n(ln),.test_key_n(1'b1),.active_enabled(en),.active_test_mode(test_mode));
 integer ns=0,nl=0;reg ps=1,pl=1;
 always @(posedge clk)begin
  if(rstn)begin if(ps&&!sn)ns=ns+1;if(pl&&!ln)nl=nl+1;end
  ps=sn;pl=ln;
 end
 task tick;begin @(negedge clk);#1;end endtask
 task mark;begin vs=1;tick;vs=0;repeat(3)tick;end endtask
 initial begin
  repeat(4)tick;rstn=1;repeat(8)tick;
  if(mode!=1||fmt!=2||en||test_mode)$fatal(1,"START C1/G0/T0");
  key_n=0;tick;key_n=1;repeat(12)tick;if(ns||nl)$fatal(1,"BOUNCE");
  key_n=0;repeat(18)tick;if(fmt!=2)$fatal(1,"SHORT CHANGED BEFORE RELEASE");
  key_n=1;repeat(32)tick;if(fmt!=3||ns!=1||nl||en)$fatal(1,"SHORT ACTION");
  key_n=0;repeat(110)tick;
  if(nl!=1||ns!=1||fmt!=3||en)$fatal(1,"LONG REPEATED OR COMMITTED MIDFRAME");
  mark;if(!en||test_mode)$fatal(1,"NATURAL GAMMA NOT ENABLED");
  key_n=1;repeat(35)tick;if(ns!=1||fmt!=3)$fatal(1,"LONG RELEASE CHANGED FORMAT");
  key_n=0;repeat(70)tick;mark;key_n=1;repeat(35)tick;
  if(en||test_mode||nl!=2||ns!=1||fmt!=3)$fatal(1,"LONG BYPASS RESTORE");
  key_n=0;repeat(18)tick;key_n=1;repeat(35)tick;
  if(fmt!=0||ns!=2||nl!=2)$fatal(1,"SHORT AFTER LONG");
  rstn=0;repeat(4)tick;if(!sn||!ln||mode!=1||fmt!=2||en)$fatal(1,"RESET");
  $display("KEY_SHORT_LONG PASS: C1 default, debounce, short-release format, held natural Gamma once at VS, long-release isolation and reset");$finish;
 end
 initial begin #100000;$fatal(1,"KEY TIMEOUT");end
endmodule
