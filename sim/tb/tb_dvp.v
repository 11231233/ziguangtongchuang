`timescale 1ns/1ps
module tb_dvp;
reg cc=0,dc=0,run_ddr=0,rstn=0,vs=0,hs=0;reg[7:0]d=0;
always #5 cc=~cc;always #7 if(run_ddr)dc=~dc;
wire[15:0]pix;wire de,vo;
dvp_capture dut(.cam_pclk(cc),.rstn(rstn),.vs(vs),.hs(hs),.d(d),.ddr_clk(dc),.ddr_rstn(rstn),.pix(pix),.de(de),.vs_o(vo));
integer mode=0,index=0,recovered=0;reg recovery_marker=0;
function[16:0]expected(input integer i);begin
 if(i==0 || i==32)expected=17'h10000;
 else if(i<32)expected=17'h01200+i-1;
 else expected=17'h03400+i-33;
end endfunction
always @(posedge dc)if(rstn)begin
 if(de&&vo)$fatal(1,"VS AND DE COLLISION");
 if(mode==0&&(de||vo))begin
  if(index>=52 || {vo,pix}!==expected(index))$fatal(1,"DVP ORDER index=%0d got=%h expected=%h",index,{vo,pix},expected(index));
  index=index+1;
 end
 if(mode==2)begin
  if(vo)begin if(recovery_marker)$fatal(1,"EXTRA MARKER");recovery_marker=1;end
  if(de)begin
   if(!recovery_marker || pix!==16'h7000+recovered)$fatal(1,"OVERFLOW RECOVERY PIXEL %0d %h",recovered,pix);
   recovered=recovered+1;
  end
 end
end
task marker;begin @(negedge cc);hs=0;vs=1;repeat(5)@(negedge cc);vs=0;repeat(4)@(negedge cc);end endtask
task pixels(input integer n,input integer base);integer x;reg[15:0]v;begin
 for(x=0;x<n;x=x+1)begin v=base+x;@(negedge cc);hs=1;d=v[15:8];@(negedge cc);d=v[7:0];end
 @(negedge cc);hs=0;repeat(6)@(negedge cc);
end endtask
initial begin
 repeat(5)@(negedge cc);rstn=1;
 pixels(7,16'h9900);marker;pixels(31,16'h1200);marker;pixels(19,16'h3400);
 run_ddr=1;repeat(150)@(negedge cc);
 if(index!=52)$fatal(1,"DVP COUNT %0d",index);
 // Exercise full and rearm, independently of the exact conservative FIFO depth.
 mode=1;rstn=0;repeat(6)@(negedge cc);run_ddr=0;rstn=1;
 marker;pixels(600,16'h5000);marker;pixels(200,16'h6000);
 run_ddr=1;repeat(1000)@(negedge cc);
 if(!dut.empty)$fatal(1,"DVP DRAIN");
 mode=2;marker;pixels(23,16'h7000);repeat(150)@(negedge cc);
 if(recovered!=23 || !recovery_marker)$fatal(1,"DVP RECOVERY COUNT %0d",recovered);
 $display("DVP PASS: mid-frame start ignored, VS ordered behind queued pixels, FIFO overflow drops to next accepted VS and recovers");$finish;
end
initial begin #200000;$fatal(1,"TIMEOUT DVP");end
endmodule
