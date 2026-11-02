`timescale 1ns/1ps
module tb_quality_natural;
 reg clk=0,rstn=0,vs=0,hs=0,de=0,cycle_n=1,overlay=0;
 reg [15:0] pixel=0,osd_pixel=0;
 wire vo,ho,dout;wire [23:0] rgb;wire [1:0] mode;
 always #5 clk=~clk;
 quality_display #(.MAX_MODE(3),.NATURAL_DETAIL(1)) dut(.clk(clk),.rstn(rstn),.vs(vs),.hs(hs),.de(de),.cycle_n(cycle_n),
  .pixel(pixel),.osd_pixel(osd_pixel),.osd_overlay(overlay),
  .vs_o(vo),.hs_o(ho),.de_o(dout),.rgb_o(rgb),.active_mode(mode));
 integer file,n,r,iv,ih,id,ic,io,ev,eh,ed,em;reg [15:0] ip,op;reg [23:0] er;
 initial begin
  repeat(3)@(negedge clk);rstn=1;
  file=$fopen("sim/out/quality_vectors.txt","r");if(!file)$fatal(1,"NO VECTORS");n=0;
  while(!$feof(file))begin
   r=$fscanf(file,"%d %d %d %d %h %h %d %d %d %d %h %d\n",iv,ih,id,ic,ip,op,io,ev,eh,ed,er,em);
   if(r==12)begin
    vs=iv;hs=ih;de=id;cycle_n=ic;pixel=ip;osd_pixel=op;overlay=io;
    @(posedge clk);#1;
    if(vo!==ev[0] || ho!==eh[0] || dout!==ed[0] || rgb!==er || mode!==em[1:0])
     $fatal(1,"QUALITY MISMATCH sample=%0d got=%b%b%b %h Q%0d expected=%0d%0d%0d %h Q%0d",n,vo,ho,dout,rgb,mode,ev,eh,ed,er,em);
    n=n+1;@(negedge clk);
   end else if(r!=-1)$fatal(1,"BAD VECTOR");
  end
  $fclose(file);if(n<190000)$fatal(1,"INSUFFICIENT VECTORS");
  $display("QUALITY_DISPLAY PASS samples=%0d all 65536 RGB565 values in Q0/Q1/Q2/Q3; timing, frame atomicity, borders and overlay",n);$finish;
 end
endmodule
