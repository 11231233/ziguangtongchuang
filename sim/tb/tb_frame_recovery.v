`timescale 1ns/1ps
module tb_frame_recovery;
reg sc=0,dc=0,rstn=0,vs=0,de=0;reg[15:0]pix=0;
always #10 sc=~sc;always #5 dc=~dc;
wire req,ready,done,adv,ovf,fd,fvalid;wire[27:0]addr;wire[7:0]beats;wire[255:0]data;wire[2:0]slot,fs;wire[31:0]seq;
frame_writer #(.H_ACT(256),.V_ACT(2),.SLOT_WORDS(256)) dut(
.src_clk(sc),.src_rstn(rstn),.src_vs(vs),.src_de(de),.src_pix(pix),.ddr_clk(dc),.ddr_rstn(rstn),
.w_req(req),.w_addr(addr),.w_beats(beats),.w_ready(ready),.w_done(done),.w_data(data),.w_adv(adv),.wr_slot(slot),.led_overflow(ovf),
.hold_valid(1'b0),.hold_slot(3'd0),.frame_done(fd),.frame_valid(fvalid),.frame_slot(fs),.frame_seq(seq));
reg busy=0;integer b=0,tail=0,k,a=0,n=0,f;reg[15:0]mem[0:3071];
assign ready=!busy;assign adv=busy&&tail==0;assign done=tail==1;
always @(posedge dc)begin
 if(req&&ready)begin a<=addr;b<=0;busy<=1;if(beats!=16 || addr+128>1536)$fatal(1,"RANGE");end
 if(adv)begin
  for(k=0;k<16;k=k+1)mem[a*2+b*16+k]<=data[k*16+:16];
  if(b==15)tail<=3;else b<=b+1;
 end
 if(tail>0)begin tail<=tail-1;if(tail==1)busy<=0;end
 if(fd)begin
  if(n>=2)$fatal(1,"BAD FRAME PUBLISHED");
  for(k=0;k<512;k=k+1)if(mem[fs*512+k]!==16'h4000+n*1024+k)$fatal(1,"MIXED FRAME n=%0d x=%0d got=%h",n,k,mem[fs*512+k]);
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
 pixels(96,16'h1000); // reset released in the middle of a camera frame
 marker;pixels(80,16'h2000); // five beats: marker must not be sent inside a 16-beat burst
 marker;pixels(300,16'h3000); // one full chunk plus a partial chunk
 marker;pixels(512,16'h4000);
 marker;pixels(512,16'h4400);
 repeat(150)@(negedge sc);
 for(f=0;f<9;f=f+1)begin marker;pixels(300,16'h6000);end
 repeat(150)@(negedge sc);
 for(f=0;f<512;f=f+1)if(mem[fs*512+f]!==16'h4400+f)$fatal(1,"LAST COMPLETE FRAME OVERWRITTEN");
 if(n!=2||seq!=2||!fvalid||!ovf)$fatal(1,"RECOVERY END completed=%0d seq=%0d error=%b",n,seq,ovf);
 $display("FRAME_RECOVERY PASS: pre-VS pixels discarded, truncated chunks isolated, clean frames recover with sticky diagnostic");$finish;
end
initial begin #1000000;$fatal(1,"TIMEOUT RECOVERY");end
endmodule
