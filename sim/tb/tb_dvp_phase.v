`timescale 1ns/1ps
module tb_dvp_phase;
 reg clk=0,pclk=0,rstn=0,vs=0,hs=0,request=0;reg[7:0] d=0;
 always #5 clk=~clk;always #8 pclk=~pclk;
 wire[15:0] pix;wire de,mark,phase;
 dvp_capture_phase dut(.cam_pclk(pclk),.rstn(rstn),.vs(vs),.hs(hs),.d(d),.phase_request(request),
  .ddr_clk(clk),.ddr_rstn(rstn),.pix(pix),.de(de),.vs_o(mark),.phase_active(phase));
 integer frame=0,index=0,total=0,f,y,x;reg[15:0] word;
 function[15:0] pattern(input integer ff,ii);begin pattern=16'h2100+ff*1024+ii*13;end endfunction
 always @(posedge clk)if(rstn)begin
  if(mark)begin if(frame && index!=128)$fatal(1,"TRUNCATED PHASE FRAME");frame=frame+1;index=0;end
  if(de)begin
   if(pix!==pattern(frame,index))$fatal(1,"PHASE PIXEL frame=%0d index=%0d pix=%h expected=%h",frame,index,pix,pattern(frame,index));
   index=index+1;total=total+1;
  end
 end
 initial begin
  repeat(5)@(negedge clk);rstn=1;
  for(f=1;f<=4;f=f+1)begin
   @(negedge pclk);#1;vs=1;repeat(8)@(negedge pclk);#1;vs=0;repeat(5)@(negedge pclk);#1;
   if(phase!==(f>=2))$fatal(1,"PHASE DID NOT COMMIT IN VS");
   for(y=0;y<4;y=y+1)begin
    for(x=0;x<32;x=x+1)begin
     hs=1;word=pattern(f,y*32+x);d=word[15:8];@(negedge pclk);#1;d=word[7:0];@(negedge pclk);#1;
     if(f==1 && y==0 && x==10)request=1;
     if(f==1 && phase!==0)$fatal(1,"PHASE CHANGED MIDFRAME");
    end
    hs=0;repeat(6)@(negedge pclk);#1;
   end
   repeat(12)@(negedge pclk);#1;
  end
  repeat(50)@(negedge clk);
  if(total!=512 || index!=128)$fatal(1,"PHASE COVERAGE");
  $display("DVP_PHASE PASS 512 exact RGB565 pixels across rising/falling capture, independent FIFO clock, VS-only switching and line boundaries");$finish;
 end
 initial begin #200000;$fatal(1,"PHASE TIMEOUT");end
endmodule
