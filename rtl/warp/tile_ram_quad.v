`timescale 1ns/1ps
`default_nettype none
// Four parity banks: any adjacent 2x2 footprint has one sample in each bank.
// 64x64x16 bits total, with the same 256-bit DDR write interface as tile_ram16.
module tile_ram_quad(
 input wire clk,we,input wire [7:0] waddr,input wire [255:0] wdata,
 input wire [5:0] x0,x1,y0,y1,
 output wire [15:0] p00,p01,p10,p11);
 wire [15:0] sample[0:3];reg [1:0] sel00,sel01,sel10,sel11;
 reg [1:0] d00,d01,d10,d11;
 genvar b,j;
 generate for(b=0;b<4;b=b+1)begin:g_bank
  reg [127:0] mem[0:127];reg [127:0] q;reg [2:0] lane;
  reg [15:0] pixel;
  wire [5:0] x=(x0[0]==(b%2))?x0:x1;
  wire [5:0] y=(y0[0]==(b/2))?y0:y1;
  for(j=0;j<8;j=j+1)begin:g_write
   always @(posedge clk)if(we && waddr[2]==(b/2))
    mem[{waddr[7:3],waddr[1:0]}][j*16+:16]<=wdata[(j*2+b%2)*16+:16];
  end
  always @(posedge clk)begin
   q<=mem[{y[5:1],x[5:4]}];lane<=x[3:1];pixel<=q[lane*16+:16];
  end
  assign sample[b]=pixel;
 end endgenerate
 always @(posedge clk)begin
  d00<={y0[0],x0[0]};d01<={y0[0],x1[0]};d10<={y1[0],x0[0]};d11<={y1[0],x1[0]};
  sel00<=d00;sel01<=d01;sel10<=d10;sel11<=d11;
 end
 assign p00=sample[sel00];assign p01=sample[sel01];
 assign p10=sample[sel10];assign p11=sample[sel11];
endmodule
`default_nettype wire
