`timescale 1ns/1ps
module tb_burst_arb;
reg clk=0,rstn=0;always #5 clk=~clk;
wire ar,br,ad,bd,aa,ba,mreq;wire[27:0]addr;wire[7:0]beats;wire[255:0]data;
reg active=0;reg[31:0]rng=32'h123abcd;integer count=0,tail=0,len=0;reg owner=0;
wire mr=!active&&rng[0];wire ma=active&&count<len&&rng[2];wire md=active&&tail==1;
burst_arb2 dut(.clk(clk),.rstn(rstn),.a_req(rstn),.b_req(rstn),.a_addr(28'h100),.b_addr(28'h200),.a_beats(8'd3),.b_beats(8'd5),.a_data(256'h1111),.b_data(256'h2222),.a_ready(ar),.b_ready(br),.a_done(ad),.b_done(bd),.a_adv(aa),.b_adv(ba),.m_req(mreq),.m_addr(addr),.m_beats(beats),.m_data(data),.m_ready(mr),.m_done(md),.m_adv(ma));
integer a_done=0,b_done=0,total=0;reg previous=1;
always @(posedge clk)begin
 rng<={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
 if(rstn)begin
 if(ar&&br||aa&&ba||ad&&bd)$fatal(1,"MULTIPLE OWNERS");
 if(mreq&&mr)begin
  owner<=addr==28'h200;len<=beats;count<=0;active<=1;
  if((addr==28'h200)==previous)$fatal(1,"ROUND ROBIN STARVATION");previous=addr==28'h200;
 end
 if(ma)begin
  if(owner?(data!==256'h2222||!ba||aa):(data!==256'h1111||!aa||ba))$fatal(1,"BURST INTERLEAVED");
  count<=count+1;if(count==len-1)tail<=5;
 end
 if(tail>0)begin tail<=tail-1;if(tail==1)active<=0;end
 if(ad)begin a_done=a_done+1;total=total+1;end
 if(bd)begin b_done=b_done+1;total=total+1;end
 if(total==20)begin if(a_done!=10||b_done!=10)$fatal(1,"UNFAIR");$display("BURST_ARB PASS: fair complete bursts, randomized acceptance/data stalls, delayed completion, exclusive data and done routing");$finish;end
 end
end
initial begin repeat(5)@(negedge clk);rstn=1;end
initial begin #100000;$fatal(1,"BURST ARB TIMEOUT");end
endmodule
