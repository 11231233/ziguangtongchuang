`timescale 1ns/1ps
`default_nettype none
// One coordinate and one 2x2 neighbourhood per cycle after pipeline fill.
// The packer reserves three packets for all coordinates/pixels in flight.
module warp_tile_stream #(parameter integer TILE=16,SRC_W=1280,SRC_H=720,CHECK_WINDOW=0)(
 input wire clk,rstn,start,input wire [15:0] tx,ty,u0,v0,
 input wire pixel_ready,
 input wire [6:0] window_width,window_height,
 output wire map_request,output wire [15:0] map_x,map_y,
 input wire map_valid,map_in_frame,input wire signed [15:0] map_ui,map_vi,
 input wire [7:0] map_uf,map_vf,
 output wire [5:0] x0,x1,y0,y1,
 input wire [15:0] p00,p01,p10,p11,
 output reg we,output reg [15:0] ox,oy,pix,output reg busy);
 localparam integer N=TILE*TILE;
 reg [15:0] issued,received,produced;
 assign map_request=busy && issued<N && pixel_ready;
 assign map_x=tx+(issued%TILE);assign map_y=ty+(issued/TILE);
 assign x0=map_ui-u0;assign y0=map_vi-v0;
 assign x1=(map_ui==SRC_W-1)?x0:x0+1'b1;
 assign y1=(map_vi==SRC_H-1)?y0:y0+1'b1;
 wire [16:0] neighbour_u=({1'b0,map_ui}-{1'b0,u0})+((map_ui==SRC_W-1)?17'd0:17'd1);
 wire [16:0] neighbour_v=({1'b0,map_vi}-{1'b0,v0})+((map_vi==SRC_H-1)?17'd0:17'd1);
 wire actual_window_ok=!CHECK_WINDOW || (window_width!=0 && window_height!=0 &&
  neighbour_u<{10'd0,window_width} && neighbour_v<{10'd0,window_height});
 wire good=actual_window_ok && map_in_frame && map_ui>=$signed({1'b0,u0}) && map_vi>=$signed({1'b0,v0}) &&
  ((map_ui-u0)<63 || map_ui==SRC_W-1) && ((map_vi-v0)<63 || map_vi==SRC_H-1);
 wire [15:0] rx=tx+(received%TILE),ry=ty+(received/TILE);
 reg v1,v2;reg [48:0] m1,m2;
 reg [32:0] t1,t2,t3,t4;wire bv;wire [15:0] bp;
 bilinear_2x2 interp(.clk(clk),.rstn(rstn),.valid_i(v2),
  .p00(p00),.p01(p01),.p10(p10),.p11(p11),.fu(m2[15:8]),.fv(m2[7:0]),.valid_o(bv),.rgb_o(bp));
 reg finish_pending;
 always @(posedge clk)begin
  if(!rstn)begin
   busy<=0;we<=0;ox<=0;oy<=0;pix<=0;issued<=0;received<=0;produced<=0;
   v1<=0;v2<=0;m1<=0;m2<=0;t1<=0;t2<=0;t3<=0;t4<=0;finish_pending<=0;
  end else begin
   we<=0;v1<=busy && map_valid && received<N;v2<=v1;
   m1<={good,rx,ry,map_uf,map_vf};m2<=m1;
   t1<=m2[48:16];t2<=t1;t3<=t2;t4<=t3;
   if(start&&!busy)begin busy<=1;issued<=0;received<=0;produced<=0;finish_pending<=0;end
   else if(busy)begin
    if(map_request)issued<=issued+1'b1;
    if(map_valid && received<N)received<=received+1'b1;
    if(bv)begin
     we<=1;ox<=t4[31:16];oy<=t4[15:0];pix<=t4[32]?bp:16'd0;
     produced<=produced+1'b1;if(produced==N-1)finish_pending<=1;
    end
    if(finish_pending)begin busy<=0;finish_pending<=0;end
   end
  end
 end
endmodule
`default_nettype wire
