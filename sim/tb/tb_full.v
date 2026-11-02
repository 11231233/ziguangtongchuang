`timescale 1ns/1ps
module tb_full;

`include "frame_coef.vh"
`ifdef FULL720P
localparam SW=1280,SH=720,W=1280,H=720,BASE=2000000,MAX_CYCLES=10000000;
`else
localparam SW=192,SH=96,W=128,H=70,BASE=20000,MAX_CYCLES=1000000;
`endif
reg clk=0,rstn=0,start=0;always #5 clk=~clk;
wire busy,done,overflow,r_req,r_ready,r_done,r_valid,r_last,w_req,w_ready,w_done,w_adv;
wire [27:0] r_addr,w_addr;wire [7:0] r_beats,w_beats;wire [255:0] r_data,w_data;
wire er_req,er_ready,er_done,er_valid,er_last,ew_req,ew_ready,ew_done,ew_adv;
wire [27:0] er_addr,ew_addr;wire [7:0] er_beats,ew_beats;wire [255:0] er_data,ew_data;
wire capture_write,display_read;
`ifdef SHARED_DDR
wire bg_wr,bg_wready,bg_wdone,bg_rr,bg_rready,bg_rdone,bg_missed;
wire [31:0] bg_writes,bg_reads;
video_background traffic(.clk(clk),.rstn(rstn),.write_req(bg_wr),.write_ready(bg_wready),.write_done(bg_wdone),
 .read_req(bg_rr),.read_ready(bg_rready),.read_done(bg_rdone),.writes(bg_writes),.reads(bg_reads),.missed_deadline(bg_missed));
