`timescale 1ns/1ps
module tb_capture_overflow;
reg sc=0,dc=0,rstn=0,vs=0,de=0,allow=0;reg[15:0]pix=0;
always #10 sc=~sc;always #5 dc=~dc;
wire req,ready,done,adv,ovf,fd,fvalid;wire[27:0]addr;wire[7:0]beats;wire[255:0]data;wire[2:0]slot,fs;wire[31:0]seq;
frame_writer #(.H_ACT(256),.V_ACT(8),.SLOT_WORDS(1024)) dut(
.src_clk(sc),.src_rstn(rstn),.src_vs(vs),.src_de(de),.src_pix(pix),.ddr_clk(dc),.ddr_rstn(rstn),
.w_req(req),.w_addr(addr),.w_beats(beats),.w_ready(ready),.w_done(done),.w_data(data),.w_adv(adv),.wr_slot(slot),.led_overflow(ovf),
.hold_valid(1'b0),.hold_slot(3'd0),.frame_done(fd),.frame_valid(fvalid),.frame_slot(fs),.frame_seq(seq));
reg busy=0;integer b=0,tail=0,k,a=0,n=0;reg[15:0]mem[0:12287];
assign ready=allow&&!busy;assign adv=busy&&tail==0;assign done=tail==1;
always @(posedge dc)begin
 if(req&&ready)begin a<=addr;b<=0;busy<=1;if(beats!=16 || addr+128>6144)$fatal(1,"RANGE");end
 if(adv)begin
  for(k=0;k<16;k=k+1)mem[a*2+b*16+k]<=data[k*16+:16];
  if(b==15)tail<=3;else b<=b+1;
 end
 if(tail>0)begin tail<=tail-1;if(tail==1)busy<=0;end
 if(fd)begin
  if(n!=0)$fatal(1,"BAD FRAME PUBLISHED");
  for(k=0;k<2048;k=k+1)if(mem[fs*2048+k]!==16'h4000+k)$fatal(1,"CAPTURE MIXED FRAME %0d",k);
  n<=n+1;
 end
end
task marker;begin @(negedge sc);de=0;vs=1;repeat(4)@(negedge sc);vs=0;end endtask
task pixels(input integer count,input integer base);integer x;begin
 for(x=0;x<count;x=x+1)begin @(negedge sc);de=1;pix=base+x;end
 @(negedge sc);de=0;repeat(20)@(negedge sc);
end endtask
initial begin
 repeat(5)@(negedge sc);rstn=1;
 marker;pixels(2000,16'h2000); // DDR blocked until the input FIFO fills
 if(!dut.src_error)$fatal(1,"FIFO FULL NOT EXERCISED");
 allow=1;repeat(600)@(negedge sc);
 if(n!=0)$fatal(1,"TRUNCATED FRAME PUBLISHED");
 marker;pixels(2048,16'h4000);repeat(200)@(negedge sc);
 if(n!=1||seq!=1||!fvalid||!ovf)$fatal(1,"CAPTURE OVERFLOW END n=%0d seq=%0d error=%b",n,seq,ovf);
 $display("CAPTURE_OVERFLOW PASS: stalled DDR fills FIFO, bad frame discarded, next complete frame recovers exactly");$finish;
end
initial begin #1000000;$fatal(1,"TIMEOUT CAPTURE OVERFLOW");end
endmodule
