`timescale 1ns/1ps
module tb_pclk_meter;
 reg ref_clk=0,source_clk=0,rstn=0,run_source=1;
 always #5 ref_clk=~ref_clk;
 always #7 if(run_source)source_clk=~source_clk;else source_clk=0;
 wire [15:0] slow_bcd,fast_bcd;
 pclk_meter #(.REF_HZ(1000),.PRESCALE(7)) slow(.ref_clk(ref_clk),.source_clk(source_clk),.rstn(rstn),.rate_bcd(slow_bcd));
 pclk_meter #(.REF_HZ(1000),.PRESCALE(1)) fast(.ref_clk(ref_clk),.source_clk(source_clk),.rstn(rstn),.rate_bcd(fast_bcd));
 function integer decimal(input [15:0] bcd);
  begin
   if(bcd[15:12]>9||bcd[11:8]>9||bcd[7:4]>9||bcd[3:0]>9)$fatal(1,"INVALID BCD");
   decimal=bcd[15:12]*1000+bcd[11:8]*100+bcd[7:4]*10+bcd[3:0];
  end
 endfunction
 integer i;reg [15:0] previous_source;reg wrapped=0;
 initial begin
  repeat(5)@(negedge ref_clk);rstn=1;
  repeat(1200)@(negedge ref_clk);previous_source=fast.source_count;
  for(i=0;i<96;i=i+1)begin
   repeat(1020)@(negedge ref_clk);
   if(decimal(slow_bcd)<101||decimal(slow_bcd)>103)$fatal(1,"PRESCALED RATE %h",slow_bcd);
   if(decimal(fast_bcd)<713||decimal(fast_bcd)>716)$fatal(1,"RATE OR COUNTER WRAP %h",fast_bcd);
   if(fast.source_count<previous_source)wrapped=1;
   previous_source=fast.source_count;
  end
  if(!wrapped)$fatal(1,"WRAP NOT EXERCISED");
  run_source=0;repeat(2500)@(negedge ref_clk);
  if(slow_bcd!==0||fast_bcd!==0)$fatal(1,"STOPPED CLOCK NOT ZERO");
  rstn=0;repeat(5)@(negedge ref_clk);rstn=1;
  repeat(1200)@(negedge ref_clk);
  if(slow_bcd!==0||fast_bcd!==0)$fatal(1,"RESET WHILE SOURCE STOPPED");
  run_source=1;repeat(2500)@(negedge ref_clk);
  if(decimal(slow_bcd)<101||decimal(slow_bcd)>103)$fatal(1,"RESTART RATE");
  $display("PCLK_METER PASS: independent clocks, prescaler, BCD, Gray-counter wrap, stopped clock, reset and restart");$finish;
 end
 initial begin #2000000;$fatal(1,"PCLK METER TIMEOUT");end
endmodule
