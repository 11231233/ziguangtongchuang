`timescale 1ns/1ps
`default_nettype none
// Observe raw 16-bit DVP words before decode/warp. Stable snapshot mailbox
// waits for a pixel-domain VS commit and its acknowledgement before reuse.
module camera_probe #(parameter integer WIDTH=1280,HEIGHT=720)(
 input wire clk,rstn,vs,de,input wire [15:0] word_i,uart_status,
 input wire pix_clk,pix_rstn,pix_vs,output reg [204:0] visible);
 reg [19:0] count;reg [7:0] mask;reg [15:0] any_bits,all_bits;reg [127:0] samples;
 reg armed,vs_q,request;reg [204:0] held;
 (* async_reg="true" *)reg [1:0] ack_sync;
 (* async_reg="true" *)reg [2:0] req_sync;
 reg ack,pending,pix_vs_q;reg [204:0] pending_data;integer i;
 always @(posedge clk)begin
  if(!rstn)begin count<=0;mask<=0;any_bits<=0;all_bits<=16'hffff;samples<=0;armed<=0;vs_q<=0;request<=0;held<=0;ack_sync<=0;end
  else begin
   vs_q<=vs;ack_sync<={ack_sync[0],ack};
   if(vs && !vs_q)begin
    if(ack_sync[1]==request)begin
     held<={(armed && count==WIDTH*HEIGHT && mask==8'hff),uart_status,count,mask,all_bits,any_bits,samples};request<=!request;
    end
    count<=0;mask<=0;any_bits<=0;all_bits<=16'hffff;samples<=0;armed<=1;
   end else if(armed && de)begin
    if(count!=20'hfffff)count<=count+1'b1;
    any_bits<=any_bits|word_i;all_bits<=all_bits&word_i;
    for(i=0;i<8;i=i+1)if(count==(HEIGHT/2)*WIDTH+WIDTH/16+i*(WIDTH/8))begin samples[i*16+:16]<=word_i;mask[i]<=1;end
   end
  end
 end
 always @(posedge pix_clk)begin
  if(!pix_rstn)begin req_sync<=0;ack<=0;pending<=0;pix_vs_q<=0;visible<=0;pending_data<=0;end
  else begin
   req_sync<={req_sync[1:0],request};pix_vs_q<=pix_vs;
   if(req_sync[2]!=ack && !pending)begin pending_data<=held;pending<=1;end
   if(pix_vs && !pix_vs_q && pending)begin visible<=pending_data;ack<=req_sync[2];pending<=0;end
  end
 end
endmodule
`default_nettype wire
