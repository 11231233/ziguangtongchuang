`timescale 1ns/1ps
`default_nettype none
// A5 5A, version=1, sequence, 14 little-endian signed Q16.16 words,
// CRC16-CCITT (init FFFF, version through payload), CRC high byte first.
// Packet reception, pending bank, active frame bank are independent.
module warp_config #(parameter integer TIMEOUT_CYCLES=1000000)(
 input wire clk,rstn,byte_valid,input wire [7:0] byte_data,
 input wire abort_packet,frame_start,release_host,
 output reg [447:0] active_coeff,output reg active,
 output reg packet_ok,packet_error,output reg [7:0] active_sequence);
 function [15:0] crc_byte(input [15:0] crc,input [7:0] value);
  reg [15:0] c;integer j;
  begin c=crc^{value,8'd0};for(j=0;j<8;j=j+1)c=c[15]?((c<<1)^16'h1021):(c<<1);crc_byte=c;end
 endfunction
 reg [2:0] st;reg [5:0] index;
 reg [31:0] timeout_count;
 reg [15:0] crc;reg [7:0] crc_hi,sequence_rx,pending_sequence;
 reg [447:0] receiving,pending_coeff;reg pending;
 always @(posedge clk)begin
  if(!rstn)begin
   st<=0;index<=0;timeout_count<=0;crc<=16'hffff;crc_hi<=0;sequence_rx<=0;
   pending_sequence<=0;active_sequence<=0;receiving<=0;pending_coeff<=0;active_coeff<=0;
   pending<=0;active<=0;packet_ok<=0;packet_error<=0;
  end else begin
   packet_ok<=0;packet_error<=0;
   if(frame_start)begin
    active<=pending && !release_host;
    if(pending)begin active_coeff<=pending_coeff;active_sequence<=pending_sequence;end
   end
   if(release_host)begin pending<=0;st<=0;end
   else if(abort_packet || (st!=0 && timeout_count==TIMEOUT_CYCLES-1))begin
    st<=0;timeout_count<=0;packet_error<=1;
   end else if(byte_valid)begin
    timeout_count<=0;
    case(st)
     0:if(byte_data==8'ha5)st<=1;
     1:if(byte_data==8'h5a)st<=2;else if(byte_data!=8'ha5)st<=0;
     2:if(byte_data==1)begin crc<=crc_byte(16'hffff,byte_data);st<=3;end
       else begin st<=0;packet_error<=1;end
     3:begin sequence_rx<=byte_data;crc<=crc_byte(crc,byte_data);index<=0;st<=4;end
     4:begin receiving[index*8+:8]<=byte_data;crc<=crc_byte(crc,byte_data);
       if(index==55)st<=5;else index<=index+1'b1;end
     5:begin crc_hi<=byte_data;st<=6;end
     6:begin
       st<=0;
       if({crc_hi,byte_data}==crc)begin
        pending_coeff<=receiving;pending_sequence<=sequence_rx;pending<=1;packet_ok<=1;
       end else packet_error<=1;
      end
     default:st<=0;
    endcase
   end else if(st!=0)timeout_count<=timeout_count+1'b1;
  end
 end
endmodule
`default_nettype wire
