`timescale 1ns/1ps
module tb_raster_720p60;
 reg clk=0,rstn=0;always #(500.0/74.25)clk=~clk;
 wire vs,hs,de,ls;wire [9:0]ly;wire[11:0]x,y;
 sync_vg #(.V_TOTAL(750),.V_FP(5),.V_BP(20),.V_SYNC(5),.V_ACT(720),
 .H_TOTAL(1650),.H_FP(110),.H_BP(220),.H_SYNC(40),.H_ACT(1280)) dut(
 .clk(clk),.rstn(rstn),.vs_out(vs),.hs_out(hs),.de_out(de),.de_re(),.x_act(x),.y_act(y),.line_start(ls),.line_y(ly));
 reg vsq=0,deq=0;integer clocks=0,pixels=0,lines=0,in_line=0,hs_count=0,vs_count=0,frames=0;realtime start_t,delta;
 always @(negedge clk)if(rstn)begin
  if(vs&&!vsq)begin
   if(frames>0)begin
    delta=$realtime-start_t;
    if(clocks!=1237500 || pixels!=921600 || lines!=720 || hs_count!=30000 || vs_count!=8250)
     $fatal(1,"RASTER counts clocks=%d pixels=%d lines=%d HS=%d VS=%d",clocks,pixels,lines,hs_count,vs_count);
    // A 1ps simulation clock rounds half-periods; tolerance is below 0.01%.
    if(delta<16665000 || delta>16668334)$fatal(1,"Frame period %f",delta);
    $display("RASTER frame=%0d pixels=%0d clocks=%0d measured_sim_hz=%f",frames,pixels,clocks,1.0e9/delta);
    if(frames==2)begin $display("RASTER_720P60 PASS 2 complete 720p60 frames, sync widths, 720 rows of 1280 pixels");$finish;end
   end
   frames=frames+1;start_t=$realtime;clocks=0;pixels=0;lines=0;hs_count=0;vs_count=0;
  end
  clocks=clocks+1;if(hs)hs_count=hs_count+1;if(vs)vs_count=vs_count+1;
  if(de)begin
   if(!deq)begin in_line=0;lines=lines+1;end
   if(x!==in_line || y!==lines-1)$fatal(1,"Active coordinate x=%d y=%d",x,y);
   in_line=in_line+1;pixels=pixels+1;
  end
  if(!de && deq && in_line!=1280)$fatal(1,"Line width %d",in_line);
  vsq=vs;deq=de;
 end
 initial begin repeat(10)@(negedge clk);rstn=1;end
 initial begin #51000000;$fatal(1,"Raster timeout");end
endmodule
