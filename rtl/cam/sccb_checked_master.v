`timescale 1ns/1ps
`default_nettype none
// 16-bit register, 8-bit data SCCB transactions. clk is a real FPGA clock;
// tick is an enable, not a new clock. ACK is sampled at the middle of SCL high.
// Read uses STOP between pointer write and read address, as supported by SCCB.
module sccb_checked_master #(parameter integer TICK_DIV=625)(
 input wire clk,rstn,start,read_i,input wire [15:0] address,input wire [7:0] write_data,
 output reg busy,done,error,output reg [7:0] read_data,
 output reg scl,inout wire sda);
 localparam IDLE=0,START_A=1,START_B=2,BITS=3,ACK=4,READ_BITS=5,NACK=6,STOP_A=7,STOP_B=8,STOP_C=9;
 reg [3:0] state;reg [15:0] divider,addr;
 reg [7:0] data;reg reading,sda_release,restart;
 reg [2:0] byte_no,bit_no;reg [1:0] phase;
 assign sda=sda_release?1'bz:1'b0;
 function [7:0] txbyte(input [2:0] n);
  begin case(n)0:txbyte=8'h78;1:txbyte=addr[15:8];2:txbyte=addr[7:0];
   3:txbyte=reading?8'h79:data;default:txbyte=0;endcase end
 endfunction
 wire [7:0] outgoing=txbyte(byte_no);
 always @(posedge clk or negedge rstn)begin
  if(!rstn)begin
   state<=IDLE;divider<=0;addr<=0;data<=0;reading<=0;sda_release<=1;restart<=0;
   byte_no<=0;bit_no<=7;phase<=0;busy<=0;done<=0;error<=0;read_data<=0;scl<=1;
  end else begin
   done<=0;
   if(state==IDLE)begin
    divider<=0;scl<=1;sda_release<=1;
    if(start)begin addr<=address;data<=write_data;reading<=read_i;error<=0;read_data<=0;
     busy<=1;byte_no<=0;bit_no<=7;phase<=0;restart<=0;state<=START_A;end
   end else if(divider==TICK_DIV-1)begin
    divider<=0;
    case(state)
     START_A:begin scl<=1;sda_release<=0;state<=START_B;end
     START_B:begin scl<=0;phase<=0;bit_no<=7;state<=BITS;end
     BITS:begin
      case(phase)
       0:begin scl<=0;sda_release<=outgoing[bit_no];phase<=1;end
       1:begin scl<=1;phase<=2;end
       2:phase<=3;
       3:begin scl<=0;phase<=0;if(bit_no==0)state<=ACK;else bit_no<=bit_no-1'b1;end
      endcase
     end
     ACK:begin
      case(phase)
       0:begin sda_release<=1;phase<=1;end
       1:begin scl<=1;phase<=2;end
       2:begin if(sda)error<=1;phase<=3;end
       3:begin
        scl<=0;phase<=0;bit_no<=7;
        if(reading && byte_no==2)begin restart<=1;state<=STOP_A;end
        else if(reading && byte_no==3)state<=READ_BITS;
        else if(byte_no==3)begin restart<=0;state<=STOP_A;end
        else begin byte_no<=byte_no+1'b1;state<=BITS;end
       end
      endcase
     end
     READ_BITS:begin
      case(phase)
       0:begin sda_release<=1;phase<=1;end
       1:begin scl<=1;phase<=2;end
       2:begin read_data[bit_no]<=sda;phase<=3;end
       3:begin scl<=0;phase<=0;if(bit_no==0)state<=NACK;else bit_no<=bit_no-1'b1;end
      endcase
     end
     NACK:begin
      case(phase)
       0:begin sda_release<=1;phase<=1;end
       1:begin scl<=1;phase<=2;end
       2:phase<=3;
       3:begin scl<=0;phase<=0;restart<=0;state<=STOP_A;end
      endcase
     end
     STOP_A:begin scl<=0;sda_release<=0;state<=STOP_B;end
     STOP_B:begin scl<=1;state<=STOP_C;end
     STOP_C:begin
      sda_release<=1;
      if(restart)begin byte_no<=3;bit_no<=7;restart<=0;state<=START_A;end
      else begin done<=1;busy<=0;state<=IDLE;end
     end
     default:begin state<=IDLE;busy<=0;error<=1;end
    endcase
   end else divider<=divider+1'b1;
  end
 end
endmodule
`default_nettype wire
