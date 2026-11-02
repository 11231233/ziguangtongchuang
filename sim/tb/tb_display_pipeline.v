`timescale 1ns/1ps
module tb_display_pipeline;
 reg clk=0,rst=0,vs=0,hs=0,de=0;always #5 clk=~clk;
 reg [11:0] x=0,y=0;reg [15:0] pixel=0;
 wire [7:0] r,g,b;wire vo,ho,deo;
 top_pangu50 dut(.sys_clk(clk),.host_rx(1'b1),.key0(1'b1),.key1(1'b1),.key2(1'b1),.key3(1'b1),
  .key4(1'b1),.key5(1'b1),.key6(1'b1),.key7(1'b1),.cam_pclk(clk),.cam_vs(1'b0),.cam_hs(1'b0),.cam_d(8'd0),
  .r_out(r),.g_out(g),.b_out(b),.vs_out(vo),.hs_out(ho),.de_out(deo));
 wire [15:0] osd;wire overlay;
 metrics_osd #(.SINGLE_CAMERA(1)) reference_osd(.clk(clk),.rstn(rst),.vs(vs),.de(de),.key_n(1'b1),
  .camera_selected(1'b0),.fusion_enabled(1'b0),.fusion_used(1'b0),.frozen(1'b0),.format2(2'd0),.display_quality(2'd2),
  .probe(205'd0),.c2_status(19'd0),.c2_status_toggle(1'b0),.c2_phase(1'b0),.overlay_active(overlay),
  .x(x),.y(y),.pixel(pixel),.snapshot(86'd0),.snapshot_toggle(1'b0),.result(osd),.enabled());
 wire rv,rh,rd;wire [23:0] rgb;
 quality_display #(.DEFAULT_MODE(2),.MAX_MODE(3),.NATURAL_DETAIL(1)) reference_quality(.clk(clk),.rstn(rst),.vs(vs),.hs(hs),.de(de),.cycle_n(1'b1),
  .pixel(pixel),.osd_pixel(osd),.osd_overlay(overlay),.vs_o(rv),.hs_o(rh),.de_o(rd),.rgb_o(rgb),.active_mode());
 reg [26:0] reference_delay1=0,reference_delay2=0;
 always @(posedge clk)begin reference_delay1<={rv,rh,rd,rgb};reference_delay2<=reference_delay1;end
 integer n;
 initial begin
  force dut.ddr_clk=clk;force dut.clk_pix=clk;force dut.clk_25m=clk;
  force dut.ddr_init_done=rst;force dut.rstn_pix=rst;force dut.rstn_cap_ddr=rst;force dut.rstn_pclk=rst;
  force dut.cam_rstn_int=rst;force dut.cam_init_en=1'b0;
  force dut.vs_aligned=vs;force dut.hs_aligned=hs;force dut.de_aligned=de;
  force dut.x_aligned=x;force dut.y_aligned=y;force dut.fb_pix=pixel;
  force dut.metric_snapshot=86'd0;force dut.metric_toggle=1'b0;
  force dut.camera_status=19'd0;force dut.camera_status_toggle=1'b0;
  force dut.camera_probe_visible=205'd0;force dut.display_frozen=1'b0;
  repeat(8)@(negedge clk);rst=1;
  for(n=0;n<20000;n=n+1)begin
   @(negedge clk);x=n%240;y=(n/240)%300;
   pixel=(n*73)^16'h5ac3;de=n%19!=0;hs=n%101<4;vs=n%2048<5;
   @(posedge clk);#1;
   if(n>10 && {vo,ho,deo,r,g,b}!==reference_delay2)
    $fatal(1,"DISPLAY PIPELINE MISMATCH n=%d got=%h expected=%h",n,{vo,ho,deo,r,g,b},reference_delay2);
  end
  $display("DISPLAY_PIPELINE PASS 20000 Q2 image, OSD and HS/VS/DE samples match original chain plus one pixel cycle");$finish;
 end
 initial begin #300000;$fatal(1,"DISPLAY PIPELINE TIMEOUT");end
endmodule
