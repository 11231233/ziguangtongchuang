`timescale 1ns/1ps
`default_nettype none
// RGB565 bilinear interpolation, exact floor semantics. Four registered stages:
// weights -> per-channel products -> pair sums -> final sum/output.
module bilinear_2x2(input wire clk,rstn,valid_i,
 input wire [15:0]p00,p01,p10,p11,input wire [7:0]fu,fv,
 output reg valid_o,output reg [15:0]rgb_o);
 reg [16:0]w00,w01,w10,w11;
 reg [15:0]c00,c01,c10,c11;
 reg v1,v2,v3;
 wire [8:0]iu=9'd256-{1'b0,fu},iv=9'd256-{1'b0,fv};
 reg [21:0]r00,r01,r10,r11,g00,g01,g10,g11,b00,b01,b10,b11;
 reg [22:0]rlo,rhi,glo,ghi,blo,bhi;
 wire [23:0]sr={1'b0,rlo}+{1'b0,rhi};
 wire [23:0]sg={1'b0,glo}+{1'b0,ghi};
 wire [23:0]sb={1'b0,blo}+{1'b0,bhi};
 always @(posedge clk)begin
  if(!rstn)begin
   w00<=0;w01<=0;w10<=0;w11<=0;c00<=0;c01<=0;c10<=0;c11<=0;
   v1<=0;v2<=0;v3<=0;valid_o<=0;rgb_o<=0;
   r00<=0;r01<=0;r10<=0;r11<=0;g00<=0;g01<=0;g10<=0;g11<=0;b00<=0;b01<=0;b10<=0;b11<=0;
   rlo<=0;rhi<=0;glo<=0;ghi<=0;blo<=0;bhi<=0;
  end else begin
   v1<=valid_i;v2<=v1;v3<=v2;valid_o<=v3;
   if(valid_i)begin
    w00<=iu*iv;w01<={1'b0,fu}*iv;w10<=iu*{1'b0,fv};w11<={1'b0,fu}*{1'b0,fv};
    c00<=p00;c01<=p01;c10<=p10;c11<=p11;
   end
   if(v1)begin
    r00<=c00[15:11]*w00;r01<=c01[15:11]*w01;r10<=c10[15:11]*w10;r11<=c11[15:11]*w11;
    g00<=c00[10:5]*w00;g01<=c01[10:5]*w01;g10<=c10[10:5]*w10;g11<=c11[10:5]*w11;
    b00<=c00[4:0]*w00;b01<=c01[4:0]*w01;b10<=c10[4:0]*w10;b11<=c11[4:0]*w11;
   end
   if(v2)begin
    rlo<={1'b0,r00}+{1'b0,r01};rhi<={1'b0,r10}+{1'b0,r11};
    glo<={1'b0,g00}+{1'b0,g01};ghi<={1'b0,g10}+{1'b0,g11};
    blo<={1'b0,b00}+{1'b0,b01};bhi<={1'b0,b10}+{1'b0,b11};
   end
   if(v3)rgb_o<={sr[20:16],sg[21:16],sb[20:16]};
  end
 end
endmodule
`default_nettype wire
