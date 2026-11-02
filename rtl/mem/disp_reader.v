`timescale 1ns/1ps
`default_nettype none
// Exact row requests from sync_vg; tagged packets never leak into another row.
module disp_reader #(parameter integer H_ACT=1280,V_ACT=720,V_OFFSET=25,AW=28,
 parameter [AW-1:0] FRAME_BASE=0,SLOT_WORDS=460800,
 parameter integer FLIP_V=0,EXTERNAL_LINE=0)(
 input wire pix_clk,pix_rstn,vs,hs,de,output reg [15:0] pix_out,
 input wire wr_slot,frame_valid,output wire shown_slot,output reg frame_seen,
 output wire visible_slot,
 input wire line_start,input wire [9:0] line_y,
 input wire ddr_clk,ddr_rstn,
 output wire r_req,output wire [AW-1:0] r_addr,output wire [7:0] r_beats,
 input wire r_ready,r_done,input wire [255:0] r_data,input wire r_valid,r_last,
 output reg led_underrun);
 localparam integer WORDS=H_ACT/2,CHUNKS=H_ACT/256;
 reg [2:0] slot_sync;reg [1:0] valid_sync;reg rd_slot;
 reg hs_d;reg [9:0] yline;reg req_tog;
 reg [AW-1:0] req_addr;reg [9:0] req_y;reg req_slot;
 wire hs_rise=hs&&!hs_d;
 wire request_line=EXTERNAL_LINE?line_start:(hs_rise && !vs && yline>=V_OFFSET && yline<V_OFFSET+V_ACT);
 wire [9:0] y=EXTERNAL_LINE?line_y:yline-V_OFFSET;
 // Acknowledge the new front only after every old-slot DDR read has retired.
 // This acknowledgement is in ddr_clk, preventing the producer from reusing a
 // buffer while a stalled read still addresses it across vertical blank.
 reg retired_slot;
 (* async_reg="true" *) reg [2:0] shown_sync;
 assign shown_slot=retired_slot;
 assign visible_slot=rd_slot;
 always @(posedge pix_clk) begin
  if(!pix_rstn) begin slot_sync<=0;valid_sync<=0;rd_slot<=0;frame_seen<=0;hs_d<=0;yline<=0;req_tog<=0;req_addr<=0;req_y<=0;req_slot<=0;end
  else begin
   slot_sync<={slot_sync[1:0],wr_slot};valid_sync<={valid_sync[0],frame_valid};hs_d<=hs;
   if(vs) begin yline<=0;if(valid_sync[1]) begin rd_slot<=~slot_sync[2];frame_seen<=1;end end
   else if(hs_rise) yline<=yline+1'b1;
   if(request_line && frame_seen) begin
    req_addr<=FRAME_BASE+(rd_slot?SLOT_WORDS:0)+(FLIP_V?(V_ACT-1-y):y)*WORDS;
    req_y<=y;req_slot<=rd_slot;req_tog<=~req_tog;
   end
  end
 end
 (* async_reg="true" *) reg [2:0] tog_sync;
 reg running,cmd_sent,ddr_error;
 reg [7:0] chunk;
 reg [AW-1:0] base_addr;
 reg [9:0] row_l;reg slot_l;
 wire req_new=tog_sync[2]^tog_sync[1];
 assign r_req=running&&!cmd_sent;
 assign r_addr=base_addr+chunk*128;
 assign r_beats=16;
 wire full,empty;wire [266:0] q;wire [7:0] level;wire pop;
 async_fifo #(.DW(267),.AW(7)) u_disp_fifo(
  .wclk(ddr_clk),.wrst_n(ddr_rstn),.wen(r_valid),.wdata({row_l,slot_l,r_data}),.full(full),
  .rclk(pix_clk),.rrst_n(pix_rstn),.ren(pop),.rdata(q),.empty(empty),.rcount(level));
 always @(posedge ddr_clk) begin
  if(!ddr_rstn) begin tog_sync<=0;running<=0;cmd_sent<=0;chunk<=0;base_addr<=0;row_l<=0;slot_l<=0;ddr_error<=0;shown_sync<=0;retired_slot<=0;end
  else begin
   tog_sync<={tog_sync[1:0],req_tog};
   shown_sync<={shown_sync[1:0],rd_slot};
   if(!running && !req_new) retired_slot<=shown_sync[2];
   if(r_valid&&full) ddr_error<=1;
   if(req_new) begin
    if(running) ddr_error<=1;
    else begin base_addr<=req_addr;row_l<=req_y;slot_l<=req_slot;chunk<=0;running<=1;cmd_sent<=0;end
   end
   if(r_req&&r_ready) cmd_sent<=1;
   if(running&&r_done) begin
    cmd_sent<=0;
    if(chunk==CHUNKS-1) begin running<=0;chunk<=0;end
    else chunk<=chunk+1'b1;
   end
  end
 end
 reg [9:0] expected_y;
 reg [10:0] x;
 reg [3:0] pidx;
 reg [255:0] pix_sh;
 reg primed;
 (* async_reg="true" *) reg [1:0] error_sync;
 wire match_head=!empty && q[266:257]==expected_y && q[256]==rd_slot;
 // One preload plus 79 replacements = 80 beats for a 1280-pixel row.
 assign pop=(!de&&!request_line&&!empty&&(!match_head||!primed)) ||
            (de&&primed&&pidx==15&&x<H_ACT-1&&match_head);
 always @(posedge pix_clk) begin
  if(!pix_rstn) begin expected_y<=0;x<=0;pidx<=0;pix_sh<=0;primed<=0;pix_out<=0;led_underrun<=0;error_sync<=0;end
  else begin
   error_sync<={error_sync[0],ddr_error};
   if(error_sync[1]) led_underrun<=1;
   if(request_line) begin expected_y<=y;x<=0;pidx<=0;primed<=0;end
   else if(!de) begin
    if(!primed&&match_head) begin pix_sh<=q[255:0];primed<=1;end
   end else begin
    pix_out<=(frame_seen&&primed)?pix_sh[15:0]:16'd0;
    if(frame_seen&&!primed) led_underrun<=1;
    x<=x+1'b1;
    if(pidx==15) begin
     pidx<=0;
     if(x<H_ACT-1) begin
      if(match_head) pix_sh<=q[255:0];
      else begin primed<=0;pix_sh<=0;if(frame_seen) led_underrun<=1;end
     end
    end else begin pidx<=pidx+1'b1;pix_sh<={16'd0,pix_sh[255:16]};end
   end
  end
 end
endmodule
`default_nettype wire
