`timescale 1ns/1ps
module tb_quality_controls;
 reg clk=0,rstn=0,key_n=1,vs=0,de=1;always #5 clk=~clk;
 wire short_n,long_n;wire [1:0] mode;wire [23:0] rgb;wire [15:0] osd_pixel;
 wire overlay,enabled;reg [11:0] x=48,y=128;
 key_short_long #(.DEBOUNCE_CYCLES(3),.LONG_CYCLES(30),.PULSE_CYCLES(10)) key(
  .clk(clk),.rstn(rstn),.key_n(key_n),.short_n(short_n),.long_n(long_n));
 metrics_osd #(.DEBOUNCE_CYCLES(3)) osd(.clk(clk),.rstn(rstn),.vs(vs),.de(de),.key_n(short_n),
  .camera_selected(1'b0),.fusion_enabled(1'b0),.fusion_used(1'b0),.frozen(1'b1),
  .format2(2'd2),.display_quality(mode),.x(x),.y(y),.pixel(16'h8410),
  .snapshot(86'd0),.snapshot_toggle(1'b0),.result(osd_pixel),.enabled(enabled),.overlay_active(overlay));
 quality_display #(.DEFAULT_MODE(2)) display(.clk(clk),.rstn(rstn),.vs(vs),.hs(1'b0),.de(de),.cycle_n(long_n),
  .pixel(16'h8410),.osd_pixel(osd_pixel),.osd_overlay(overlay),.active_mode(mode),
  .vs_o(),.hs_o(),.de_o(),.rgb_o(rgb));
 task frame;begin
  @(negedge clk);de=0;vs=1;repeat(3)@(negedge clk);vs=0;de=1;repeat(3)@(negedge clk);
 end endtask
 task short_press;begin key_n=0;repeat(12)@(negedge clk);key_n=1;repeat(22)@(negedge clk);end endtask
 task long_press;begin key_n=0;repeat(100)@(negedge clk);key_n=1;repeat(22)@(negedge clk);end endtask
 initial begin
  repeat(4)@(negedge clk);rstn=1;frame;
  if(mode!==2 || !enabled || osd.character!=="2")$fatal(1,"DEFAULT Q2 LABEL");
  short_press;
  if(!enabled || mode!==2)$fatal(1,"SHORT BEFORE VS");frame;
  if(enabled || mode!==2)$fatal(1,"SHORT OSD ONLY");
  long_press;
  if(mode!==2)$fatal(1,"MIDFRAME QUALITY CHANGE");frame;
  if(mode!==0 || enabled || osd.character!=="0")$fatal(1,"LONG Q0 ONLY");
  long_press;frame;if(mode!==1 || enabled)$fatal(1,"LONG Q1 CYCLE");
  long_press;frame;if(mode!==2 || enabled)$fatal(1,"LONG Q2 CYCLE");
  short_press;frame;
  if(!enabled || mode!==2)$fatal(1,"RESTORE OSD");
  // Q-label extends the box by one row; background outside is never covered.
  x=16;y=128;#1;if(!overlay || osd.character!=="Q")$fatal(1,"QUALITY ROW");
  x=210;#1;if(overlay)$fatal(1,"OVERLAY LEAK");
  $display("QUALITY_CONTROLS PASS short OSD only, held long once, Q2 Q0 Q1 cycle, VS atomicity and label");$finish;
 end
endmodule
