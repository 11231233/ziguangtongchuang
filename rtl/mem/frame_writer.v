`timescale 1ns/1ps
`default_nettype none
// Ordered frame markers. Assemble a complete burst before giving DDR ownership;
// a new marker discards an incomplete burst instead of entering the data stream.
module frame_writer #(parameter integer H_ACT=1280,V_ACT=720,FLIP_V=0,AW=28,SLOT_COUNT=6,
 parameter integer STRIDE_WORDS=((H_ACT+255)/256)*128,
 parameter [AW-1:0] FRAME_BASE=0,SLOT_WORDS=460800)(
 input wire src_clk,src_rstn,src_vs,src_de,input wire [15:0] src_pix,
 input wire ddr_clk,ddr_rstn,
 output wire w_req,output wire [AW-1:0] w_addr,output wire [7:0] w_beats,
 input wire w_ready,w_done,output wire [255:0] w_data,input wire w_adv,
 output wire [2:0] wr_slot,output reg led_overflow,
 input wire hold_valid,input wire [2:0] hold_slot,
 output reg frame_done,output reg frame_valid,output reg [2:0] frame_slot,
 output reg [31:0] frame_seq);
 // A row may have a short final burst (e.g. 1296 pixels = 81 beats).
 // The source is 16-pixel aligned. Pad the last DDR burst, never steal
 // pixels from the next sensor row. STRIDE_WORDS must include that padding.
 localparam integer WORDS=STRIDE_WORDS, CHUNKS=(H_ACT+255)/256;
 localparam integer LAST_BEATS=(H_ACT/16)-(CHUNKS-1)*16;
 localparam integer LAYOUT_OK=(H_ACT>0 && H_ACT%16==0 && V_ACT>0 && V_ACT<=1024 &&
  STRIDE_WORDS>=CHUNKS*128 && (SLOT_WORDS==0 || SLOT_WORDS>=STRIDE_WORDS*V_ACT));
 reg vs_d,armed;reg [3:0] pc;reg [255:0] sr;reg src_error;
 wire marker=src_vs && !vs_d;
 wire push=marker || (armed && src_de && pc==15);
 wire full,empty;wire [256:0] q;
 reg busy,active;reg [2:0] slot;reg [9:0] line;
 reg [7:0] chunk;reg [4:0] sent,filled;
 // Complete-burst RAM plus a synchronous look-ahead head; no reset of stored data.
 reg [255:0] burst_mem[0:15];
 reg [255:0] burst_head;
 wire [3:0] head_index=busy?((w_adv && sent<15)?sent[3:0]+4'd1:sent[3:0]):4'd0;
 wire [4:0] fill_target=(chunk==CHUNKS-1)?LAST_BEATS:16;
 wire pop=!busy && filled<fill_target && !empty;
 wire consume_marker=pop && q[256];
 always @(posedge ddr_clk)begin
  if(pop && active && !consume_marker)burst_mem[filled[3:0]]<=q[255:0];
  burst_head<=burst_mem[head_index];
 end
 async_fifo #(.DW(257),.AW(6)) u_fifo(
  .wclk(src_clk),.wrst_n(src_rstn),.wen(push),.wdata(marker?{1'b1,256'd0}:{1'b0,src_pix,sr[255:16]}),.full(full),
  .rclk(ddr_clk),.rrst_n(ddr_rstn),.ren(pop),.rdata(q),.empty(empty),.rcount());
 always @(posedge src_clk) begin
  if(!src_rstn) begin vs_d<=0;armed<=0;pc<=0;sr<=0;src_error<=0;end
  else begin
   vs_d<=src_vs;
   if(marker) begin pc<=0;sr<=0;armed<=!full;end
   else if(armed && src_de) begin sr<={src_pix,sr[255:16]};pc<=pc+1'b1;end
   // Drop the rest of this frame on loss. Only a successfully queued marker rearms.
   if(push&&full) begin src_error<=1;armed<=0;pc<=0;end
  end
 end
 (* async_reg="true" *) reg [1:0] err_sync;
 reg [AW-1:0] slot_base;
 function [2:0] following(input [2:0] s);begin following=(s==SLOT_COUNT-1)?3'd0:s+3'd1;end endfunction
 wire [2:0] next0=following(slot),next1=following(next0),next2=following(next1);
 // All live dependencies are explicit. A function that only takes the slot
 // argument can leave simulation stale when protection metadata alone changes.
 wire reserved0=(hold_valid && next0==hold_slot)||(frame_valid && next0==frame_slot);
 wire reserved1=(hold_valid && next1==hold_slot)||(frame_valid && next1==frame_slot);
 wire [2:0] next_slot=!reserved0?next0:(!reserved1?next1:next2);
 assign wr_slot=slot;
 assign w_req=LAYOUT_OK && active && !busy && filled==fill_target;
 assign w_addr=FRAME_BASE+slot_base+(FLIP_V?(V_ACT-1-line):line)*WORDS+chunk*128;
 assign w_beats=16;
 assign w_data=(!busy || sent<fill_target)?burst_head:256'd0;
 always @(posedge ddr_clk) begin
  if(!ddr_rstn) begin
   err_sync<=0;busy<=0;active<=0;slot<=SLOT_COUNT-1;slot_base<=0;line<=0;chunk<=0;sent<=0;filled<=0;
   frame_done<=0;frame_valid<=0;frame_slot<=0;frame_seq<=0;led_overflow<=0;
  end else begin
   err_sync<={err_sync[0],src_error};
   if(err_sync[1]) led_overflow<=1;
   frame_done<=0;
   if(consume_marker) begin
    if(active) led_overflow<=1;
    slot<=next_slot;slot_base<=next_slot*SLOT_WORDS;
    active<=1;line<=0;chunk<=0;filled<=0;
   end else if(pop && active) begin
    filled<=filled+1'b1;
   end
   if(w_req&&w_ready) begin busy<=1;sent<=0;end
   if(busy&&w_adv&&sent<16) begin sent<=sent+1'b1;end
   if(busy&&w_done) begin
    busy<=0;filled<=0;
    if(chunk==CHUNKS-1) begin
     chunk<=0;
     if(line==V_ACT-1) begin
      active<=0;
      frame_done<=1;frame_valid<=1;frame_slot<=slot;frame_seq<=frame_seq+1'b1;
     end else line<=line+1'b1;
    end else chunk<=chunk+1'b1;
   end
   if(!LAYOUT_OK)begin active<=0;busy<=0;frame_valid<=0;led_overflow<=1;end
  end
 end
endmodule
`default_nettype wire
