`timescale 1ns/1ps
`default_nettype none
// Process-cycle measurement only: excludes sensor exposure and display latency.
// A5 5B, 01, active-sequence, cycles LE32, completed-frames LE32, CRC16 BE.
module warp_telemetry #(parameter integer CLK_HZ=100000000,BAUD=115200)(
 input wire clk,rstn,frame_start,frame_done,input wire [7:0] sequence_id,
 output wire tx,output reg [31:0] last_cycles,completed_frames);
 function [15:0] crc_byte(input [15:0] crc,input [7:0] value);
  reg [15:0] c;integer j;
  begin c=crc^{value,8'd0};for(j=0;j<8;j=j+1)c=c[15]?((c<<1)^16'h1021):(c<<1);crc_byte=c;end
 endfunction
 reg running;reg [31:0] cycles;
 reg [79:0] payload,pending_payload;reg pending;
 reg [3:0] index;reg [1:0] state;
 reg [15:0] crc;reg start_tx;reg [7:0] data_tx;
 wire tx_busy;
 uart_tx #(.CLK_HZ(CLK_HZ),.BAUD(BAUD)) serial_out(.clk(clk),.rstn(rstn),.start(start_tx),.data(data_tx),.tx(tx),.busy(tx_busy));
 always @(posedge clk)begin
  if(!rstn)begin running<=0;cycles<=0;last_cycles<=0;completed_frames<=0;
   payload<=0;pending_payload<=0;pending<=0;index<=0;state<=0;crc<=16'hffff;start_tx<=0;data_tx<=0;
  end else begin
   start_tx<=0;
   if(frame_start)begin running<=1;cycles<=0;end
   else if(running)cycles<=cycles+1'b1;
   if(frame_done)begin
    running<=0;last_cycles<=cycles;completed_frames<=completed_frames+1'b1;
    pending_payload<={completed_frames+32'd1,cycles,sequence_id,8'd1};pending<=1;
   end
   case(state)
    0:if(pending)begin payload<=pending_payload;pending<=frame_done;index<=0;crc<=16'hffff;state<=1;end
    1:if(!tx_busy)begin
      case(index)
       0:data_tx<=8'ha5;
       1:data_tx<=8'h5b;
       12:data_tx<=crc[15:8];
       13:data_tx<=crc[7:0];
       default:begin data_tx<=payload[(index-2)*8+:8];crc<=crc_byte(crc,payload[(index-2)*8+:8]);end
      endcase
      start_tx<=1;state<=2;
     end
    2:if(tx_busy)state<=3;
    3:if(!tx_busy)begin if(index==13)state<=0;else begin index<=index+1'b1;state<=1;end end
   endcase
  end
 end
endmodule
`default_nettype wire
