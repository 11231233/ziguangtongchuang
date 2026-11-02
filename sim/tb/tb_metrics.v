`timescale 1ns/1ps
module tb_metrics;
 reg clk=0,pclk=0,rstn=0,sd=0,ps=0,pd=0;
 always #5 clk=~clk;always #7 pclk=~pclk;
 reg [5:0] mode_status=6'h19;wire [85:0] snap;wire toggle;
 video_metrics #(.CLK_HZ(10000)) metrics(.clk(clk),.rstn(rstn),.source_done(sd),
  .process_start(ps),.process_done(pd),.mode_status(mode_status),.pclk_rate_bcd(16'h0210),.focus_bcd(16'h1234),.gamma_status(2'd2),.test_mode(2'd1),.mean_luma_bcd(8'h32),.snapshot(snap),.snapshot_toggle(toggle));
 reg vs=0,de=1,key_n=1,camera_selected=0,fusion_enabled=0,fusion_used=0,frozen=0;reg[1:0]format2=0;reg [11:0] x=0,y=0;
 wire [15:0] result;wire enabled;
 metrics_osd #(.DEBOUNCE_CYCLES(3)) osd(.clk(pclk),.rstn(rstn),.vs(vs),.de(de),.key_n(key_n),.camera_selected(camera_selected),.fusion_enabled(fusion_enabled),.fusion_used(fusion_used),.format2(format2),.display_quality(2'd1),.frozen(frozen),
  .x(x),.y(y),.pixel(16'h35ad),.snapshot(snap),.snapshot_toggle(toggle),.result(result),.enabled(enabled));
 task boundary;begin @(negedge pclk);vs=1;@(negedge pclk);vs=0;@(negedge pclk);end endtask
 task press;begin @(negedge pclk);key_n=0;repeat(12)@(negedge pclk);end endtask
 task release_key;begin key_n=1;repeat(12)@(negedge pclk);end endtask
 integer n,fd,ix,iy;reg [85:0] previous;
 initial begin
  repeat(5)@(negedge clk);rstn=1;
  for(n=0;n<10000;n=n+1)begin
   sd=(n%1000==999);ps=(n==2000);pd=(n==2400);@(negedge clk);
  end
  sd=0;ps=0;pd=0;
  if(snap!=={2'd1,8'h32,2'd2,16'h1234,16'h0210,6'h19,36'h010001040} || toggle!==1)$fatal(1,"METRIC WINDOW snap=%h",snap);
  repeat(8)@(negedge pclk);
  if(osd.visible!==0)$fatal(1,"METRICS CHANGED WITHIN FRAME");boundary;
  if(osd.visible!==snap || !enabled)$fatal(1,"SNAPSHOT CDC");
  x=0;y=0;#1;if(result!==16'h35ad)$fatal(1,"OUTSIDE REGION MODIFIED");
  x=20;y=16;#1;if(result!==16'hffff)$fatal(1,"FONT FOREGROUND");
  x=16;#1;if(result!==16'h0000)$fatal(1,"FONT BACKGROUND");
  de=0;#1;if(result!==16'h35ad)$fatal(1,"BLANKING MODIFIED");de=1;
  // Status uses the same atomic CDC snapshot and changes only at VS.
  y=64;x=16;#1;if(osd.character!=="C")$fatal(1,"COR MODE LABEL");
  x=96;#1;if(osd.character!=="2")$fatal(1,"ACTIVE STRENGTH");
  x=192;#1;if(osd.character!=="0")$fatal(1,"LIVE HOLD FLAG");
  frozen=1;repeat(8)@(negedge pclk);#1;if(osd.character!=="0")$fatal(1,"HOLD FLAG MIDFRAME");
  boundary;#1;if(osd.character!=="1")$fatal(1,"HOLD FLAG CDC");
  x=144;#1;if(osd.character!=="1")$fatal(1,"ACTIVE ZOOM");
  mode_status=0;repeat(8000)@(negedge pclk);
  if(osd.visible[41:36]!==6'h19)$fatal(1,"MODE CHANGED MIDFRAME");boundary;
  x=16;y=64;#1;if(osd.character!=="R")$fatal(1,"RAW MODE LABEL");
  mode_status=6'h20;repeat(8000)@(negedge pclk);boundary;
  #1;if(osd.character!=="H")$fatal(1,"HOST MODE LABEL");
  x=96;#1;if(osd.character!=="-")$fatal(1,"HOST LOCAL PRESET MISLABELED");
  mode_status=6'h19;repeat(8000)@(negedge pclk);boundary;
  y=80;x=80;#1;if(osd.character!=="0")$fatal(1,"PCLK HUNDREDS");
  x=96;#1;if(osd.character!=="2")$fatal(1,"PCLK TENS");
  x=112;#1;if(osd.character!=="1")$fatal(1,"PCLK UNITS");
  x=128;#1;if(osd.character!==".")$fatal(1,"PCLK DECIMAL");
  x=144;#1;if(osd.character!=="0")$fatal(1,"PCLK TENTHS");
  y=96;x=80;#1;if(osd.character!=="1")$fatal(1,"FOCUS THOUSANDS");
  x=96;#1;if(osd.character!=="2")$fatal(1,"FOCUS HUNDREDS");
  x=112;#1;if(osd.character!=="3")$fatal(1,"FOCUS TENS");
  x=128;#1;if(osd.character!=="4")$fatal(1,"FOCUS UNITS");
  x=160;#1;if(osd.character!=="G")$fatal(1,"GAMMA LABEL");
  x=176;#1;if(osd.character!=="2")$fatal(1,"GAMMA STATUS");
  y=112;x=16;#1;if(osd.character!=="Y")$fatal(1,"LUMA LABEL");
  x=48;#1;if(osd.character!=="3")$fatal(1,"LUMA TENS");
  x=64;#1;if(osd.character!=="2")$fatal(1,"LUMA UNITS");
  x=96;#1;if(osd.character!=="T")$fatal(1,"TEST LABEL");
  x=112;#1;if(osd.character!=="1")$fatal(1,"TEST MODE");
  x=144;y=112;#1;if(osd.character!=="C")$fatal(1,"CAMERA LABEL");
  x=160;#1;if(osd.character!=="1")$fatal(1,"CAMERA1 LABEL");
  camera_selected=1;repeat(8)@(negedge pclk);
  #1;if(osd.character!=="1")$fatal(1,"CAMERA LABEL CHANGED MIDFRAME");
  boundary;#1;if(osd.character!=="2")$fatal(1,"CAMERA2 LABEL CDC");
  fusion_enabled=1;format2=2;repeat(8)@(negedge pclk);boundary;
  x=144;y=112;#1;if(osd.character!=="F")$fatal(1,"FUSION LABEL");
  x=160;#1;if(osd.character!=="0")$fatal(1,"FALLBACK MUST NOT CLAIM FUSED");
  x=192;#1;if(osd.character!=="2")$fatal(1,"FORMAT LABEL");
  fusion_used=1;repeat(8)@(negedge pclk);x=160;#1;if(osd.character!=="0")$fatal(1,"FUSION STATUS MIDFRAME");
  boundary;#1;if(osd.character!=="1")$fatal(1,"ACTUAL FUSION LABEL");
  // Save the actual RTL output for visual inspection of the new on-screen text.
  fd=$fopen("sim/out/metrics_osd.ppm","w");$fwrite(fd,"P3\n224 144\n255\n");
  for(iy=0;iy<144;iy=iy+1)for(ix=0;ix<224;ix=ix+1)begin
   @(negedge pclk);x=ix;y=iy;#1;
   $fwrite(fd,"%0d %0d %0d\n",{result[15:11],3'b0},{result[10:5],2'b0},{result[4:0],3'b0});
  end
  $fclose(fd);
  press;if(!enabled)$fatal(1,"ENABLE CHANGED MIDFRAME");boundary;
  x=20;y=16;#1;if(enabled || result!==16'h35ad)$fatal(1,"DISABLE PASSTHROUGH");
  repeat(30)@(negedge pclk);boundary;if(enabled)$fatal(1,"LONG PRESS REPEATED");
  release_key;press;boundary;if(!enabled)$fatal(1,"REENABLE");release_key;
  $display("METRICS PASS: source/output FPS, whole-ms duration, stable CDC, VS updates, OSD masking and debounced toggle");$finish;
 end
 initial begin #2000000;$fatal(1,"METRICS TIMEOUT");end
endmodule
