`timescale 1ns/1ps
module tb_warp_scheduler;
 reg clk=0,rstn=0,wanted=0,valid=0,done=0,ovf=0,shown=0,shownslot=0;
 reg [31:0] seq=0;reg[2:0] slot=0;always #5 clk=~clk;
 wire accept,start,hold,dst,front,have,frozen,display_frozen;wire[2:0] held;wire[27:0] src;
 warp_scheduler #(.SLOT_WORDS(100)) dut(.clk(clk),.rstn(rstn),.freeze_wanted(wanted),.frame_valid(valid),.frame_seq(seq),.frame_slot(slot),
  .process_done(done),.process_overflow(ovf),.display_seen(shown),.display_slot(shownslot),.accept_source(accept),.process_start(start),
  .source_base(src),.read_hold(hold),.read_slot(held),.destination_slot(dst),.front_slot(front),.have_frame(have),.frozen(frozen),.display_frozen(display_frozen));
 task tick;begin @(negedge clk);#1;end endtask
 task complete;begin done=1;tick;done=0;end endtask
 task acknowledge;begin shown=1;shownslot=front;tick;shown=0;end endtask
 integer i;
 initial begin
  repeat(4)tick;rstn=1;tick;if(accept||start||hold||have)$fatal(1,"EMPTY START");
  valid=1;seq=1;slot=2;tick;if(!start||!hold||held!=2||src!=200)$fatal(1,"SOURCE PIN");
  wanted=1;repeat(4)tick;complete;
  if(!frozen||!hold||!have||display_frozen)$fatal(1,"FREEZE BEFORE DISPLAY ACK");
  shown=1;shownslot=~front;repeat(3)tick;if(accept)$fatal(1,"REUSED FRONT TOO SOON");shown=0;
  acknowledge;if(!display_frozen)$fatal(1,"DISPLAY HOLD ACK");
  for(i=0;i<12;i=i+1)begin
   seq=seq+1;slot=(i%6);tick;
   if(!start||src!=200||held!=2||!hold)$fatal(1,"FROZEN SOURCE CHANGED");
   tick;complete;if(!hold)$fatal(1,"RELEASED FROZEN SLOT");acknowledge;
  end
  tick;if(!start)$fatal(1,"FROZEN REPEAT");
  wanted=0;tick;if(!hold||display_frozen)$fatal(1,"RELEASED WHILE READ ACTIVE");
  complete;if(hold||frozen)$fatal(1,"LIVE SOURCE NOT RELEASED");acknowledge;
  seq=99;slot=4;tick;if(!start||src!=400||held!=4)$fatal(1,"LIVE DID NOT CATCH UP");
  tick;complete;acknowledge;repeat(3)tick;if(start||accept||hold)$fatal(1,"DUPLICATE LIVE FRAME");
  wanted=1;repeat(3)tick;if(frozen||accept)$fatal(1,"PINNED STALE UNPROTECTED FRAME");
  seq=100;slot=5;tick;if(!start||!hold||src!=500)$fatal(1,"WAIT FOR FRESH FREEZE");
  tick;ovf=1;complete;if(hold||frozen||display_frozen||front!=0)$fatal(1,"OVERFLOW FRONT OR HOLD");
  seq=101;repeat(5)tick;if(start||accept)$fatal(1,"ERROR DID NOT STOP");
  rstn=0;tick;if(have||hold||frozen||display_frozen)$fatal(1,"RESET");
  $display("WARP_SCHEDULER PASS: live frames, mid-render freeze, 12 same-source rerenders, display retirement, safe release, fresh-only pinning and overflow");$finish;
 end
 initial begin #100000;$fatal(1,"SCHEDULER TIMEOUT");end
endmodule
