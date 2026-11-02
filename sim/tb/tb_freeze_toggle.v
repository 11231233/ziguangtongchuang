`timescale 1ns/1ps
module tb_freeze_toggle;
 reg clk=0,rstn=0,key_n=1,clear_i=0;always #5 clk=~clk;wire wanted;
 freeze_toggle #(.DEBOUNCE_CYCLES(3)) dut(.clk(clk),.rstn(rstn),.key_n(key_n),.clear_i(clear_i),.wanted(wanted));
 task tick;begin @(negedge clk);#1;end endtask
 initial begin
  repeat(4)tick;rstn=1;repeat(8)tick;
  key_n=0;tick;key_n=1;repeat(10)tick;if(wanted)$fatal(1,"BOUNCE");
  key_n=0;repeat(30)tick;if(!wanted)$fatal(1,"TOGGLE/HELD");
  clear_i=1;tick;clear_i=0;repeat(12)tick;if(wanted)$fatal(1,"CLEAR WHILE HELD");
  key_n=1;repeat(12)tick;key_n=0;repeat(12)tick;if(!wanted)$fatal(1,"REARM");
  key_n=1;repeat(12)tick;key_n=0;repeat(12)tick;if(wanted)$fatal(1,"RELEASE");
  rstn=0;repeat(3)tick;if(wanted)$fatal(1,"RESET");
  $display("FREEZE_TOGGLE PASS: debounce, held key, context clear and rearm");$finish;
 end
 initial begin #20000;$fatal(1,"TIMEOUT");end
endmodule
