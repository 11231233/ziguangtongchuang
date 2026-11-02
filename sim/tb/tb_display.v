`timescale 1ns/1ps
module tb_display;
localparam W=256,H=8,SLOT=W*H/2;
reg pc=0,dc=0,rstn=0;always #6.6667 pc=~pc;always #5 dc=~dc;
wire vs,hs,de,ls;wire[9:0]ly;wire[15:0]pix;
wire req,ready,done,valid,last,under,shown,seen;wire[27:0]addr;wire[7:0]beats;wire[255:0]data;
reg wr_slot=1;
sync_vg #(.H_ACT(W),.H_SYNC(4),.H_BP(80),.H_FP(30),.H_TOTAL(W+114),.V_ACT(H),.V_SYNC(2),.V_BP(3),.V_FP(2),.V_TOTAL(H+7)) timing(
.clk(pc),.rstn(rstn),.vs_out(vs),.hs_out(hs),.de_out(de),.de_re(),.x_act(),.y_act(),.line_start(ls),.line_y(ly));
disp_reader #(.H_ACT(W),.V_ACT(H),.SLOT_WORDS(SLOT),.EXTERNAL_LINE(1)) dut(
.pix_clk(pc),.pix_rstn(rstn),.vs(vs),.hs(hs),.de(de),.pix_out(pix),.wr_slot(wr_slot),.frame_valid(1'b1),.shown_slot(shown),.frame_seen(seen),.line_start(ls),.line_y(ly),
.ddr_clk(dc),.ddr_rstn(rstn),.r_req(req),.r_addr(addr),.r_beats(beats),.r_ready(ready),.r_done(done),.r_data(data),.r_valid(valid),.r_last(last),.led_underrun(under));
reg[31:0]rng=32'h11ba;always @(posedge dc)rng<={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
reg rb=0;integer ra=0,ri=0,len=0,tail=0,k,idx;reg[255:0]rd;
assign ready=!rb&&rng[0];assign valid=rb&&tail==0&&rng[2];assign last=ri==len-1;assign done=tail==1;assign data=rd;
always_comb begin for(integer j=0;j<16;j=j+1)begin
 integer a; a=ra*2+ri*16+j;rd[j*16+:16]=((a/(W*H))<<15)|(((a%(W*H))/W)<<8)|(a%W);
end end
always @(posedge dc)begin
 if(req&&ready)begin if(addr%8||beats!=16||addr+128>2*SLOT)$fatal(1,"DISPLAY RANGE");ra<=addr;ri<=0;len<=beats;rb<=1;end
 if(valid)begin if(last)tail<=4;else ri<=ri+1;end
 if(tail>0)begin tail<=tail-1;if(tail==1)rb<=0;end
end
reg de_d=0,vs_d=0;integer frame=0,n=0,total=0;reg[15:0]gold;
always @(posedge pc)begin de_d<=de;vs_d<=vs;end
always @(negedge pc)if(rstn)begin
 if(vs&&!vs_d)begin frame=frame+1;n=0;end
 if(de_d)begin
  gold=((frame>=3)?16'h8000:16'h0000)|((n/W)<<8)|(n%W);
  if(pix!==gold)$fatal(1,"DISPLAY PIX frame=%d x=%d y=%d got=%h exp=%h",frame,n%W,n/W,pix,gold);
  n=n+1;total=total+1;
  if(frame==3&&n==W*H)begin if(under||!seen||!shown)$fatal(1,"DISPLAY STATUS");$display("DISPLAY PASS: 3 complete frames, 75MHz timing, exact first/last row, mid-frame publication deferred to VS, no underflow");$finish;end
 end
end
initial begin repeat(10)@(negedge pc);rstn=1;wait(total==W*H+W*4);@(negedge pc);wr_slot=0;end
initial begin #500000;$fatal(1,"TIMEOUT DISPLAY");end
endmodule
