`timescale 1ns/1ps
`default_nettype none
// 2048 piecewise-linear cells over r^2=[0,32], step=1/64.
// ROM word: {signed Q24 base, signed Q24 endpoint delta}. 3 clock latency.
// The output is Q16, rounded once after interpolation. No runtime division.
module radial_lut #(parameter ROM_FILE="")(
 input wire clk,rstn,valid_i,input wire signed[31:0]r2_q16,
 output reg valid_o,in_range_o,output reg signed[31:0]factor_q16);
 reg[63:0]rom[0:2047];
 // Only $readmemh initialises this array: PDS ignores other initial statements and
 // caps loops at 2000 iterations, so a 2048-entry clear loop fails elaboration.
 initial begin
  if(ROM_FILE!="")$readmemh(ROM_FILE,rom);
 end
 wire endpoint=r2_q16>=32'sd2097152;
 wire[10:0]address=endpoint?11'd2047:r2_q16[20:10];
 wire signed[11:0]fraction=endpoint?12'sd1024:$signed({2'b0,r2_q16[9:0]});
 reg v1,v2,ok1,ok2;reg[63:0]pair1;reg signed[11:0]frac1;
 reg signed[31:0]base2;reg signed[43:0]product2;
 wire signed[31:0]base1=$signed(pair1[63:32]),delta1=$signed(pair1[31:0]);
 wire signed[44:0]interpolated=($signed({{13{base2[31]}},base2})<<<10)+$signed({product2[43],product2});
 always @(posedge clk)begin
  if(!rstn)begin
   v1<=0;v2<=0;valid_o<=0;ok1<=0;ok2<=0;in_range_o<=0;pair1<=0;frac1<=0;base2<=0;product2<=0;factor_q16<=0;
  end else begin
   v1<=valid_i;v2<=v1;valid_o<=v2;
   if(valid_i)begin
    pair1<=rom[address];frac1<=fraction;
    ok1<=ROM_FILE!="" && r2_q16>=0 && r2_q16<=32'sd2097152;
   end
   if(v1)begin base2<=base1;product2<=delta1*frac1;ok2<=ok1;end
   if(v2)begin factor_q16<=(interpolated+45'sd131072)>>>18;in_range_o<=ok2;end
  end
 end
endmodule
`default_nettype wire
