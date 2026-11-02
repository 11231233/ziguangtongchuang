`timescale 1ns/1ps
module tb_focus_meter;
 localparam W=32,H=16;
 reg clk=0,rstn=0,vs=0,de=0;reg [15:0] pixel=0;
 always #5 clk=~clk;
 wire [15:0] score;wire toggle;
 focus_meter #(.WIDTH(W),.HEIGHT(H),.SCORE_SHIFT(6)) dut(.clk(clk),.rstn(rstn),.vs(vs),.de(de),.pixel(pixel),.score_bcd(score),.score_toggle(toggle));
 function [15:0] pattern(input integer scene,xx,yy);
  integer a;begin
   case(scene)
    0:a=128;
    1:a=(xx>=16)?255:0;
    2:a=(xx<12)?0:(xx>=20)?255:(xx-12)*32;
    3:a=(yy>=8)?255:0;
    4:a=(xx>=2)?255:0;
    default:a=((xx+yy)%2)?255:0;
   endcase
   pattern={a[7:3],a[7:2],a[7:3]};
  end
 endfunction
 function integer decimal(input [15:0] b);
  begin
   if(b[15:12]>9||b[11:8]>9||b[7:4]>9||b[3:0]>9)$fatal(1,"INVALID FOCUS BCD");
   decimal=b[15:12]*1000+b[11:8]*100+b[7:4]*10+b[3:0];
  end
 endfunction
 function integer gray(input [15:0] p);
  integer r,g,b;begin r=(p[15:11]*255)/31;g=(p[10:5]*255)/63;b=(p[4:0]*255)/31;gray=(r+2*g+b)/4;end
 endfunction
 // Primary assertions use fixtures with exact black/white expected energy.
 // A ramp must have less energy than the hard step, unlike L1 edge sums.
 task send(input integer scene,count,input gaps,immediate_marker);
  integer i;begin
   @(negedge clk);vs=1;de=0;@(negedge clk);vs=0;
   for(i=0;i<count;i=i+1)begin
    if(gaps&&i%7==0)begin @(negedge clk);de=0;repeat(2)@(negedge clk);end
    @(negedge clk);de=1;pixel=pattern(scene,i%W,i/W);
   end
   @(negedge clk);de=0;vs=immediate_marker;
   @(negedge clk);vs=0;repeat(30)@(negedge clk);
  end
 endtask
 reg previous;integer sharp,blur;
 initial begin
  repeat(5)@(negedge clk);rstn=1;
  de=1;pixel=16'hffff;repeat(30)@(negedge clk);de=0;
  if(score!==0||toggle!==0)$fatal(1,"UNARMED INPUT ACCEPTED");
  send(0,W*H,1,0);if(score!==0||toggle!==1)$fatal(1,"FLAT FRAME");
  send(1,W*H,1,1);sharp=decimal(score);if(sharp!=8128||toggle!==0)$fatal(1,"SHARP STEP ENERGY %0d",sharp);
  previous=toggle;send(2,300,1,0);
  if(toggle!==previous||decimal(score)!=sharp)$fatal(1,"TRUNCATED FRAME PUBLISHED");
  send(2,W*H,1,1);blur=decimal(score);
  if(blur<=0||blur>=sharp)$fatal(1,"BLUR NOT DISTINGUISHED sharp=%0d blur=%0d",sharp,blur);
  send(4,W*H,0,0);if(score!==0)$fatal(1,"OUTSIDE ROI INFLUENCES SCORE");
  send(3,W*H,0,0);if(score!==16'h9999)$fatal(1,"SATURATION %h",score);
  rstn=0;repeat(5)@(negedge clk);rstn=1;
  if(score!==0||toggle!==0)$fatal(1,"RESET STATE");
  send(0,W*H,0,0);if(score!==0||toggle!==1)$fatal(1,"RESET RECOVERY");
  $display("FOCUS PASS: passive ROI, flat/step/blur distinction, bubbles, immediate marker, partial-frame rejection, saturation and reset");$finish;
 end
 initial begin #1000000;$fatal(1,"FOCUS TIMEOUT");end
endmodule
