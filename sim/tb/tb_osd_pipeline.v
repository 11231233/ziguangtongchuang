`timescale 1ns/1ps
module tb_osd_pipeline;
 reg clk=0,rstn=0,vs=0,de=0;always #5 clk=~clk;
 reg [11:0] x=0,y=0;reg [15:0] pixel=0;
 reg [85:0] snapshot=86'h123456789abcdef1234567;
 wire [15:0] original,pipelined;wire original_box,pipelined_box;
 metrics_osd #(.SINGLE_CAMERA(1)) reference(
  .clk(clk),.rstn(rstn),.vs(vs),.de(de),.key_n(1'b1),.camera_selected(1'b0),
  .fusion_enabled(1'b0),.fusion_used(1'b0),.frozen(1'b0),.format2(2'd0),.display_quality(2'd2),
  .probe(205'h1abcde0123456789abcdef13572468fbfb0000ffabcde1234),
  .c2_status(19'h5a5a5),.c2_status_toggle(1'b1),.c2_phase(1'b0),
  .overlay_active(original_box),.x(x),.y(y),.pixel(pixel),
  .snapshot(snapshot),.snapshot_toggle(1'b1),.result(original),.enabled());
 metrics_osd #(.SINGLE_CAMERA(1),.PIPELINE_FONT(1)) candidate(
  .clk(clk),.rstn(rstn),.vs(vs),.de(de),.key_n(1'b1),.camera_selected(1'b0),
  .fusion_enabled(1'b0),.fusion_used(1'b0),.frozen(1'b0),.format2(2'd0),.display_quality(2'd2),
  .probe(205'h1abcde0123456789abcdef13572468fbfb0000ffabcde1234),
  .c2_status(19'h5a5a5),.c2_status_toggle(1'b1),.c2_phase(1'b0),
  .overlay_active(pipelined_box),.x(x),.y(y),.pixel(pixel),
  .snapshot(snapshot),.snapshot_toggle(1'b1),.result(pipelined),.enabled());
 integer i,j,count=0;reg [15:0] expected;reg expected_box;
 initial begin
  repeat(4)@(negedge clk);rstn=1;repeat(8)@(negedge clk);
  vs=1;repeat(3)@(negedge clk);vs=0;repeat(3)@(negedge clk);
  for(j=0;j<300;j=j+1)for(i=0;i<224;i=i+1)begin
   @(negedge clk);x=i;y=j;de=(i%17!=0);pixel=(i*59+j*31)^16'ha53c;
   #1;expected=original;expected_box=original_box;
   @(posedge clk);#1;
   if(pipelined!==expected || pipelined_box!==expected_box)
    $fatal(1,"OSD PIPELINE MISMATCH x=%d y=%d got=%h expected=%h",x,y,pipelined,expected);
   count=count+1;
  end
  rstn=0;@(posedge clk);#1;if(pipelined_box!==0 || pipelined!==0)$fatal(1,"OSD PIPELINE RESET");
  $display("OSD_PIPELINE PASS %0d points, all glyph rows, blanking, bounds, exact image and overlay alignment",count);$finish;
 end
 initial begin #2000000;$fatal(1,"OSD PIPELINE TIMEOUT");end
endmodule
