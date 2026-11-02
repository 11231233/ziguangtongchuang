`timescale 1ns/1ps
module tb_stereo_controls;
reg clk=0,rstn=0,k6=1,k4=1;always #5 clk=~clk;wire[1:0]mode,format2;
stereo_controls #(.DEBOUNCE_CYCLES(3)) dut(.clk(clk),.rstn(rstn),.key_mode_n(k6),.key_format_n(k4),.mode(mode),.format2(format2));
task tick;begin @(negedge clk);#1;end endtask
task press6;begin k6=0;repeat(15)tick;k6=1;repeat(12)tick;end endtask
task press4;begin k4=0;repeat(15)tick;k4=1;repeat(12)tick;end endtask
initial begin repeat(4)tick;rstn=1;repeat(3)tick;if(mode!=0||format2!=2)$fatal(1,"DEFAULT");
 k6=0;tick;k6=1;repeat(10)tick;if(mode!=0)$fatal(1,"BOUNCE");
 press6;if(mode!=1)$fatal(1,"CAM1");press6;if(mode!=2)$fatal(1,"CAM2");press6;if(mode!=0)$fatal(1,"FUSION WRAP");
 press4;if(format2!=3)$fatal(1,"FORMAT3");press4;if(format2!=0)$fatal(1,"FORMAT WRAP");press4;press4;if(format2!=2)$fatal(1,"FORMAT2");
 k6=0;repeat(50)tick;if(mode!=1)$fatal(1,"HELD KEY REPEATED");
 $display("STEREO_CONTROLS PASS: default fusion / RGB565BE, mode and format wrap, bounce and held key");$finish;
end
initial begin #100000;$fatal(1,"CONTROLS TIMEOUT");end
endmodule
