`timescale 1ns/1ps
module tb_window_bounds;
 reg clk=0,rst=0,start=0;always #5 clk=~clk;
 reg [6:0] width=16,height=16;reg signed [15:0] u=0,v=0;
 wire req,busy,we;wire[15:0] mx,my,pix;reg mv=0;
 always @(posedge clk)mv<=req;
 warp_tile_stream #(.TILE(2),.SRC_W(64),.SRC_H(64),.CHECK_WINDOW(1)) dut(
  .clk(clk),.rstn(rst),.start(start),.tx(16'd0),.ty(16'd0),.u0(16'd0),.v0(16'd0),.pixel_ready(1'b1),
  .window_width(width),.window_height(height),.map_request(req),.map_x(mx),.map_y(my),
  .map_valid(mv),.map_in_frame(1'b1),.map_ui(u),.map_vi(v),.map_uf(8'd0),.map_vf(8'd0),
  .x0(),.x1(),.y0(),.y1(),.p00(16'hffff),.p01(16'hffff),.p10(16'hffff),.p11(16'hffff),.we(we),.ox(),.oy(),.pix(pix),.busy(busy));
 integer count=0;reg [15:0] expected;
 always @(posedge clk)if(we)begin if(pix!==expected)$fatal(1,"READ STALE WINDOW PIXEL got=%h expected=%h",pix,expected);count=count+1;end
 task run(input integer x,y,w,h,input [15:0] e);
  begin
   @(negedge clk);u=x;v=y;width=w;height=h;expected=e;count=0;start=1;
   @(negedge clk);start=0;wait(busy);wait(!busy);repeat(3)@(negedge clk);
   if(count!=4)$fatal(1,"WINDOW PIXEL COUNT %d",count);
  end
 endtask
 initial begin
  repeat(4)@(negedge clk);rst=1;
  run(20,5,16,16,0);run(5,20,16,16,0);run(15,5,16,16,0);
  run(5,15,16,16,0);run(5,5,16,16,16'hffff);run(63,63,64,64,16'hffff);run(0,0,0,16,0);
  $display("WINDOW_BOUNDS PASS actual fetched extents, neighbour checks, zero-size guard and duplicated source-edge samples");$finish;
 end
 initial begin #10000;$fatal(1,"WINDOW TIMEOUT");end
endmodule
