`timescale 1ns/1ps
`default_nettype none
module uart_tx #(parameter integer CLK_HZ=100000000,BAUD=115200)(
 input wire clk,rstn,start,input wire [7:0] data,output reg tx,busy);
 localparam integer DIV=(CLK_HZ+BAUD/2)/BAUD;
 reg [31:0] ticks;reg [3:0] bitno;reg [9:0] bits;
 always @(posedge clk)begin
  if(!rstn)begin tx<=1;busy<=0;ticks<=0;bitno<=0;bits<=10'h3ff;end
  else if(!busy)begin
   if(start)begin bits<={1'b1,data,1'b0};tx<=0;busy<=1;ticks<=DIV-1;bitno<=0;end
  end else if(ticks!=0)ticks<=ticks-1;
  else if(bitno==9)begin busy<=0;tx<=1;end
  else begin bitno<=bitno+1'b1;bits<={1'b1,bits[9:1]};tx<=bits[1];ticks<=DIV-1;end
 end
endmodule
`default_nettype wire
