`timescale 1ns/1ps
module tb_raw_edge;
`include "frame_coef.vh"
reg clk=0,rstn=0,valid=0;always #5 clk=~clk;reg[15:0]x=0,y=0;wire vo,inf;wire signed[31:0]u,v;wire signed[15:0]ui,vi;wire[7:0]uf,vf;
coord_map dut(.clk(clk),.rstn(rstn),.A(A),.B(B),.C(C),.D(D),.E(E),.F(F),.k1(K1),.k2(K2),.p1(P1),.p2(P2),.fx(FX),.fy(FY),.cx(CX),.cy(CY),.valid_i(valid),.x_i(x),.y_i(y),.valid_o(vo),.u_q16(u),.v_q16(v),.in_frame(inf),.u_int(ui),.v_int(vi),.u_frac(uf),.v_frac(vf));
integer i,n=0;always @(negedge clk)if(vo)begin $display("x=%0d u=%0d v=%0d inf=%b ui=%0d vi=%0d",n,u,v,inf,ui,vi);n=n+1;end
initial begin repeat(5)@(negedge clk);rstn=1;for(i=0;i<16;i=i+1)begin @(negedge clk);valid=1;x=i;end @(negedge clk);valid=0;repeat(40)@(negedge clk);$finish;end
endmodule
