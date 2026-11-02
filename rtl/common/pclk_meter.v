`timescale 1ns/1ps
`default_nettype none
// Count groups of 100000 camera clocks during one 100MHz reference second.
// Result BCD is MHz with one fractional digit: 0210 means 21.0MHz.
// This measures the running PCLK, not active pixels or exposure/frame rate.
module pclk_meter #(
 parameter integer REF_HZ=100000000,
 parameter integer PRESCALE=100000
)(input wire ref_clk,source_clk,rstn,output reg [15:0] rate_bcd);
 (* async_reg="true" *)reg [1:0] source_reset;
 always @(posedge source_clk or negedge rstn)
  if(!rstn)source_reset<=0;else source_reset<={source_reset[0],1'b1};
 reg [16:0] divider;
 reg [15:0] source_count,source_gray;
 always @(posedge source_clk or negedge rstn)begin
  if(!rstn)begin divider<=0;source_count<=0;source_gray<=0;end
  else if(!source_reset[1])begin divider<=0;source_count<=0;source_gray<=0;end
  else if(divider==PRESCALE-1)begin
   divider<=0;source_count<=source_count+1'b1;
   source_gray<=((source_count+16'd1)>>1)^(source_count+16'd1);
  end else divider<=divider+1'b1;
 end
 (* async_reg="true" *)reg [15:0] gray_sync1,gray_sync2;
 reg [15:0] observed;integer i;
 always @*begin
  observed[15]=gray_sync2[15];
  for(i=14;i>=0;i=i-1)observed[i]=observed[i+1]^gray_sync2[i];
 end
 reg [31:0] ticks;
 reg [15:0] previous,shift_bin,shift_bcd;
 reg [4:0] bits_left;
 reg [15:0] adjusted;integer j;
 always @*begin
  adjusted=shift_bcd;
  for(j=0;j<4;j=j+1)if(shift_bcd[j*4+:4]>=5)adjusted[j*4+:4]=shift_bcd[j*4+:4]+4'd3;
 end
 always @(posedge ref_clk)begin
  if(!rstn)begin
   gray_sync1<=0;gray_sync2<=0;ticks<=0;previous<=0;
   shift_bin<=0;shift_bcd<=0;bits_left<=0;rate_bcd<=0;
  end else begin
   gray_sync1<=source_gray;gray_sync2<=gray_sync1;
   if(ticks==REF_HZ-1)begin
    ticks<=0;previous<=observed;shift_bin<=observed-previous;
    shift_bcd<=0;bits_left<=16;
   end else ticks<=ticks+1'b1;
   if(bits_left!=0)begin
    shift_bcd<={adjusted[14:0],shift_bin[15]};shift_bin<={shift_bin[14:0],1'b0};
    bits_left<=bits_left-1'b1;
    if(bits_left==1)rate_bcd<={adjusted[14:0],shift_bin[15]};
   end
  end
 end
endmodule
`default_nettype wire
