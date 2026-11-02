`timescale 1ns/1ps
`default_nettype none
// All inputs are synchronous to the DDR user clock. One-second BCD snapshots
// avoid pixel-clock division and distinguish source FPS from correction FPS.
module video_metrics #(parameter integer CLK_HZ=100000000)(
 input wire clk,rstn,source_done,process_start,process_done,
 input wire [5:0] mode_status,input wire [15:0] pclk_rate_bcd,focus_bcd,
 input wire [1:0] gamma_status,test_mode,input wire [7:0] mean_luma_bcd,
 output reg [85:0] snapshot,output reg snapshot_toggle);
 localparam integer MS_DIV=CLK_HZ/1000;
 reg [31:0] second_ticks,ms_ticks;
 reg [11:0] source_count,output_count,current_ms,last_ms;
 reg processing;
 function [11:0] increment(input [11:0] n);
  begin
   if(n==12'h999)increment=n;
   else if(n[7:0]==8'h99)increment={n[11:8]+4'd1,8'd0};
   else if(n[3:0]==9)increment={n[11:4]+8'd1,4'd0};
   else increment=n+1'b1;
  end
 endfunction
 always @(posedge clk)begin
  if(!rstn)begin
   second_ticks<=0;ms_ticks<=0;source_count<=0;output_count<=0;
   current_ms<=0;last_ms<=0;processing<=0;snapshot<=0;snapshot_toggle<=0;
  end else begin
   if(source_done)source_count<=increment(source_count);
   if(process_done)output_count<=increment(output_count);
   if(second_ticks==CLK_HZ-1)begin
    second_ticks<=0;
    snapshot<={test_mode,mean_luma_bcd,gamma_status,focus_bcd,pclk_rate_bcd,mode_status,source_done?increment(source_count):source_count,
               process_done?increment(output_count):output_count,last_ms};
    snapshot_toggle<=!snapshot_toggle;source_count<=0;output_count<=0;
   end else second_ticks<=second_ticks+1'b1;
   if(process_start)begin processing<=1;current_ms<=0;ms_ticks<=0;end
   else if(processing)begin
    if(ms_ticks==MS_DIV-1)begin ms_ticks<=0;current_ms<=increment(current_ms);end
    else ms_ticks<=ms_ticks+1'b1;
   end
   if(process_done)begin
    processing<=0;
    last_ms<=(processing && ms_ticks==MS_DIV-1)?increment(current_ms):current_ms;
   end
  end
 end
endmodule
`default_nettype wire
