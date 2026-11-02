`timescale 1ns/1ps
module tb_slots;
reg sc=0,dc=0,rstn=0,vs=0,de=0;reg [15:0] pix=0;always #10 sc=~sc;always #5 dc=~dc;
wire req,ready,done,adv,ovf,fd,fvalid;wire [27:0]addr;wire[7:0]beats;wire[255:0]data;wire[2:0]slot,fs;wire[31:0]seq;
reg hold=0;reg[2:0] held=0;
frame_writer #(.H_ACT(256),.V_ACT(2),.FLIP_V(1),.SLOT_WORDS(256)) dut(
.src_clk(sc),.src_rstn(rstn),.src_vs(vs),.src_de(de),.src_pix(pix),.ddr_clk(dc),.ddr_rstn(rstn),
.w_req(req),.w_addr(addr),.w_beats(beats),.w_ready(ready),.w_done(done),.w_data(data),.w_adv(adv),.wr_slot(slot),.led_overflow(ovf),
.hold_valid(hold),.hold_slot(held),.frame_done(fd),.frame_valid(fvalid),.frame_slot(fs),.frame_seq(seq));
reg [15:0]mem[0:3071];reg busy=0;integer a=0,b=0,tail=0,k,nframes=0;
assign ready=!busy;assign adv=busy&&tail==0;assign done=tail==1;
always @(posedge dc)begin
 if(req&&ready)begin
  if(beats!=16 || addr%8 || addr+128>1536)$fatal(1,"SLOT RANGE");
  if(hold && (addr/256)==held)$fatal(1,"OVERWROTE LOCKED SOURCE");
  a<=addr;b<=0;busy<=1;
 end
 if(adv)begin
  for(k=0;k<16;k=k+1)mem[a*2+b*16+k]<=data[k*16+:16];
  if(b==15)tail<=3;else b<=b+1;
 end
 if(tail>0)begin tail<=tail-1;if(tail==1)busy<=0;end
 if(fd)begin
  if(!fvalid || seq!=nframes+1)$fatal(1,"FRAME METADATA");
  if(nframes==0)begin if(fs!=0)$fatal(1,"FIRST SLOT");hold<=1;held<=0;end
  else if(fs==0)$fatal(1,"PUBLISHED HELD SLOT");
  nframes<=nframes+1;
 end
end
integer f,y,x;
initial begin
 repeat(5)@(negedge sc);rstn=1;
 for(f=0;f<14;f=f+1)begin
  @(negedge sc);vs=1;repeat(8)@(negedge sc);vs=0;
  for(y=0;y<2;y=y+1)begin
   for(x=0;x<256;x=x+1)begin @(negedge sc);de=1;pix=(f<<10)|(y<<8)|x;end
   @(negedge sc);de=0;repeat(30)@(negedge sc);
  end
 end
 repeat(100)@(negedge sc);
 if(nframes!=14 || ovf)$fatal(1,"SLOT END frames=%d ovf=%b",nframes,ovf);
 for(x=0;x<256;x=x+1)begin
  if(mem[x]!==16'd256+x || mem[256+x]!==x[15:0])$fatal(1,"FLIP OR PROTECTION");
 end
 $display("SLOTS PASS: 14 completed frames, six-slot wrap, pinned source preserved, vertical flip before correction");$finish;
end
initial begin #1000000;$fatal(1,"TIMEOUT SLOTS");end
endmodule
