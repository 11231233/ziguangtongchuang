`timescale 1ns/1ps
module tb_sensor_diag;
 reg clk=0,rst=0,vs=0,k1=1,k4=1,k5=1,k6=1,txbit=1,rxbyte=0;
 always #5 clk=~clk;
 reg [11:0] x=16,y=16;
 top_pangu50 dut(.sys_clk(clk),.host_rx(1'b1),.key0(1'b1),.key1(k1),.key2(1'b1),.key3(1'b1),.key4(k4),.key5(k5),.key6(k6),.key7(1'b1),
 .cam_pclk(clk),.cam_vs(vs),.cam_hs(1'b0),.cam_d(8'd0));
 defparam dut.u_key1.DEBOUNCE_CYCLES=3,dut.u_key1.LONG_CYCLES=30,dut.u_key1.PULSE_CYCLES=10;
 defparam dut.u_key4.DEBOUNCE_CYCLES=3,dut.u_key4.LONG_CYCLES=30,dut.u_key4.PULSE_CYCLES=10;
 defparam dut.u_key5.DEBOUNCE_CYCLES=3,dut.u_key5.LONG_CYCLES=30,dut.u_key5.PULSE_CYCLES=10;
 defparam dut.u_key6.DEBOUNCE_CYCLES=3,dut.u_key6.LONG_CYCLES=30,dut.u_key6.PULSE_CYCLES=10;
 defparam dut.u_freeze.DEBOUNCE_CYCLES=3;
 task boundary;begin vs=1;repeat(12)@(negedge clk);vs=0;repeat(12)@(negedge clk);end endtask
 task checkchar(input integer row,col,input [7:0] expected);begin
  y=16+16*row;x=16+16*col;repeat(2)@(negedge clk);#1;
  if(dut.u_osd.character!==expected)$fatal(1,"OSD row=%0d col=%0d got=%h exp=%h",row,col,dut.u_osd.character,expected);
 end endtask
 integer i;
 initial begin
  force dut.ddr_clk=clk;force dut.clk_pix=clk;force dut.clk_25m=clk;
  force dut.ddr_init_done=rst;force dut.rstn_pix=rst;force dut.rstn_pclk=rst;force dut.rstn_cap_ddr=rst;
  force dut.cam_rstn_int=rst;force dut.cam_init_en=1'b0;
  force dut.probe_vs=vs;force dut.vs_aligned=vs;force dut.de_aligned=1'b1;
  force dut.x_aligned=x;force dut.y_aligned=y;force dut.bar_active=dut.bar_request;
  force dut.host_tx=txbit;force dut.host_byte_valid=rxbyte;
  repeat(8)@(negedge clk);rst=1;repeat(10)@(negedge clk);
  if(dut.decode_active!==0 || dut.phase_active!==0 || dut.bar_request!==0)$fatal(1,"Diagnostic boot");
  k4=0;repeat(14)@(negedge clk);k4=1;repeat(14)@(negedge clk);
  if(dut.decode_request!==1 || dut.decode_active!==0)$fatal(1,"Decode update not frame atomic");
  boundary;if(dut.decode_active!==1)$fatal(1,"Decode not committed at VS");
  k6=0;repeat(14)@(negedge clk);k6=1;repeat(14)@(negedge clk);
  if(dut.phase_request!==1 || dut.phase_active!==0)$fatal(1,"Phase changed before blanking");
  boundary;if(dut.phase_active!==1)$fatal(1,"Phase did not commit");
  k6=0;repeat(100)@(negedge clk);k6=1;repeat(25)@(negedge clk);
  if(dut.freeze_wanted || dut.phase_request!==1)$fatal(1,"Held KEY6 unexpectedly freezes or switches phase");
  k5=0;repeat(100)@(negedge clk);k5=1;repeat(25)@(negedge clk);
  if(dut.bar_request!==1 || dut.gamma_test_ddr!==0)$fatal(1,"Long key5 accidentally changes stimulus");
  k1=0;repeat(100)@(negedge clk);k1=1;repeat(25)@(negedge clk);
  if(!dut.freeze_wanted)$fatal(1,"Freeze request");
  k6=0;repeat(14)@(negedge clk);k6=1;repeat(14)@(negedge clk);boundary;
  if(dut.freeze_wanted)$fatal(1,"Diagnostic context did not unfreeze");
  for(i=0;i<8;i=i+1)begin txbit=~txbit;repeat(2)@(negedge clk);end
  for(i=0;i<3;i=i+1)begin rxbyte=1;@(negedge clk);rxbyte=0;repeat(2)@(negedge clk);end
  if(dut.tx_edges!==8 || dut.rx_bytes!==3)$fatal(1,"UART diagnostic counters");
  force dut.camera_probe_visible={1'b1,16'hab12,20'he1000,8'hff,16'h0000,16'hfbfb,128'h0123456789abcdef13572468aaaa5555};
  checkchar(10,0,"0");checkchar(10,2,"5");checkchar(10,7,"A");
  checkchar(13,0,"6");checkchar(13,2,"4");checkchar(13,7,"0");
  checkchar(14,0,"O");checkchar(14,1,"F");checkchar(14,2,"B");checkchar(14,6,"A");checkchar(14,7,"0");
  checkchar(15,0,"V");if(dut.u_osd.bitmap==0)$fatal(1,"Missing V glyph");checkchar(15,1,"1");checkchar(15,4,"F");checkchar(15,7,"E");
  checkchar(16,0,"T");checkchar(16,1,"A");checkchar(16,2,"B");checkchar(16,4,"R");checkchar(16,5,"1");checkchar(16,6,"2");
  y=288;repeat(2)@(negedge clk);#1;if(dut.osd_overlay)$fatal(1,"Diagnostic overlay boundary");
  rst=0;repeat(10)@(negedge clk);rst=1;repeat(10)@(negedge clk);
  if(dut.decode_active!==0 || dut.phase_request!==0 || dut.bar_request!==0 || dut.tx_edges!==0 || dut.rx_bytes!==0)$fatal(1,"Diagnostic reset");
  $display("SENSOR_DIAG PASS C1 decode and phase at VS, native-bar key isolation, freeze invalidation, UART counters, all diagnostic OSD fields and reset");$finish;
 end
 initial begin #100000;$fatal(1,"Diagnostic timeout");end
endmodule
