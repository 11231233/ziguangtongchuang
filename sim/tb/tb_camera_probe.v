`timescale 1ns/1ps
module tb_camera_probe;
 reg clk=0,pclk=0,rst=0,vs=0,de=0,pvs=0;reg [15:0] word_i=0;
 always #5 clk=~clk;always #7 pclk=~pclk;
 wire [204:0] visible;
 camera_probe #(.WIDTH(32),.HEIGHT(4)) dut(.clk(clk),.rstn(rst),.vs(vs),.de(de),.word_i(word_i),.uart_status(16'hab12),
 .pix_clk(pclk),.pix_rstn(rst),.pix_vs(pvs),.visible(visible));
 function [15:0] bar(input integer n);begin case(n)
 0:bar=16'hffff;1:bar=16'h07ff;2:bar=16'hffe0;3:bar=16'h07e0;
 4:bar=16'hf81f;5:bar=16'h001f;6:bar=16'hf800;default:bar=0;
 endcase end endfunction
 task marker;begin @(negedge clk);de=0;vs=1;repeat(3)@(negedge clk);vs=0;end endtask
 task frame(input [15:0] mask,input integer words);integer n;begin
  for(n=0;n<words;n=n+1)begin @(negedge clk);de=1;word_i=bar((n%32)/4)&mask;end
  @(negedge clk);de=0;
 end endtask
 task boundary;begin repeat(8)@(negedge pclk);pvs=1;repeat(2)@(negedge pclk);pvs=0;repeat(8)@(negedge pclk);end endtask
 reg [204:0] held;integer n;
 initial begin
  repeat(5)@(negedge clk);rst=1;marker;boundary;repeat(6)@(negedge clk);
  frame(16'hffff,128);marker;repeat(10)@(negedge clk);held=dut.held;
  frame(16'hfbfb,128);marker;frame(16'hfbfb,128);marker;
  if(dut.held!==held)$fatal(1,"Mailbox overwritten before VS acknowledgement");
  boundary;
  if(!visible[204] || visible[187:168]!=128 || visible[167:160]!==8'hff || visible[203:188]!==16'hab12)
   $fatal(1,"Snapshot metadata/CDC");
  if(visible[143:128]!==16'hffff || visible[159:144]!==0)$fatal(1,"Full-bit OR/AND");
  for(n=0;n<8;n=n+1)if(visible[n*16+:16]!==bar(n))$fatal(1,"Bar sample %0d",n);
  repeat(6)@(negedge clk);frame(16'hfbfb,128);marker;boundary;
  if(!visible[204] || visible[143:128]!==16'hfbfb || visible[159:144]!==0)$fatal(1,"D2 stuck-low not visible");
  repeat(6)@(negedge clk);frame(16'hffff,110);marker;boundary;
  if(visible[204] || visible[187:168]!=110)$fatal(1,"Incomplete frame labeled valid");
  $display("CAMERA_PROBE PASS raw bar samples, D2 bit fault, frame count, truncated frame, independent clocks and VS-ack stable mailbox");$finish;
 end
 initial begin #100000;$fatal(1,"Probe timeout");end
endmodule
