`timescale 1ns/1ps
`default_nettype none
// A debounced short release selects the camera format; a held key toggles
// natural-video Gamma once. Pulses last long enough for downstream debounce.
module key_short_long #(
 parameter DEBOUNCE_CYCLES=1000000,LONG_CYCLES=100000000,PULSE_CYCLES=2000000
)(input wire clk,rstn,key_n,output wire short_n,long_n);
 (* async_reg="true" *)reg [1:0] sync;
 reg stable,held_long;
 reg [19:0] debounce;
 reg [26:0] held;
 reg [20:0] short_left,long_left;
 assign short_n=(short_left==0);assign long_n=(long_left==0);
 always @(posedge clk)begin
  if(!rstn)begin sync<=3;stable<=1;held_long<=0;debounce<=0;held<=0;short_left<=0;long_left<=0;end
  else begin
   sync<={sync[0],key_n};
   if(short_left!=0)short_left<=short_left-1'b1;
   if(long_left!=0)long_left<=long_left-1'b1;
   if(sync[1]==stable)debounce<=0;
   else if(debounce==DEBOUNCE_CYCLES-1)begin
    stable<=sync[1];debounce<=0;
    if(sync[1])begin
     if(!held_long)short_left<=PULSE_CYCLES;
     held<=0;held_long<=0;
    end else begin held<=0;held_long<=0;end
   end else debounce<=debounce+1'b1;
   if(!stable && !held_long && !(sync[1] && debounce==DEBOUNCE_CYCLES-1))begin
    if(held==LONG_CYCLES-1)begin held_long<=1;long_left<=PULSE_CYCLES;end
    else held<=held+1'b1;
   end
  end
 end
endmodule
`default_nettype wire
