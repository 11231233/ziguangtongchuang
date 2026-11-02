`timescale 1ns/1ps
`default_nettype none
// Pin one complete source while rendering. Frozen rerenders reuse the exact
// same slot; frame_writer must honor read_hold until freezing is released.
module warp_scheduler #(parameter AW=28,SLOT_WORDS=460800)(
 input wire clk,rstn,freeze_wanted,frame_valid,
 input wire [31:0] frame_seq,input wire [2:0] frame_slot,
 input wire process_done,process_overflow,display_seen,display_slot,
 output wire accept_source,output reg process_start,
 output reg [AW-1:0] source_base,
 output reg read_hold,output reg [2:0] read_slot,
 output reg destination_slot,front_slot,have_frame,
 output reg frozen,display_frozen,output wire [31:0] selected_frame_seq);
 reg [1:0] state;
 reg [31:0] seen;
 assign accept_source=(state==0) && ((frozen && freeze_wanted) || (frame_valid && frame_seq!=seen));
 assign selected_frame_seq=(frozen && freeze_wanted)?seen:frame_seq;
 function [AW-1:0] base(input [2:0] slot);
  begin case(slot)
   0:base=0;1:base=SLOT_WORDS;2:base=SLOT_WORDS*2;
   3:base=SLOT_WORDS*3;4:base=SLOT_WORDS*4;default:base=SLOT_WORDS*5;
  endcase end
 endfunction
 always @(posedge clk)begin
  if(!rstn)begin
   state<=0;seen<=0;process_start<=0;source_base<=0;read_hold<=0;read_slot<=0;
   destination_slot<=0;front_slot<=0;have_frame<=0;frozen<=0;display_frozen<=0;
  end else begin
   process_start<=0;
   if(!freeze_wanted)display_frozen<=0;
   case(state)
    0:begin
     if(!freeze_wanted)begin frozen<=0;read_hold<=0;end
     if(accept_source)begin
      if(!(frozen && freeze_wanted))begin
       seen<=frame_seq;read_slot<=frame_slot;source_base<=base(frame_slot);
      end
      read_hold<=1;frozen<=freeze_wanted;process_start<=1;state<=1;
     end
    end
    1:if(process_done)begin
     read_hold<=freeze_wanted;frozen<=freeze_wanted;
     if(!process_overflow)begin front_slot<=destination_slot;have_frame<=1;state<=2;end
     else begin state<=3;read_hold<=0;frozen<=0;display_frozen<=0;end
    end
    2:begin
     if(!freeze_wanted)begin read_hold<=0;frozen<=0;end
     if(display_seen && display_slot==front_slot)begin
      display_frozen<=frozen && freeze_wanted;
      destination_slot<=~front_slot;state<=0;
     end
    end
   endcase
  end
 end
endmodule
`default_nettype wire
