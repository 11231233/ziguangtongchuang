`timescale 1ns/1ps
// Control integration with vendor primitives black-boxed, not a board/IP model.
module tb_dual_q2_boot;
 reg clk=0,rst=0,frame_vs=0,key6=1,key7=1,key5=1;always #5 clk=~clk;
 top_pangu50 dut(.sys_clk(clk),.host_rx(1'b1),
  .key0(1'b1),.key1(1'b1),.key2(1'b1),.key3(1'b1),.key4(1'b1),.key5(key5),.key6(key6),.key7(key7));
 defparam dut.u_stereo_controls.DEBOUNCE_CYCLES=3;
 defparam dut.u_key6.DEBOUNCE_CYCLES=3;
 defparam dut.u_key6.LONG_CYCLES=30;
 defparam dut.u_key6.PULSE_CYCLES=10;
 defparam dut.u_key5.DEBOUNCE_CYCLES=3;
 defparam dut.u_key5.LONG_CYCLES=30;
 defparam dut.u_key5.PULSE_CYCLES=10;
 defparam dut.u_quality_key.DEBOUNCE_CYCLES=3;
 defparam dut.u_quality_key.LONG_CYCLES=30;
 defparam dut.u_quality_key.PULSE_CYCLES=10;
 task press6;begin key6=0;repeat(14)@(negedge clk);key6=1;repeat(14)@(negedge clk);end endtask
 task check_boot;begin
  if(dut.stereo_mode!==0 || dut.format2_active!==0 || dut.display_quality!==2)
   $fatal(1,"BOOT DEFAULTS mode=%0d format=%0d Q=%0d",dut.stereo_mode,dut.format2_active,dut.display_quality);
  if(dut.freeze_context_previous!==10'd0 || dut.freeze_wanted!==0)
   $fatal(1,"BOOT FREEZE CONTEXT");
 end endtask
 initial begin
  force dut.ddr_clk=clk;force dut.clk_pix=clk;
  force dut.ddr_init_done=rst;force dut.rstn_pix=rst;
  force dut.c2_phase_active=dut.c2_phase_request;force dut.c2_bar_active=dut.c2_bar_request;
  force dut.vs_aligned=frame_vs;force dut.de_aligned=1'b0;
  repeat(6)@(negedge clk);check_boot;rst=1;repeat(6)@(negedge clk);check_boot;
  press6;if(dut.stereo_mode!==1)$fatal(1,"FUSION TO C1");
  press6;if(dut.stereo_mode!==2)$fatal(1,"C1 TO C2");
  press6;if(dut.stereo_mode!==0)$fatal(1,"C2 TO FUSION");
  key6=0;repeat(100)@(negedge clk);key6=1;repeat(25)@(negedge clk);
  if(dut.stereo_mode!==0 || dut.c2_phase_request!==1)$fatal(1,"LONG KEY6 PHASE ONLY");
  key5=0;repeat(100)@(negedge clk);key5=1;repeat(25)@(negedge clk);
  if(dut.c2_bar_request!==1 || dut.stereo_mode!==0)$fatal(1,"LONG KEY5 SENSOR BAR ONLY");
  key7=0;repeat(100)@(negedge clk);key7=1;repeat(20)@(negedge clk);
  if(dut.display_quality!==2 || dut.u_quality_display.wanted!==0)$fatal(1,"Q2 REQUEST MUST WAIT VS");
  frame_vs=1;repeat(3)@(negedge clk);frame_vs=0;repeat(3)@(negedge clk);
  if(dut.display_quality!==0)$fatal(1,"Q2 TO Q0 AT VS");
  press6;rst=0;repeat(6)@(negedge clk);check_boot;
  rst=1;repeat(6)@(negedge clk);check_boot;
  $display("DUAL_Q2_BOOT PASS actual top fusion/Q2 defaults, C1/C2 fallback keys, frame-atomic quality and reset restoration");$finish;
 end
endmodule
