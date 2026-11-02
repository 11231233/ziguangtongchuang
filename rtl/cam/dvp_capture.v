`timescale 1ns/1ps
`default_nettype none
// RGB565 high byte first. Frame markers share the pixel FIFO, so a delayed
// pixel can never be overtaken by VS. Both resets must share an assertion source.
module dvp_capture (
 input wire cam_pclk,rstn,vs,hs,input wire [7:0] d,
 input wire ddr_clk,ddr_rstn,
 output wire [15:0] pix,output wire de,vs_o);
 reg [7:0] d_r,b0;
 reg hs_r,vs_r,vs_r2,half,armed;
 reg [16:0] payload;reg push;
 wire full,empty;wire [16:0] q;
 wire marker=vs_r&&!vs_r2;
 always @(posedge cam_pclk) begin
  if(!rstn) begin
   d_r<=0;hs_r<=0;vs_r<=0;vs_r2<=0;half<=0;armed<=0;b0<=0;payload<=0;push<=0;
  end else begin
   d_r<=d;hs_r<=hs;vs_r<=vs;vs_r2<=vs_r;push<=0;
   if(marker) begin
    half<=0;
    // push is registered: conservatively account for the preceding FIFO write.
    // If it fills at this edge, the marker is rejected and the frame stays disarmed.
    armed<=!full;
    if(!full) begin payload<={1'b1,16'd0};push<=1;end
   end else if(!hs_r || vs_r || !armed) half<=0;
   else if(!half) begin b0<=d_r;half<=1;end
   else begin
    half<=0;
    if(!full) begin payload<={1'b0,b0,d_r};push<=1;end
    else armed<=0;
   end
   // Any pending write rejected by a newly asserted full invalidates the frame.
   if(push&&full) begin armed<=0;push<=0;end
  end
 end
 async_fifo #(.DW(17),.AW(9)) u_fifo(
  .wclk(cam_pclk),.wrst_n(rstn),.wen(push),.wdata(payload),.full(full),
  .rclk(ddr_clk),.rrst_n(ddr_rstn),.ren(!empty),.rdata(q),.empty(empty),.rcount());
 assign pix=q[15:0];
 assign de=!empty&&!q[16];
 assign vs_o=!empty&&q[16];
endmodule
`default_nettype wire
