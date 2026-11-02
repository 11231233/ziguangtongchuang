`timescale 1ns/1ps
module tb_hub_acceptance;
 reg clk=0,rst=0,enabled=0;always #5 clk=~clk;
 reg w0=0,w1=0,r0=0,r1=0;
 reg [27:0] wa0=100,wa1=200,ra0=300,ra1=400;
 wire wr0,wr1,rr0,rr1,mw,mr;wire [27:0] wa,ra;wire [7:0] wb,rb;
 reg wd=0,rd=0;integer wc=0,rc=0,wt=0,rt=0;
 mem_hub dut(.clk(clk),.rstn(rst),
  .w0_req(w0),.w0_addr(wa0),.w0_beats(8'd1),.w0_ready(wr0),.w0_done(),.w0_data(256'd0),.w0_adv(),
  .w1_req(w1),.w1_addr(wa1),.w1_beats(8'd1),.w1_ready(wr1),.w1_done(),.w1_data(256'd0),.w1_adv(),
  .r0_req(r0),.r0_addr(ra0),.r0_beats(8'd1),.r0_ready(rr0),.r0_done(),.r0_data(),.r0_valid(),.r0_last(),
  .r1_req(r1),.r1_addr(ra1),.r1_beats(8'd1),.r1_ready(rr1),.r1_done(),.r1_data(),.r1_valid(),.r1_last(),
  .m_wr_req(mw),.m_wr_addr(wa),.m_wr_beats(wb),.m_wr_ready(enabled && wt==0),.m_wr_done(wd),.m_wr_data(),.m_wr_adv(1'b0),
  .m_rd_req(mr),.m_rd_addr(ra),.m_rd_beats(rb),.m_rd_ready(enabled && rt==0),.m_rd_done(rd),.m_rd_data(256'd0),.m_rd_valid(1'b0),.m_rd_last(1'b0));
 always @(posedge clk)if(rst)begin
  if(!enabled && (wr0||wr1||rr0||rr1))$fatal(1,"CLIENT ACK BEFORE DDR ACCEPTANCE");
  if(wr0)begin w0<=0;wa0<=9999;end
  if(wr1)begin w1<=0;wa1<=9998;end
  if(rr0)begin r0<=0;ra0<=9997;end
  if(rr1)begin r1<=0;ra1<=9996;end
  wd<=0;rd<=0;
  if(mw && enabled && wt==0)begin
   if(wa!==(wc==0?28'd100:wc==1?28'd200:wc==2?28'd500:wc==3?28'd700:28'd900) || wb!=1)$fatal(1,"WRITE ADDRESS LOST");
   wc<=wc+1;wt<=4;
  end else if(wt>0)begin wt<=wt-1;if(wt==1)wd<=1;end
  if(mr && enabled && rt==0)begin
   if(ra!==(rc==0?28'd300:rc==1?28'd400:rc==2?28'd600:rc==3?28'd800:28'd1000) || rb!=1)$fatal(1,"READ ADDRESS LOST");
   rc<=rc+1;rt<=4;
  end else if(rt>0)begin rt<=rt-1;if(rt==1)rd<=1;end
 end
 initial begin
  repeat(4)@(negedge clk);rst=1;w0=1;w1=1;r0=1;r1=1;
  repeat(20)@(negedge clk);enabled=1;
  repeat(35)@(negedge clk);
  if(wc!=2 || rc!=2 || w0 || w1 || r0 || r1)$fatal(1,"MISSING TRANSACTION");
  @(negedge clk);wa0=500;ra0=600;w0=1;r0=1;#1;
  if(!wr0 || !rr0 || !mw || !mr)$fatal(1,"IDLE COMMAND NOT BYPASSED");
  repeat(12)@(negedge clk);
  if(wc!=3 || rc!=3)$fatal(1,"BYPASS COMMAND LOST");
  enabled=0;wa1=700;ra1=800;w1=1;r1=1;
  repeat(3)@(negedge clk);wa0=900;ra0=1000;w0=1;r0=1;#1;
  if(wa!=700 || ra!=800)$fatal(1,"STALLED GRANT PREEMPTED BY NEW PRIORITY");
  repeat(3)@(negedge clk);enabled=1;
  repeat(25)@(negedge clk);
  if(wc!=5 || rc!=5)$fatal(1,"RESERVED/BYPASS TRANSACTIONS LOST");
  $display("HUB_ACCEPTANCE PASS stalled DDR, exact command acceptance, address retention, locked priority, idle bypass and both clients");$finish;
 end
 initial begin #10000;$fatal(1,"HUB ACCEPTANCE TIMEOUT");end
endmodule
