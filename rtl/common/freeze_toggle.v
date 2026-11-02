`timescale 1ns/1ps
`default_nettype none
module freeze_toggle #(parameter DEBOUNCE_CYCLES=1000000)(
 input wire clk,rstn,key_n,clear_i,output reg wanted);
 (* async_reg="true" *)reg [1:0] sync;
 reg stable;reg [19:0] count;
 wire hit=sync[1]!=stable && count==DEBOUNCE_CYCLES-1 && !sync[1];
 always @(posedge clk)begin
  if(!rstn)begin sync<=3;stable<=1;count<=0;wanted<=0;end
  else begin
   sync<={sync[0],key_n};
   if(sync[1]==stable)count<=0;
   else if(count==DEBOUNCE_CYCLES-1)begin stable<=sync[1];count<=0;end
   else count<=count+1'b1;
   if(clear_i)wanted<=0;else if(hit)wanted<=!wanted;
  end
 end
endmodule
`default_nettype wire
