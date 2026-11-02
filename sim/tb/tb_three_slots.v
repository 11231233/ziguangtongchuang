`timescale 1ns/1ps
module tb_three_slots;
 reg sc=0,dc=0,rstn=0,vs=0,de=0,wanted=0;reg[15:0]pix=0;
 always #10 sc=~sc;always #5 dc=~dc;
 wire req,adv,done,fd,valid,ovf,hold;wire[27:0]addr;wire[255:0]data;wire[7:0]beats;wire[2:0]slot,held;wire[31:0]seq;
 reg busy=0;integer a=0,b=0,tail=0,k,j;
 reg[15:0]mem[0:1535];
 frame_writer #(.H_ACT(256),.V_ACT(2),.SLOT_WORDS(256),.SLOT_COUNT(3)) writer(
 .src_clk(sc),.src_rstn(rstn),.src_vs(vs),.src_de(de),.src_pix(pix),.ddr_clk(dc),.ddr_rstn(rstn),
 .w_req(req),.w_addr(addr),.w_beats(beats),.w_ready(!busy),.w_done(done),.w_data(data),.w_adv(adv),
 .wr_slot(),.led_overflow(ovf),.hold_valid(hold),.hold_slot(held),.frame_done(fd),.frame_valid(valid),.frame_slot(slot),.frame_seq(seq));
 assign adv=busy&&tail==0;assign done=tail==1;
 always @(posedge dc)begin
  if(req&&!busy)begin
   if(addr>=768 || beats!=16)$fatal(1,"THREE SLOT ADDRESS RANGE");
   if(valid && addr/256==slot)$fatal(1,"WRITER OVERWROTE MOST RECENT COMPLETE FRAME addr=%d latest=%d held=%d hold=%b writer=%d seq=%d next=%d",addr,slot,held,hold,writer.slot,seq,writer.next_slot);
   if(hold&&addr/256==held)$fatal(1,"WRITER OVERWROTE HELD FRAME");
   a<=addr;b<=0;busy<=1;
  end
  if(adv)begin
   for(k=0;k<16;k=k+1)mem[a*2+b*16+k]<=data[k*16+:16];
   if(b==15)tail<=3;else b<=b+1;
  end
  if(tail>0)begin tail<=tail-1;if(tail==1)busy<=0;end
 end
 wire accept,start,front,dst,have,frozen,display_frozen;wire[27:0]src;
 reg pd=0;integer pending=0,renders=0,frozen_renders=0,live_after=0;
 reg was_frozen=0;reg[15:0] saved[0:511];
 warp_scheduler #(.SLOT_WORDS(256)) scheduler(.clk(dc),.rstn(rstn),.freeze_wanted(wanted),.frame_valid(valid),.frame_seq(seq),.frame_slot(slot),
 .process_done(pd),.process_overflow(1'b0),.display_seen(have),.display_slot(front),.accept_source(accept),.process_start(start),
 .source_base(src),.read_hold(hold),.read_slot(held),.destination_slot(dst),.front_slot(front),.have_frame(have),.frozen(frozen),.display_frozen(display_frozen));
 always @(posedge dc)if(rstn)begin
  pd<=0;
  if(start)begin
   renders<=renders+1;pending<=35;
   if(frozen)begin
    frozen_renders<=frozen_renders+1;
    for(j=0;j<512;j=j+1)begin
     if(was_frozen && mem[src*2+j]!==saved[j])$fatal(1,"FROZEN PIXELS CHANGED DURING CAPTURE");
     saved[j]=mem[src*2+j];
    end
    was_frozen<=1;
   end else if(was_frozen)live_after<=live_after+1;
  end else if(pending>0)begin pending<=pending-1;if(pending==1)pd<=1;end
 end
 integer f,y,x;
 initial begin
  repeat(5)@(negedge sc);rstn=1;
  for(f=0;f<100;f=f+1)begin
   if(f==4)wanted=1;if(f==78)wanted=0;
   @(negedge sc);vs=1;repeat(8)@(negedge sc);vs=0;
   for(y=0;y<2;y=y+1)begin
    for(x=0;x<256;x=x+1)begin @(negedge sc);de=1;pix=f*512+y*256+x;end
    @(negedge sc);de=0;repeat(30)@(negedge sc);
   end
  end
  repeat(150)@(negedge sc);
  if(seq!=100||ovf||frozen_renders<10||live_after<2||frozen||display_frozen)$fatal(1,"FREEZE END seq=%d held renders=%d live=%d",seq,frozen_renders,live_after);
  $display("THREE_SLOTS PASS: 100 live capture frames, three-slot wraps, 512 held pixels exact across repeated renders, no overwrite and live recovery");$finish;
 end
 initial begin #2000000;$fatal(1,"FREEZE CAPTURE TIMEOUT");end
endmodule

