`timescale 1ns/1ps
`default_nettype none
// Generated ONLY after geometry-bound real calibration passes its gates.
module margin_runtime_controls #(parameter DEBOUNCE=1000000,REPEAT_DELAY=50000000,REPEAT_PERIOD=10000000,RESET_HOLD=200000000)(
 input wire clk,rstn,frame_start,input wire[3:0]key_n,
 output reg[447:0]coeff,output reg active_enabled,output reg signed[9:0]active_angle,
 output reg[12:0]angle_bcd,output reg angle_toggle,output wire certified);
 assign certified=1'b@CERTIFIED@;
 (* async_reg="true" *)reg[3:0]sync0,sync1;reg[3:0]stable,hit;reg[19:0]debounce[0:3];integer i;
 reg[5:0]wanted_index;reg wanted_enabled;reg[27:0]repeat_count;reg repeating;
 reg[28:0]chord_count;reg chord_latched,chord_fired;
 wire chord=(stable[3:2]==0);
 wire tick=repeat_count==(repeating?REPEAT_PERIOD-1:REPEAT_DELAY-1);
 always @(posedge clk)begin
  if(!rstn)begin
   sync0<=15;sync1<=15;stable<=15;hit<=0;wanted_index<=20;wanted_enabled<=1;
   repeat_count<=0;repeating<=0;chord_count<=0;chord_latched<=0;chord_fired<=0;
   for(i=0;i<4;i=i+1)debounce[i]<=0;
  end else begin
   sync0<=key_n;sync1<=sync0;hit<=0;
   for(i=0;i<4;i=i+1)begin
    if(sync1[i]==stable[i])debounce[i]<=0;
    else if(debounce[i]==DEBOUNCE-1)begin stable[i]<=sync1[i];debounce[i]<=0;if(!sync1[i])hit[i]<=1;end
    else debounce[i]<=debounce[i]+1'b1;
   end
   if(stable[3:2]==3 || chord || chord_latched)begin repeat_count<=0;repeating<=0;end
   else if(tick)begin repeat_count<=0;repeating<=1;end
   else repeat_count<=repeat_count+1'b1;
   if(chord)begin
    wanted_index<=20;chord_latched<=1;
    if(!chord_fired)begin
     if(chord_count==RESET_HOLD-1)begin wanted_enabled<=1;chord_fired<=1;end
     else chord_count<=chord_count+1'b1;
    end
   end else begin
    chord_count<=0;chord_fired<=0;if(stable[3:2]==3)chord_latched<=0;
    if(!chord_latched)begin
     if((hit[2] || (!stable[2] && stable[3] && tick)) && wanted_index<40)wanted_index<=wanted_index+1'b1;
     else if((hit[3] || (!stable[3] && stable[2] && tick)) && wanted_index>0)wanted_index<=wanted_index-1'b1;
    end
    if(hit[0])wanted_enabled<=!wanted_enabled;
   end
  end
 end
 reg[5:0]index;reg en0,en1;reg[447:0]cor,raw;reg[12:0]bcd;reg signed[9:0]angle;
 always @(posedge clk)begin
  if(!rstn)begin index<=20;en0<=1;en1<=1;coeff<=448'h@ZERO@;active_enabled<=1;active_angle<=0;angle_bcd<=0;angle_toggle<=0;end
  else begin
   index<=wanted_index;en0<=wanted_enabled;en1<=en0;
   if(frame_start)begin
    coeff<=en1?cor:raw;active_enabled<=en1;active_angle<=angle;angle_bcd<=bcd;
    if(bcd!=angle_bcd)angle_toggle<=!angle_toggle;
   end
  end
 end
 always @(posedge clk)begin
  case(index)
@ROWS@
   default:begin cor<=448'h@ZERO@;raw<=448'h@ZERO_RAW@;bcd<=0;angle<=0;end
  endcase
 end
endmodule
`default_nettype wire
