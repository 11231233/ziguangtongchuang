`timescale 1ns/1ps
`default_nettype none
// Alternative input sampling phase only for C2. The downstream word/FIFO clock
// remains PCLK rising; the half-cycle path is checked by normal timing analysis.
module dvp_capture_phase(
 input wire cam_pclk,rstn,vs,hs,input wire [7:0] d,input wire phase_request,
 input wire ddr_clk,ddr_rstn,output wire [15:0] pix,output wire de,vs_o,
 output reg phase_active);
 reg [7:0] neg_d,selected_d;reg neg_hs,neg_vs,selected_hs,selected_vs;
 (* async_reg="true" *)reg [1:0] phase_sync;
 always @(negedge cam_pclk)begin
  if(!rstn)begin neg_d<=0;neg_hs<=0;neg_vs<=0;end
  else begin neg_d<=d;neg_hs<=hs;neg_vs<=vs;end
 end
 always @(posedge cam_pclk)begin
  if(!rstn)begin phase_sync<=0;phase_active<=0;selected_d<=0;selected_hs<=0;selected_vs<=0;end
  else begin
   phase_sync<={phase_sync[0],phase_request};
   if(vs && !hs)phase_active<=phase_sync[1];
   selected_d<=phase_active?neg_d:d;
   selected_hs<=phase_active?neg_hs:hs;
   selected_vs<=phase_active?neg_vs:vs;
  end
 end
 dvp_capture capture(.cam_pclk(cam_pclk),.rstn(rstn),.vs(selected_vs),.hs(selected_hs),.d(selected_d),
  .ddr_clk(ddr_clk),.ddr_rstn(ddr_rstn),.pix(pix),.de(de),.vs_o(vs_o));
endmodule
`default_nettype wire