mem_hub hub(.clk(clk),.rstn(rstn),
 .w0_req(bg_wr),.w0_addr(28'd4000000),.w0_beats(8'd16),.w0_ready(bg_wready),.w0_done(bg_wdone),.w0_data(256'd0),.w0_adv(),
 .w1_req(ew_req),.w1_addr(ew_addr),.w1_beats(ew_beats),.w1_ready(ew_ready),.w1_done(ew_done),.w1_data(ew_data),.w1_adv(ew_adv),
 .r0_req(bg_rr),.r0_addr(28'd0),.r0_beats(8'd16),.r0_ready(bg_rready),.r0_done(bg_rdone),.r0_data(),.r0_valid(),.r0_last(),
 .r1_req(er_req),.r1_addr(er_addr),.r1_beats(er_beats),.r1_ready(er_ready),.r1_done(er_done),.r1_data(er_data),.r1_valid(er_valid),.r1_last(er_last),
 .m_wr_req(w_req),.m_wr_addr(w_addr),.m_wr_beats(w_beats),.m_wr_ready(w_ready),.m_wr_done(w_done),.m_wr_data(w_data),.m_wr_adv(w_adv),
 .m_rd_req(r_req),.m_rd_addr(r_addr),.m_rd_beats(r_beats),.m_rd_ready(r_ready),.m_rd_done(r_done),.m_rd_data(r_data),.m_rd_valid(r_valid),.m_rd_last(r_last));
assign capture_write=!hub.w_selected;
assign display_read=!hub.r_selected;
`else
assign r_req=er_req;assign r_addr=er_addr;assign r_beats=er_beats;
assign er_ready=r_ready;assign er_done=r_done;assign er_valid=r_valid;assign er_last=r_last;assign er_data=r_data;
assign w_req=ew_req;assign w_addr=ew_addr;assign w_beats=ew_beats;assign w_data=ew_data;
assign ew_ready=w_ready;assign ew_done=w_done;assign ew_adv=w_adv;
assign capture_write=0;assign display_read=0;
`endif
`ifndef FULL720P
reg [15:0] src[0:SW*SH-1];
`endif
reg [15:0] gold[0:W*H-1];
reg [15:0] dst[0:W*H-1];integer seen[0:W*H-1];
warp_frame #(.WORDS_PER_LINE(W/2),.SRC_STRIDE(SW/2),.SRC_H(SH),.V_ACT(H),.TILE(16)) dut(
.clk(clk),.rstn(rstn),.A(A),.B(B),.C(C),.D(D),.E(E),.F(F),.k1(K1),.k2(K2),.p1(P1),.p2(P2),.fx(FX),.fy(FY),.cx(CX),.cy(CY),
.src_base(28'd0),.dst_base(BASE[27:0]),.start(start),.busy(busy),.done(done),
.r_req(er_req),.r_addr(er_addr),.r_beats(er_beats),.r_ready(er_ready),.r_done(er_done),.r_data(er_data),.r_valid(er_valid),.r_last(er_last),
.w_req(ew_req),.w_addr(ew_addr),.w_beats(ew_beats),.w_ready(ew_ready),.w_done(ew_done),.w_data(ew_data),.w_adv(ew_adv),.overflow(overflow));
reg [31:0] rng=32'h1234567;always @(posedge clk) rng<={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
reg rb=0;integer ra=0,ri=0,rlen=0,rtail=0;reg [255:0] rd=0;integer k,j;
assign r_ready=!rb && rng[0];assign r_valid=rb&&rtail==0&&rng[2];
assign r_last=ri==rlen-1;assign r_data=rd;assign r_done=rb&&rtail==1;
`ifdef FULL720P
function [15:0] source_pixel(input integer address);
 integer x,y;begin x=address%SW;y=address/SW;
 source_pixel=(((x*13+y*7)%32)<<11)|(((x+y*3)%64)<<5)|((x*3+y*5)%32);end
endfunction
always @* begin rd=0;if(rb)for(integer q=0;q<16;q=q+1) rd[q*16+:16]=source_pixel(ra*2+ri*16+q);end
`else
always @* begin rd=0;if(rb)for(integer q=0;q<16;q=q+1) rd[q*16+:16]=src[ra*2+ri*16+q];end
`endif
always @(posedge clk) begin
 if(r_req&&r_ready) begin
  if(r_addr%8 || r_beats<1 || r_beats>(display_read?16:4) || r_addr*2+r_beats*16>SW*SH) begin
   // Per-row bounds are checked below; the full 64-row size is checked by the scheduler's requests.
   $fatal(1,"READ ADDRESS %d beats=%d",r_addr,r_beats);
  end
  ra<=r_addr;ri<=0;rlen<=r_beats;rb<=1;
 end
 if(r_valid) begin if(r_last) rtail<=5;else ri<=ri+1;end
 if(rtail>0) begin rtail<=rtail-1;if(rtail==1) rb<=0;end
end
reg wb=0,wa_capture=0;integer wa=0,wi=0,wn=0,wtail=0,wcount=0;
`ifdef STALL_OUTPUT
reg [15:0] stall_cycles=0;reg saw_full=0;
always @(posedge clk)begin
 if(stall_cycles<20000)stall_cycles<=stall_cycles+1'b1;
 if(!dut.u_pack.pixel_ready)saw_full<=1;
end
assign w_ready=stall_cycles>=20000&&!wb&&rng[3];
`else
assign w_ready=!wb&&rng[3];
`endif
assign w_adv=wb&&wtail==0&&rng[4];assign w_done=wb&&wtail==1;
always @(posedge clk) begin
 if(w_req&&w_ready) begin
  if(capture_write)begin if(w_addr!=4000000 || w_beats!=16)$fatal(1,"BACKGROUND WRITE RANGE");end
  else if(w_addr%8 || w_beats!=1 || w_addr<BASE || w_addr+8>BASE+W*H/2) $fatal(1,"WRITE RANGE %d",w_addr);
  wa<=w_addr;wn<=w_beats;wi<=0;wb<=1;wa_capture<=capture_write;
 end
 if(w_adv) begin
  if(!wa_capture)begin
  for(k=0;k<16;k=k+1) begin
   j=(wa-BASE)*2+wi*16+k;
   if(seen[j]!=0) $fatal(1,"DUPLICATE %d",j);
   dst[j]<=w_data[k*16+:16];seen[j]<=seen[j]+1;
  end
  wcount<=wcount+16;
  end else if(w_data!==256'd0)$fatal(1,"BACKGROUND WRITE DATA");
  if(wi==wn-1) wtail<=9;else wi<=wi+1;
 end
 if(wtail>0) begin wtail<=wtail-1;if(wtail==1) wb<=0;end
end
integer i,n,err=0,cycles=0,round_no;
integer perf_rd_requests=0,perf_rd_beats=0,perf_rd_wait=0,perf_wr_wait=0;
integer perf_fetch_cycles=0,perf_render_cycles=0,perf_overlap=0,perf_render_starved=0,perf_pack_stall=0;
always @(posedge clk)if(rstn&&busy)begin
 if(er_req&&er_ready)begin perf_rd_requests<=perf_rd_requests+1;perf_rd_beats<=perf_rd_beats+er_beats;end
 if(er_req&&!er_ready)perf_rd_wait<=perf_rd_wait+1;
 if(ew_req&&!ew_ready)perf_wr_wait<=perf_wr_wait+1;
 if(dut.fetch_busy)perf_fetch_cycles<=perf_fetch_cycles+1;
 if(dut.render_active)perf_render_cycles<=perf_render_cycles+1;
 if(dut.fetch_busy&&dut.render_active)perf_overlap<=perf_overlap+1;
 if(!dut.render_active&&!dut.all_rendered)perf_render_starved<=perf_render_starved+1;
 if(dut.render_active&&!dut.pack_ready)perf_pack_stall<=perf_pack_stall+1;
end
`ifdef REPEAT_FRAME
localparam FRAME_ROUNDS=2;
`else
localparam FRAME_ROUNDS=1;
`endif
reg saw_overlap=0;
reg [6:0] checked_width[0:1],checked_height[0:1];
always @(posedge clk)if(rstn)begin
 if(dut.fetch_done)begin checked_width[dut.fetch_bank]<=dut.fetch_width;checked_height[dut.fetch_bank]<=dut.fetch_height;end
 if(dut.pixel_result && dut.map_in_frame)begin
  if($signed(dut.map_ui)<dut.render_u || $signed(dut.map_vi)<dut.render_v ||
     dut.map_ui-dut.render_u>=checked_width[dut.render_bank] || dut.map_vi-dut.render_v>=checked_height[dut.render_bank])
   $fatal(1,"VALID PIXEL OUTSIDE ACTUALLY FETCHED WINDOW");
  if((dut.map_ui!=SW-1 && dut.map_ui+1-dut.render_u>=checked_width[dut.render_bank]) ||
     (dut.map_vi!=SH-1 && dut.map_vi+1-dut.render_v>=checked_height[dut.render_bank]))
   $fatal(1,"BILINEAR NEIGHBOUR WAS NOT FETCHED");
 end
 if(dut.fetch_we && dut.render_active && dut.fetch_bank==dut.render_bank)$fatal(1,"WINDOW BANK OVERWRITTEN DURING RENDER");
 if(dut.fetch_we && dut.valid_bank[dut.fetch_bank])$fatal(1,"PUBLISHED WINDOW OVERWRITTEN");
 if(dut.bb_valid && dut.pixel_request)$fatal(1,"MAPPER DOUBLE ISSUE");
 if(dut.fetch_we && dut.render_busy)saw_overlap<=1;
end
initial begin
`ifndef FULL720P
 $readmemh("sim/out/full_src.hex",src);
`endif
 $readmemh("sim/out/full_expect.hex",gold);
 repeat(5) @(negedge clk);rstn=1;repeat(5) @(negedge clk);
 for(round_no=0;round_no<FRAME_ROUNDS;round_no=round_no+1)begin
 for(i=0;i<W*H;i=i+1) begin dst[i]=16'hxxxx;seen[i]=0;end
 wcount=0;cycles=0;err=0;
 perf_rd_requests=0;perf_rd_beats=0;perf_rd_wait=0;perf_wr_wait=0;
 perf_fetch_cycles=0;perf_render_cycles=0;perf_overlap=0;perf_render_starved=0;perf_pack_stall=0;
 start=1;@(negedge clk);start=0;
 while(!done && cycles<MAX_CYCLES) begin @(negedge clk);cycles=cycles+1;if(cycles%200000==0)$display("FULL_PROGRESS cycles=%d state=%d tile=(%d,%d)",cycles,dut.st,dut.tx,dut.ty);end
 if(!done || busy || (wb&&!wa_capture) || overflow || wcount!=W*H) $fatal(1,"INCOMPLETE cycles=%d count=%d",cycles,wcount);
 for(i=0;i<W*H;i=i+1) begin
  if(seen[i]!=1 || dst[i]!==gold[i]) begin
   if(err<12) $display("MISMATCH x=%d y=%d got=%h exp=%h",i%W,i/W,dst[i],gold[i]);err=err+1;
  end
 end
`ifdef STALL_OUTPUT
 if(!saw_full)$fatal(1,"BACKPRESSURE RESERVE NOT EXERCISED");
`endif
`ifndef FULL720P
 if(cycles>150000)$fatal(1,"FAST FRAME CYCLE BUDGET EXCEEDED %0d",cycles);
`endif
 if(err) $fatal(1,"FULL FRAME FAIL %d",err);
 if(!saw_overlap)$fatal(1,"PREFETCH OVERLAP NOT EXERCISED");
`ifdef SHARED_DDR
 if(bg_missed || bg_writes<2 || bg_reads<2)$fatal(1,"BACKGROUND VIDEO SERVICE MISSED writes=%d reads=%d",bg_writes,bg_reads);
 $display("SHARED_VIDEO PASS: capture=%d display=%d bursts, each average 720P60 payload, no missed deadline",bg_writes,bg_reads);
`endif
 $display("FULL_FRAME PASS: %d pixels exact, clipped edges, aligned DDR, random stalls, completion drained; cycles=%d",wcount,cycles);
 $display("PERF rd_requests=%0d rd_beats=%0d rd_request_wait=%0d wr_request_wait=%0d fetch_cycles=%0d render_cycles=%0d overlap_cycles=%0d render_starved=%0d pack_stall=%0d",perf_rd_requests,perf_rd_beats,perf_rd_wait,perf_wr_wait,perf_fetch_cycles,perf_render_cycles,perf_overlap,perf_render_starved,perf_pack_stall);
 repeat(5)@(negedge clk);
 end
 $finish;
end
initial begin #(MAX_CYCLES*10+100000);$fatal(1,"TIMEOUT full frame");end
`ifdef TRACE_EDGE
initial begin #100000; $finish;end
always @(posedge clk)begin
 if(dut.wp_we && dut.wp_y==0 && dut.wp_x<16)$display("EDGE_OUT x=%d pix=%h bp=%h tag=%h",dut.wp_x,dut.wp_pix,dut.u_warp.bp,dut.u_warp.t4);
 if(dut.u_warp.v2 && dut.u_warp.m2[31:16]==0 && dut.u_warp.m2[47:32]<16)$display("EDGE_RAM meta=%h p=%h %h %h %h",dut.u_warp.m2,dut.a00,dut.a01,dut.a10,dut.a11);
 if(dut.fetch_we && dut.fetch_addr<4 && dut.tx==0 && dut.ty==0)$display("EDGE_FETCH addr=%h data=%h",dut.fetch_addr,dut.fetch_data);
end
`endif
endmodule
