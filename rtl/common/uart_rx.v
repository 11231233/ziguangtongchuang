`timescale 1ns/1ps
`default_nettype none
// 8N1 receiver; false starts and bad stop bits never publish bytes.
module uart_rx #(parameter integer CLK_HZ=100000000, BAUD=115200)(
 input wire clk,rstn,rx,output reg valid,output reg [7:0] data,
 output reg framing_error);
 localparam integer DIV=(CLK_HZ+BAUD/2)/BAUD;
 (* async_reg="true" *) reg r1,r2;
 reg [1:0] st;reg [31:0] ticks;reg [2:0] bitno;reg [7:0] shift;
 always @(posedge clk) begin
  if(!rstn)begin r1<=1;r2<=1;st<=0;ticks<=0;bitno<=0;shift<=0;valid<=0;data<=0;framing_error<=0;end
  else begin
   r1<=rx;r2<=r1;valid<=0;framing_error<=0;
   case(st)
    0:if(!r2)begin ticks<=DIV/2-1;st<=1;end
    1:if(ticks!=0)ticks<=ticks-1;else if(r2)st<=0;
      else begin ticks<=DIV-1;bitno<=0;st<=2;end
    2:if(ticks!=0)ticks<=ticks-1;else begin
       shift[bitno]<=r2;ticks<=DIV-1;
       if(bitno==7)st<=3;else bitno<=bitno+1'b1;
      end
    3:if(ticks!=0)ticks<=ticks-1;else begin
       if(r2)begin data<=shift;valid<=1;end else framing_error<=1;
       st<=0;
      end
   endcase
  end
 end
endmodule
`default_nettype wire
