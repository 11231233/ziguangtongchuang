`timescale 1ns/1ps
// Actual top integration. Vendor DDR/PLL are black boxes; DDR sink is modeled.
module tb_key_angle_top;
 reg clk=0,pclk=0,rst=0,hs=0,vs=0,rx=1,fs=0,fv=0,osd_de=0;
 reg [11:0] osd_x=16,osd_y=16;
 reg [7:0] data=0;reg key6=1,key7=1,key1=1,key0=1,key2=1,key3=1;
 always #5 clk=~clk;always #12 pclk=~pclk;
 wire tx;
 top_pangu50 #(.H_ACT(256),.V_ACT(4)) dut(.sys_clk(clk),.host_rx(rx),.host_tx(tx),
  .key0(key0),.key1(key1),.key2(key2),.key3(key3),.key4(1'b1),.key5(1'b1),.key6(key6),.key7(key7),
  .cam_pclk(pclk),.cam_hs(hs),.cam_vs(vs),.cam_d(data));
 defparam dut.u_key6.DEBOUNCE_CYCLES=3;
 defparam dut.u_host_rx.CLK_HZ=2000,dut.u_host_rx.BAUD=100;
 defparam dut.u_quality_key.DEBOUNCE_CYCLES=3,dut.u_quality_key.LONG_CYCLES=30,dut.u_quality_key.PULSE_CYCLES=10;
 defparam dut.u_key1.DEBOUNCE_CYCLES=3,dut.u_key1.LONG_CYCLES=30,dut.u_key1.PULSE_CYCLES=10;
 defparam dut.u_freeze.DEBOUNCE_CYCLES=3;
 defparam dut.u_controls.DEBOUNCE_CYCLES=3,dut.u_controls.REPEAT_DELAY=500,dut.u_controls.REPEAT_PERIOD=20,dut.u_controls.RESET_HOLD=80;
 defparam dut.u_key0.DEBOUNCE_CYCLES=3,dut.u_key0.LONG_CYCLES=30,dut.u_key0.PULSE_CYCLES=10;
 reg ready=0,adv=0,done=0;integer bus_tick=0,beat=0,burst=0,received=0,j;
 reg busy=0;reg [15:0] expected_pixel;
 function [15:0] sensor_word(input integer n);begin sensor_word=(n*53)^16'ha53c;end endfunction
 function [15:0] rgb_word(input integer n);reg [15:0] w;begin w=sensor_word(n);rgb_word={w[4:0],w[10:5],w[15:11]};end endfunction
 always @(negedge clk)begin
  bus_tick=bus_tick+1;ready=rst&&!busy&&(bus_tick%3!=0);adv=rst&&busy&&(beat<16)&&(bus_tick%5!=0);done=rst&&busy&&(beat==16);
 end
 always @(posedge clk)if(rst)begin
  if(dut.src_de)begin
   if(dut.src_rgb565!==rgb_word(received))$fatal(1,"C1 direct capture pixel %0d",received);
   received=received+1;
  end
  if(dut.cap_m_req&&ready)begin
   if(dut.cap_m_addr!==(3-burst)*128 || dut.cap_m_beats!==16)$fatal(1,"Single source ring address/vertical flip");
   busy=1;beat=0;
  end else if(adv)begin
   for(j=0;j<16;j=j+1)begin
    expected_pixel=rgb_word(burst*256+beat*16+j);
    if(dut.cap_m_data[j*16+:16]!==expected_pixel)$fatal(1,"DDR data burst=%0d beat=%0d pixel=%0d",burst,beat,j);
   end
   beat=beat+1;
  end else if(done)begin busy=0;burst=burst+1;end
 end
 task byte_in(input [7:0] b);begin @(negedge pclk);#1;data=b;end endtask
 task serial_byte(input [7:0] b);integer k;begin
  @(negedge clk);rx=0;repeat(20)@(negedge clk);
  for(k=0;k<8;k=k+1)begin rx=b[k];repeat(20)@(negedge clk);end
  rx=1;repeat(24)@(negedge clk);
 end endtask
 reg [7:0] packet[0:61];reg [447:0] coeff[0:0];integer n;reg [15:0] w;
 initial begin
  force dut.ddr_clk=clk;force dut.clk_pix=clk;
  force dut.ddr_init_done=rst;force dut.rstn_pix=rst;force dut.rstn_cap_ddr=rst;force dut.rstn_pclk=rst;
  force dut.cap_m_ready=ready;force dut.cap_m_adv=adv;force dut.cap_m_done=done;
  force dut.accept_source=fs;force dut.wp_start=1'b0;
  force dut.vs_aligned=fv;force dut.de_aligned=osd_de;
  force dut.x_aligned=osd_x;force dut.y_aligned=osd_y;
  $readmemh("sim/out/host_packet.hex",packet);$readmemh("sim/out/host_coeff.hex",coeff);
  repeat(10)@(negedge clk);rst=1;repeat(20)@(negedge clk);
  if(dut.display_quality!==2||dut.host_active!==0||dut.freeze_wanted!==0)$fatal(1,"Boot defaults");
  // No C2 clocks or signals exist. A single DVP frame must complete by itself.
  @(negedge pclk);#1;vs=1;repeat(5)@(negedge pclk);#1;vs=0;
  repeat(5)@(negedge pclk);
  for(n=0;n<1024;n=n+1)begin
   w=sensor_word(n);byte_in(w[15:8]);hs=1;byte_in(w[7:0]);
   if(n%256==255)begin @(negedge pclk);#1;hs=0;repeat(8)@(negedge pclk);end
  end
  repeat(1000)@(negedge clk);
  if(received!=1024||burst!=4||!dut.fw_frame_valid||dut.fw_frame_seq!=1||dut.fw_ovf)$fatal(1,"Single capture incomplete");
  // KEY6 cannot select a missing C2 or fusion path.
  key6=0;repeat(120)@(negedge clk);key6=1;repeat(20)@(negedge clk);
  if(dut.u_osd.camera_selected!==0||dut.u_osd.fusion_enabled!==0)$fatal(1,"Not locked to C1");
  osd_de=1;osd_y=144;repeat(2)@(negedge clk);#1;if(!dut.osd_overlay)$fatal(1,"C1 diagnostics missing");
  osd_y=128;#1;if(!dut.osd_overlay)$fatal(1,"Q label missing");
  osd_y=112;osd_x=144;#1;if(dut.u_osd.character!=="C")$fatal(1,"C1 label C");
  osd_x=160;#1;if(dut.u_osd.character!=="1")$fatal(1,"C1 label 1");
  osd_x=176;#1;if(dut.u_osd.character!=="R")$fatal(1,"Diagnostic decode label missing");
  osd_de=0;
  for(n=0;n<62;n=n+1)serial_byte(packet[n]);
  if(dut.host_active)$fatal(1,"Host committed before frame boundary");
  fs=1;repeat(2)@(negedge clk);fs=0;repeat(2)@(negedge clk);
  if(dut.host_active || dut.host_sequence!=0 || dut.WP_A!==dut.PRE_A || dut.WP_K1!==dut.PRE_K1)$fatal(1,"Standalone must reject host override");
  if(dut.u_warp_frame.AFFINE_FRAC_BITS!=24 || dut.u_warp_frame.u_bbox.AFFINE_FRAC_BITS!=24)$fatal(1,"Slope format not connected");
  key2=0;repeat(12)@(negedge clk);key2=1;repeat(20)@(negedge clk);
  if(dut.active_angle!==0)$fatal(1,"Angle changed before source boundary");
  fs=1;@(negedge clk);fs=0;repeat(8)@(negedge clk);
  if(dut.active_angle!==1 || dut.WP_B>=0 || dut.WP_D<=0)$fatal(1,"Plus routing");
  fv=1;@(negedge clk);fv=0;repeat(2)@(negedge clk);
  osd_de=1;osd_y=128;osd_x=80;#1;if(dut.u_osd.character!=="A")$fatal(1,"OSD A label");
  osd_x=112;#1;if(dut.u_osd.character!=="+")$fatal(1,"OSD angle sign");
  osd_x=160;#1;if(dut.u_osd.character!=="1")$fatal(1,"OSD applied angle");osd_de=0;
  key3=0;repeat(12)@(negedge clk);key3=1;repeat(20)@(negedge clk);
  fs=1;@(negedge clk);fs=0;repeat(8)@(negedge clk);if(dut.active_angle!==0)$fatal(1,"Minus routing");
  key0=0;repeat(100)@(negedge clk);key0=1;repeat(25)@(negedge clk);
  fs=1;@(negedge clk);fs=0;repeat(8)@(negedge clk);
  if(dut.local_zoom_active!==1 || !dut.local_correction_active)$fatal(1,"Long KEY0 zoom or short isolation");
  key0=0;repeat(12)@(negedge clk);key0=1;repeat(30)@(negedge clk);
  fs=1;@(negedge clk);fs=0;repeat(8)@(negedge clk);if(dut.local_correction_active || dut.WP_K1!==0)$fatal(1,"Short KEY0 RAW");
  key2=0;key3=0;repeat(120)@(negedge clk);key2=1;repeat(20)@(negedge clk);key3=1;repeat(20)@(negedge clk);
  fs=1;@(negedge clk);fs=0;repeat(8)@(negedge clk);
  if(dut.active_angle!==0 || dut.local_zoom_active!==0 || !dut.local_correction_active)$fatal(1,"Chord default/reset and staggered release");
  // Quality change remains frame atomic and reset restores Q2.
  key7=0;repeat(100)@(negedge clk);key7=1;repeat(20)@(negedge clk);
  if(dut.display_quality!==2)$fatal(1,"Quality changed mid-frame");
  fv=1;repeat(3)@(negedge clk);fv=0;repeat(3)@(negedge clk);
  if(dut.display_quality!==3)$fatal(1,"Q2 to Q3");
  key1=0;repeat(100)@(negedge clk);key1=1;repeat(20)@(negedge clk);
  if(!dut.freeze_wanted)$fatal(1,"Freeze key lost");
  rst=0;repeat(10)@(negedge clk);rst=1;repeat(10)@(negedge clk);
  if(dut.display_quality!==2||dut.host_active!==0||dut.freeze_wanted!==0)$fatal(1,"Reset restoration");
  $display("KEY_ANGLE_TOP PASS 1024 DVP pixels, 64 stalled DDR beats, vertical flip, C1 lock, standalone rejects UART override, Q2 and freeze");$finish;
 end
 initial begin #2000000;$fatal(1,"Timeout");end
endmodule
