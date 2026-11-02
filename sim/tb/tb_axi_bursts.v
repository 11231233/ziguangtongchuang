`timescale 1ns/1ps
module tb_axi_bursts;
 reg clk=0,rst=0,wreq=0,rreq=0;always #5 clk=~clk;
 reg [27:0] wbase=0,rbase=0;reg [7:0] beats=1;
 wire wr_ready,wr_done,wr_adv,rr_ready,rr_done,rv,rl;
 wire [27:0] awaddr,araddr;wire [3:0] awlen,arlen;wire awvalid,arvalid;
 wire [255:0] wd,rd;
 integer tick=0,wremain=0,rremain=0,wt=0,rt=0,src=0,ws=0,rs=0,commands=0;
 wire awready=rst && wremain==0 && tick%4!=0;
 wire arready=rst && rremain==0 && tick%3!=0;
 wire wready=rst && wremain>0 && tick%3!=0;
 wire rvalid=rst && rremain>0 && tick%4!=0;
 function [255:0] pattern(input integer n);
  integer j;begin for(j=0;j<16;j=j+1)pattern[j*16+:16]=(n*37+j*101)^16'ha53c;end
 endfunction
 axi_ddr_master dut(.clk(clk),.rstn(rst),.wr_req(wreq),.wr_addr(wbase),.wr_beats(beats),
  .wr_ready(wr_ready),.wr_done(wr_done),.wr_data(pattern(src)),.wr_dready(wr_adv),
  .rd_req(rreq),.rd_addr(rbase),.rd_beats(beats),.rd_ready(rr_ready),.rd_done(rr_done),.rd_data(rd),.rd_dvalid(rv),.rd_dlast(rl),
  .axi_awaddr(awaddr),.axi_awid(),.axi_awlen(awlen),.axi_awvalid(awvalid),.axi_awready(awready),
  .axi_wdata(wd),.axi_wstrb(),.axi_wready(wready),.axi_wusero_last(1'b0),
  .axi_araddr(araddr),.axi_arid(),.axi_arlen(arlen),.axi_arvalid(arvalid),.axi_arready(arready),
  .axi_rdata(pattern(rt)),.axi_rvalid(rvalid),.axi_rlast(rvalid && rremain==1),.axi_rid(4'd0));
 reg aw_wait=0,ar_wait=0;reg [31:0] aw_saved,ar_saved;
 always @(posedge clk)begin
  tick<=tick+1;
  if(rst)begin
   if(aw_wait && (!awvalid || {awaddr,awlen}!==aw_saved))$fatal(1,"AW CHANGED UNDER STALL");
   if(ar_wait && (!arvalid || {araddr,arlen}!==ar_saved))$fatal(1,"AR CHANGED UNDER STALL");
   aw_wait<=awvalid&&!awready;ar_wait<=arvalid&&!arready;
   aw_saved<={awaddr,awlen};ar_saved<={araddr,arlen};
   if(awvalid&&awready)begin
    if(awaddr!==wbase+(wt-ws)*8)$fatal(1,"WRITE WORD ADDRESS UNIT/INCREMENT");
    if(awlen+1>beats-(wt-ws))$fatal(1,"WRITE OVERREAD LENGTH");
    wremain<=awlen+1;
   end
   if(arvalid&&arready)begin
    if(araddr!==rbase+(rt-rs)*8)$fatal(1,"READ WORD ADDRESS UNIT/INCREMENT");
    if(arlen+1>beats-(rt-rs))$fatal(1,"READ OVERREAD LENGTH");
    rremain<=arlen+1;
   end
   if(wready)begin
    if(wd!==pattern(wt) || !wr_adv)$fatal(1,"WRITE DATA/ADVANCE MISMATCH");
    wremain<=wremain-1;wt<=wt+1;
   end
   if(wr_adv)src<=src+1;
   if(rvalid)begin
    if(!rv || rd!==pattern(rt) || rl!==(rremain==1))$fatal(1,"READ DATA/LAST ROUTING");
    rremain<=rremain-1;rt<=rt+1;
   end
  end
 end
 task run(input integer n,input integer base);
  begin
   @(negedge clk);ws=wt;rs=rt;wbase=base;rbase=base+2048;beats=n;wreq=1;rreq=1;
   wait(wr_ready && rr_ready);@(negedge clk);wreq=0;rreq=0;
   fork begin wait(wr_done);end begin wait(rr_done);end join
   repeat(3)@(negedge clk);
   if(wt-ws!=n || rt-rs!=n)$fatal(1,"COMMAND BEAT COUNT n=%d write=%d read=%d",n,wt-ws,rt-rs);
   commands=commands+1;
  end
 endtask
 initial begin
  repeat(4)@(negedge clk);rst=1;
  run(1,0);run(16,1016);run(17,2040);run(31,4096);run(32,8184);run(240,16384);
  $display("AXI_BURSTS PASS %0d concurrent read/write commands, 337 beats each, vendor word addresses, split lengths and stalls",commands);$finish;
 end
 initial begin #100000;$fatal(1,"AXI BURST TIMEOUT");end
endmodule
