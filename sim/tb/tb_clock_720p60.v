`timescale 1ns/1ps
module tb_clock_720p60;
 reg sys=0;always #10 sys=~sys;
 wire ref75,cfg10,cam25,pix,lock0,lock1;
 pll main_pll(.clkin1(sys),.clkout0(ref75),.clkout1(cfg10),.clkout2(cam25),.pll_lock(lock0));
 pll_720p60 pixel_pll(.clkin1(ref75),.clkout0(pix),.clkout1(),.clkout2(),.pll_lock(lock1));
 realtime start_t,elapsed;
 initial begin
  // Vendor phase-delay model needs settling beyond LOCK. The real top holds
  // global reset for 16384 control clocks (1.6384ms), far longer than this.
  wait(lock0 && lock1);#50000;repeat(200)@(posedge pix);
  @(posedge pix);start_t=$realtime;repeat(1000)@(posedge pix);elapsed=$realtime-start_t;
  if(elapsed<13467.9 || elapsed>13468.2)$fatal(1,"Pixel frequency incorrect duration=%f",elapsed);
  $display("PIXEL_PLL measured 1000 periods ns=%f MHz=%f",elapsed,1000000.0/elapsed);
  @(posedge cfg10);start_t=$realtime;repeat(100)@(posedge cfg10);elapsed=$realtime-start_t;
  if(elapsed<9999.9 || elapsed>10000.1)$fatal(1,"Configuration clock changed %f",elapsed);
  @(posedge cam25);start_t=$realtime;repeat(100)@(posedge cam25);elapsed=$realtime-start_t;
  if(elapsed<3999.9 || elapsed>4000.1)$fatal(1,"Camera control clock changed %f",elapsed);
  if(!lock0 || !lock1)$fatal(1,"PLL lost lock");
  $display("CLOCK_720P60 PASS vendor PLL model 74.25MHz pixel and retained 10MHz/25MHz clocks");$finish;
 end
 initial begin #200000;$fatal(1,"PLL lock timeout");end
endmodule
