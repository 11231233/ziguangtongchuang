`timescale 1ns/1ps
module tb_controls;
reg clk=0,rstn=0,fs=0;reg[3:0]kn=15;always #5 clk=~clk;
wire signed[31:0]A,C,E,F,fx,fy,cx,cy,k1,k2;wire enabled,ae;wire[1:0]strength,zoom,ast,az;
warp_controls #(.DEBOUNCE_CYCLES(3)) dut(.clk(clk),.rstn(rstn),.key_n(kn),.frame_start(fs),
.A(A),.C(C),.E(E),.F(F),.fx(fx),.fy(fy),.cx(cx),.cy(cy),.k1(k1),.k2(k2),
.enabled(enabled),.strength(strength),.zoom(zoom),.active_enabled(ae),.active_strength(ast),.active_zoom(az));
task latch_frame;begin @(negedge clk);fs=1;@(negedge clk);fs=0;end endtask
task press(input integer n);begin @(negedge clk);kn[n]=0;repeat(15)@(negedge clk);kn[n]=1;repeat(12)@(negedge clk);end endtask
integer i,z;reg signed[31:0]oldk;reg signed[63:0]delta;
reg [255:0]geometry;
initial begin
 repeat(5)@(negedge clk);rstn=1;repeat(4)@(negedge clk);
 if(!ae||k1!=-21061||k2!=7082||A!=126||ast!=2||az!=0||C!=-80660||F!=-45371)$fatal(1,"DEFAULT MUST BE NOMINAL 1X");
 kn[0]=0;@(negedge clk);kn[0]=1;repeat(10)@(negedge clk);
 if(!enabled)$fatal(1,"BOUNCE ACCEPTED");
 for(z=0;z<3;z=z+1)begin
  geometry={A,C,E,F,fx,fy,cx,cy};
  press(0);if(enabled||!ae||k1!=-21061)$fatal(1,"MID FRAME CONFIG CHANGE");
  latch_frame;
  if(ae||k1!=0||k2!=0||{A,C,E,F,fx,fy,cx,cy}!==geometry)$fatal(1,"RAW/COR GEOMETRY MUST MATCH");
  if(z==0)begin
   for(i=0;i<1280;i=i+1)begin
    delta=(((64'(A)*i+C)*fx+32768)>>>16)+cx-(64'(i)<<16);
    if(delta>32768||delta< -32768)$fatal(1,"RAW NOMINAL 1X X ERROR i=%0d delta=%0d",i,delta);
   end
   for(i=0;i<720;i=i+1)begin
    delta=(((64'(E)*i+F)*fy+32768)>>>16)+cy-(64'(i)<<16);
    if(delta>32768||delta< -32768)$fatal(1,"RAW NOMINAL 1X Y ERROR i=%0d delta=%0d",i,delta);
   end
  end
  press(0);latch_frame;
  if(!ae||k1!=-21061||k2!=7082||{A,C,E,F,fx,fy,cx,cy}!==geometry)$fatal(1,"COR RESTORE CHANGES SCALE");
  press(2);latch_frame;
 end
 if(az!=0||A!=126)$fatal(1,"ZOOM WRAP");
 for(i=0;i<4;i=i+1)begin
  oldk=k1;press(1);if(k1!=oldk)$fatal(1,"STRENGTH CHANGED WITHIN FRAME");latch_frame;
  case(ast)
   0:if(k1!=-7864||k2!=1311)$fatal(1,"PRESET0");
   1:if(k1!=-18350||k2!=5243)$fatal(1,"PRESET1");
   2:if(k1!=-21061||k2!=7082)$fatal(1,"PRESET2");
   3:if(k1!=-32768||k2!=10486)$fatal(1,"PRESET3");
  endcase
 end
 press(2);latch_frame;press(0);latch_frame;
 press(3);latch_frame;if(!ae||ast!=2||az!=0||k1!=-21061||k2!=7082||A!=126)$fatal(1,"RESET PRESETS");
 $display("CONTROLS PASS: debounce, matched RAW/COR geometry in all zooms, default nominal 1x within 0.5px, frame-atomic updates, restore");$finish;
end
initial begin #100000;$fatal(1,"TIMEOUT CONTROLS");end
endmodule
