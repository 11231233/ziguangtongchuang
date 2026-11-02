`timescale 1ns/1ps
// Each 16-beat command transfers 256 RGB565 pixels. At 100 MHz, one command
// per 463 clocks is the average payload of 1280x720@60fps, for EACH direction.
module video_background #(parameter integer PERIOD=463)(
 input wire clk,rstn,
 output wire write_req,input wire write_ready,write_done,
 output wire read_req,input wire read_ready,read_done,
 output reg [31:0] writes,reads,output reg missed_deadline);
 reg [15:0] ticks;reg [1:0] ws,rs;
 assign write_req=ws==1;assign read_req=rs==1;
 always @(posedge clk)begin
  if(!rstn)begin ticks<=0;ws<=0;rs<=0;writes<=0;reads<=0;missed_deadline<=0;end
  else begin
   if(ticks==PERIOD-1)begin
    ticks<=0;
    if(ws!=0 || rs!=0)missed_deadline<=1;
    if(ws==0)ws<=1;if(rs==0)rs<=1;
   end else ticks<=ticks+1'b1;
   if(ws==1 && write_ready)ws<=2;
   if(ws==2 && write_done)begin ws<=0;writes<=writes+1'b1;end
   if(rs==1 && read_ready)rs<=2;
   if(rs==2 && read_done)begin rs<=0;reads<=reads+1'b1;end
  end
 end
endmodule
