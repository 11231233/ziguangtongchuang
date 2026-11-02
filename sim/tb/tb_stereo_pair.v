`timescale 1ns/1ps
module tb_stereo_pair;
reg clk=0,rstn=0;always #5 clk=~clk;
reg [1:0]mode=0,fd=0,fv=0;reg[2:0]s0=0,s1=0;reg[31:0]q0=0,q1=0;
reg busy=0,done=0;wire start,hold_frames;wire[2:0]h0,h1;wire[27:0]b0,b1;wire[1:0]active;wire[20:0]lastf;
stereo_pair_select #(.WAIT_CYCLES(10),.AGE_CYCLES(30)) dut(.clk(clk),.rstn(rstn),.mode(mode),.frame_done(fd),.frame_valid(fv),.slot0(s0),.slot1(s1),.seq0(q0),.seq1(q1),.busy(busy),.done(done),.fused_pixels(21'd123),.start(start),.hold_frames(hold_frames),.hold0(h0),.hold1(h1),.base0(b0),.base1(b1),.active_mode(active),.last_fused_pixels(lastf));
task tick;begin @(negedge clk);#1;end endtask
integer starts=0;always @(posedge clk)if(start)begin starts=starts+1;busy<=1;end
task finish;begin tick;done=1;tick;done=0;busy=0;tick;end endtask
initial begin
 repeat(4)tick;rstn=1;tick;fv=1;q0=1;fd=1;s0=2;tick;fd=0;
 repeat(3)begin tick;if(start||starts)$fatal(1,"LEFT CONSUMED BEFORE RIGHT");end
 fv=3;q1=1;fd=2;s1=3;tick;fd=0;repeat(3)tick;
 if(starts!=1||active!=0||!hold_frames||h0!=2||h1!=3||b0!=4921600||b1!=9382400)$fatal(1,"PAIR PINNING");
 s0=4;s1=5;q0=2;q1=2;fd=3;tick;fd=0;repeat(3)tick;
 if(h0!=2||h1!=3||starts!=1)$fatal(1,"CHANGED PINNED SLOTS");
 finish;repeat(3)tick;if(starts!=2||h0!=4||h1!=5)$fatal(1,"LATEST PAIR NOT CONSUMED");
 finish;repeat(35)tick;
 q0=3;fd=1;tick;fd=0;repeat(14)tick;
 if(starts!=3||active!=1)$fatal(1,"MISSING RIGHT FALLBACK");
 finish;mode=2;q1=3;fd=2;tick;fd=0;repeat(4)tick;
 if(starts!=4||active!=2)$fatal(1,"RIGHT SOLO");finish;
 if(lastf!=123)$fatal(1,"FUSION STATUS");
 $display("STEREO_PAIR PASS: staggered completions, timestamp wait, missing-right fallback, pinned slots, independent solo modes");$finish;
end
initial begin #100000;$fatal(1,"PAIR TIMEOUT");end
endmodule
