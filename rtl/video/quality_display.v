`timescale 1ns/1ps
`default_nettype none
// Display experiment only. Sensor, geometry, frame stores and CALC are unchanged.
// Q0 legacy zero extension; Q1 full-range bit replication; Q2 Q1 + bounded
// horizontal luma edge enhancement. This does not recover lost sensor detail.
// Exactly one pixel of latency in every mode, including blanking and sync.
module quality_display #(parameter integer DEFAULT_MODE=1,
 parameter integer MAX_MODE=2, NATURAL_DETAIL=0)(
 input wire clk,rstn,vs,hs,de,cycle_n,
 input wire [15:0] pixel,osd_pixel,input wire osd_overlay,
 output reg vs_o,hs_o,de_o,output reg [23:0] rgb_o,
 output reg [1:0] active_mode);
 reg [1:0] wanted;
 reg cycle_q,vs_q,hs_q,de_q,de_qq,overlay_q;
 reg [15:0] center_pixel,center_osd;
 reg [7:0] center_y,left_y;
 wire [7:0] rr={pixel[15:11],pixel[15:13]};
 wire [7:0] gg={pixel[10:5],pixel[10:9]};
 wire [7:0] bb={pixel[4:0],pixel[4:2]};
 wire [9:0] weighted={2'd0,rr}+{1'd0,gg,1'b0}+{2'd0,bb};
 wire [7:0] current_y=weighted[9:2];
 wire signed [10:0] edge_value=$signed({2'b00,center_y,1'b0})-
    $signed({3'b000,left_y})-$signed({3'b000,current_y});
 wire signed [10:0] scaled_edge=edge_value>>>3;
 wire signed [10:0] bounded_edge=(scaled_edge>11'sd8)?11'sd8:
    (scaled_edge< -11'sd8)?-11'sd8:scaled_edge;
 // Natural Q2 suppresses weak high-frequency noise and avoids pushing dark or
 // near-white pixels. Q3 retains the previous stronger Q2 response.
 wire signed [10:0] soft_edge=edge_value>>>4;
 wire signed [10:0] soft_bound=(soft_edge>11'sd4)?11'sd4:
    (soft_edge< -11'sd4)?-11'sd4:soft_edge;
 wire natural_gate=(edge_value>11'sd8 || edge_value< -11'sd8) && center_y>=24 && center_y<=224;
 wire signed [10:0] enhancement=(NATURAL_DETAIL && active_mode==2)?
    (natural_gate?soft_bound:11'sd0):bounded_edge;
 wire signed [10:0] delta=((active_mode==2 || active_mode==3) && de_q && de_qq && de && !overlay_q)?enhancement:11'sd0;
 wire [15:0] selected=overlay_q?center_osd:center_pixel;
 wire [7:0] r8={selected[15:11],selected[15:13]};
 wire [7:0] g8={selected[10:5],selected[10:9]};
 wire [7:0] b8={selected[4:0],selected[4:2]};
 function [7:0] add_clip(input [7:0] value,input signed [10:0] change);
  reg signed [11:0] sum;
  begin
   sum=$signed({4'd0,value})+change;
   if(sum<0)add_clip=0;else if(sum>255)add_clip=255;else add_clip=sum[7:0];
  end
 endfunction
 always @(posedge clk)begin
  if(!rstn)begin
   wanted<=DEFAULT_MODE;active_mode<=DEFAULT_MODE;cycle_q<=1;vs_q<=0;hs_q<=0;de_q<=0;de_qq<=0;
   overlay_q<=0;center_pixel<=0;center_osd<=0;center_y<=0;left_y<=0;
   vs_o<=0;hs_o<=0;de_o<=0;rgb_o<=0;
  end else begin
   cycle_q<=cycle_n;
   if(cycle_q && !cycle_n)wanted<=(wanted==MAX_MODE)?0:wanted+1'b1;
   if(vs && !vs_q)active_mode<=wanted;
   vs_q<=vs;hs_q<=hs;de_q<=de;de_qq<=de_q;
   center_pixel<=pixel;center_osd<=osd_pixel;overlay_q<=osd_overlay;
   center_y<=current_y;left_y<=center_y;
   vs_o<=vs_q;hs_o<=hs_q;de_o<=de_q;
   if(!de_q)rgb_o<=0;
   else if(active_mode==0)rgb_o<={selected[15:11],3'b000,selected[10:5],2'b00,selected[4:0],3'b000};
   else rgb_o<={add_clip(r8,delta),add_clip(g8,delta),add_clip(b8,delta)};
  end
 end
endmodule
`default_nettype wire
