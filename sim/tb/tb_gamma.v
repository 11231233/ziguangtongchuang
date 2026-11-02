`timescale 1ns/1ps
module tb_gamma;
 reg clk=0,rstn=0,vs=0,de=0,key_n=1,test_key_n=1;
 reg [15:0] pixel=0;
 always #5 clk=~clk;
 wire vo,do_;wire [15:0] po;wire en;wire [1:0] curve,code;wire toggle;wire [1:0] test_mode;wire [7:0] mean_bcd;
 adaptive_gamma #(.WIDTH(8),.HEIGHT(4),.DEBOUNCE_CYCLES(3)) dut(
  .clk(clk),.rstn(rstn),.vs(vs),.de(de),.key_n(key_n),.test_key_n(test_key_n),.pixel(pixel),
  .vs_o(vo),.de_o(do_),.pixel_o(po),.active_enabled(en),.active_curve(curve),
  .status_code(code),.status_toggle(toggle),.active_test_mode(test_mode),.mean_luma_bcd(mean_bcd),.mean_toggle());
 reg ev,ed;reg [15:0] ep,prepared;integer monitored=0;integer r,g,b;
 always @(posedge clk)if(rstn)begin
  ev=vs;ed=de;
  r=pixel[15:11];g=pixel[10:5];b=pixel[4:0];
  if(test_mode==1)begin r=r/4;g=g/4;b=b/4;end
  if(test_mode==2)begin r=31-(31-r)/4;g=63-(63-g)/4;b=31-(31-b)/4;end
  prepared={r[4:0],g[5:0],b[4:0]};
  ep=en?{dut.gamma5(prepared[15:11],curve),dut.gamma6(prepared[10:5],curve),dut.gamma5(prepared[4:0],curve)}:prepared;
  #1;if(vo!==ev || do_!==ed || po!==ep)$fatal(1,"GAMMA PIXEL/DE/VS ALIGNMENT");
  monitored=monitored+1;
 end
 task mark;begin
  @(negedge clk);de=0;vs=1;@(negedge clk);vs=0;
 end endtask
 task frame(input integer n,input [15:0] color);integer j;begin
  mark;
  for(j=0;j<n;j=j+1)begin
   de=1;pixel=color;@(negedge clk);
   if(j%7==3)begin de=0;@(negedge clk);end
  end
  de=0;
 end endtask
 task hold_key;begin key_n=0;repeat(15)@(negedge clk);end endtask
 task release_key;begin key_n=1;repeat(15)@(negedge clk);end endtask
 integer i,c,expected,last;real exponent;
 initial begin
  // Independent real-valued Gamma definition validates every LUT entry,
  // monotonicity and exact black/white endpoints at both RGB565 precisions.
  for(c=0;c<3;c=c+1)begin
   exponent=(c==1)?0.75:(c==2)?1.25:1.0;
   last=-1;
   for(i=0;i<32;i=i+1)begin
    expected=$rtoi(31.0*$pow(i/31.0,exponent)+0.5);
    if(dut.gamma5(i,c)!==expected[4:0] || expected<last)$fatal(1,"GAMMA5 LUT");
    last=expected;
   end
   last=-1;
   for(i=0;i<64;i=i+1)begin
    expected=$rtoi(63.0*$pow(i/63.0,exponent)+0.5);
    if(dut.gamma6(i,c)!==expected[5:0] || expected<last)$fatal(1,"GAMMA6 LUT");
    last=expected;
   end
  end
  repeat(4)@(negedge clk);rstn=1;
  // Orphan pixels cannot affect frame statistics.
  de=1;pixel=16'hffff;repeat(40)@(negedge clk);de=0;
  if(dut.armed || dut.count!=0)$fatal(1,"UNARMED STATISTICS");
  for(i=0;i<4;i=i+1)frame(32,16'h8410);
  if(en || code!=0 || curve!=0)$fatal(1,"RESET MUST BYPASS");
  hold_key;
  if(en)$fatal(1,"KEY CHANGED MIDFRAME");
  frame(32,16'h8410);
  if(!en || code!=1)$fatal(1,"KEY DID NOT ENABLE AT VS");
  repeat(50)@(negedge clk);frame(32,16'h8410);
  if(!en)$fatal(1,"LONG KEY PRESS REPEATED");release_key;
  for(i=0;i<4;i=i+1)frame(32,16'h2104);
  if(curve!=1 || code!=2)$fatal(1,"DARK SCENE NOT LIFTED");
  // Single bright frame cannot change the selected curve.
  frame(32,16'he71c);frame(32,16'h2104);frame(32,16'h2104);mark;
  if(curve!=1)$fatal(1,"ONE FRAME SPIKE CHANGED CURVE");
  // Two truncated/overlong bright frames must not adapt the mode.
  frame(31,16'he71c);frame(33,16'he71c);mark;
  if(dut.estimated_curve!=1)$fatal(1,"BAD FRAME CHANGED CURVE");
  for(i=0;i<4;i=i+1)frame(32,16'he71c);
  if(curve!=2 || code!=3)$fatal(1,"BRIGHT SCENE NOT SELECTED");
  // 43/63 is inside the bright-mode exit hysteresis band.
  for(i=0;i<4;i=i+1)frame(32,{5'd21,6'd43,5'd21});
  if(curve!=2)$fatal(1,"BRIGHT HYSTERESIS");
  for(i=0;i<4;i=i+1)frame(32,16'h8410);
  if(curve!=0 || code!=1)$fatal(1,"NORMAL SCENE NOT IDENTITY");
  hold_key;frame(32,16'h8410);release_key;
  if(en || code!=0)$fatal(1,"BYPASS NOT RESTORED");
  // Full RGB565 range: default/bypass is bit exact, even outside a valid frame.
  for(i=0;i<65536;i=i+1)begin
   de=1;pixel=i;@(negedge clk);
   if(po!==pixel)$fatal(1,"BYPASS NOT BIT EXACT");
  end
  de=0;
  test_key_n=0;repeat(15)@(negedge clk);test_key_n=1;repeat(15)@(negedge clk);
  if(test_mode!=0 || en || code!=0)$fatal(1,"TEST MODE/ENABLE CHANGED MIDFRAME");
  for(i=0;i<4;i=i+1)frame(32,16'h8410);
  repeat(10)@(negedge clk);
  if(test_mode!=1 || mean_bcd!=8'h08 || curve!=1 || !en || code!=2)$fatal(1,"KEY5 DARK AUTO-ENABLE/STIMULUS/MEAN");
  // Manual bypass comparison is still available in a stimulus mode.
  hold_key;frame(32,16'h8410);release_key;
  if(en || code!=0 || test_mode!=1)$fatal(1,"KEY4 MANUAL DARK BYPASS");
  // The next KEY5 restores adaptation even after a manual bypass.
  test_key_n=0;repeat(15)@(negedge clk);test_key_n=1;repeat(15)@(negedge clk);
  for(i=0;i<4;i=i+1)frame(32,16'h8410);
  repeat(10)@(negedge clk);
  if(test_mode!=2 || mean_bcd!=8'h56 || code!=3 || !en)$fatal(1,"KEY5 BRIGHT AUTO-ENABLE/STIMULUS/MEAN");
  test_key_n=0;repeat(15)@(negedge clk);test_key_n=1;repeat(15)@(negedge clk);
  for(i=0;i<4;i=i+1)frame(32,16'h8410);
  if(test_mode!=0 || code!=0 || en)$fatal(1,"KEY5 NATURAL MODE MUST RESTORE BYPASS");
  // Held KEY5 must advance once; automatic enable does not bypass debounce.
  test_key_n=0;repeat(80)@(negedge clk);
  for(i=0;i<4;i=i+1)frame(32,16'h8410);
  if(test_mode!=1 || !en || code!=2)$fatal(1,"HELD KEY5 REPEATED OR FAILED");
  test_key_n=1;repeat(15)@(negedge clk);
  // Simultaneous debounced edges: KEY5's bright test takes precedence over
  // KEY4's attempted disable, with no mid-frame activation.
  key_n=0;test_key_n=0;repeat(15)@(negedge clk);
  if(test_mode!=1 || !en || code!=2)$fatal(1,"COMBINED KEY EDGE CHANGED MIDFRAME");
  key_n=1;test_key_n=1;repeat(15)@(negedge clk);
  for(i=0;i<4;i=i+1)frame(32,16'h8410);
  if(test_mode!=2 || !en || code!=3)$fatal(1,"KEY5 PRIORITY OVER KEY4");
  test_key_n=0;repeat(15)@(negedge clk);test_key_n=1;repeat(15)@(negedge clk);
  for(i=0;i<4;i=i+1)frame(32,16'h8410);
  if(test_mode!=0 || en || code!=0)$fatal(1,"FINAL NATURAL BYPASS RESTORE");
  de=0;@(negedge clk);rstn=0;repeat(3)@(negedge clk);
  if(en || code || po || vo || do_)$fatal(1,"RESET RECOVERY");
  $display("GAMMA PASS: LUTs, 65536 bypass colors, alignment, adaptation, frame validation, hysteresis, KEY5 auto-enable/restore, manual override, held keys and simultaneous-key priority");
  $finish;
 end
 initial begin #3000000;$fatal(1,"GAMMA TIMEOUT");end
endmodule
