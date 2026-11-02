`timescale 1ns/1ps
`default_nettype none
// Checked OV5640 configuration, shared by single-camera and legacy test instances.
module ov5640_checked_config #(
 parameter [7:0] PLL_MULTIPLIER=8'h34,
 parameter integer VERIFY_PLL=0,
 // Fixed-frame AEC/AGC and automatic white balance; legacy defaults unchanged.
 parameter integer IMAGE_PROFILE=0,GEOMETRY_PROFILE=0,
 parameter integer TICK_DIV=625,DUMMY_DELAY=110000,RESET_DELAY=500000,MAX_RETRIES=3
)(input wire clk,rstn,initial_en,bar_request,
 output reg config_ok,fault,bar_active,output reg [7:0] format_readback,retry_total,
 output wire scl,inout wire sda);
 localparam GEOM_BASE=365+(IMAGE_PROFILE?15:0),GEOM_VERIFY_BASE=9+(IMAGE_PROFILE?15:0);
 localparam WAIT=0,ROM=1,ISSUE=2,BUS_WAIT=3,ADVANCE=4,DELAY=5,VERIFY=6,READY=7,BAR_WRITE=8,BAR_READ=9;
 reg [3:0] state,return_state;reg [8:0] index;
 reg [5:0] verify_index;reg [31:0] delay_left;
 reg [1:0] en_sync,bar_sync;reg [2:0] retries;
 reg go,reading,delay_skip;reg [15:0] address;reg [7:0] value,expected;
 wire [23:0] rom_data;wire busy,done,error;wire [7:0] received;
 ov5640_reg_rom #(.PLL_MULTIPLIER(PLL_MULTIPLIER),.RGB_FORMAT(8'h60)) rom(.reg_index(index),.reg_data(rom_data));
 sccb_checked_master #(.TICK_DIV(TICK_DIV)) bus(.clk(clk),.rstn(rstn),.start(go),.read_i(reading),
  .address(address),.write_data(value),.busy(busy),.done(done),.error(error),.read_data(received),.scl(scl),.sda(sda));
 function [23:0] image_write(input [4:0] n);
  begin case(n)
   0:image_write=24'h3a0078; // Night mode off, auto banding and sub-line AEC on.
   1:image_write=24'h340600; // Automatic white balance, not manual channel gains.
   2:image_write=24'h350300; // Automatic exposure and gain.
   3:image_write=GEOMETRY_PROFILE?24'h3a0203:24'h3a0202;4:image_write=24'h3a03e0; // 736 lines, below VTS.
   5:image_write=GEOMETRY_PROFILE?24'h3a1403:24'h3a1402;6:image_write=24'h3a15e0;
   7:image_write=24'h3a1800;8:image_write=24'h3a1980; // Lower gain ceiling than legacy 00f8.
   9:image_write=24'h500183; // Preserve ISP/AWB processing enables.
   10:image_write=24'h530825; // Automatic sensor detail/noise threshold control.
   11:image_write=GEOMETRY_PROFILE?24'h380e03:24'h380e02;
   12:image_write=GEOMETRY_PROFILE?24'h380fe8:24'h380fe4; // Fixed VTS 740; no long-exposure frame insertion.
   13:image_write=24'h3c0004; // 50Hz fallback is bit 2, not bit 6 (legacy 40).
   default:image_write=24'h3c0134; // Automatic 50/60Hz light-frequency selection.
  endcase end
 endfunction
 function [23:0] geometry_write(input [4:0] n);
  begin case(n)
   0:geometry_write=24'h380000;
   1:geometry_write=24'h380100;
   2:geometry_write=24'h380200;
   3:geometry_write=24'h380300;
   4:geometry_write=24'h38040a;
   5:geometry_write=24'h38053f;
   6:geometry_write=24'h380607;
   7:geometry_write=24'h38079f;
   8:geometry_write=24'h380805;
   9:geometry_write=24'h380910;
   10:geometry_write=24'h380a03;
   11:geometry_write=24'h380bcc;
   12:geometry_write=24'h380c07;
   13:geometry_write=24'h380d64;
   14:geometry_write=24'h380e03;
   15:geometry_write=24'h380fe8;
   16:geometry_write=24'h381000;
   17:geometry_write=24'h381108;
   18:geometry_write=24'h381200;
   19:geometry_write=24'h381302;
   20:geometry_write=24'h381431;
   21:geometry_write=24'h381531;
   22:geometry_write=24'h382047;
   // 0x3821: bit[2]=ISP mirror, bit[1]=sensor mirror, bit[0]=horizontal binning.
   // OV5640 is back-side illuminated, so the die itself mirrors the image; the
   // mirror bits must be SET to cancel that. They were 0, which is why the whole
   // picture came out left-right reversed. bit[0] stays set to match 0x3820.
   23:geometry_write=24'h382107;
   default:geometry_write=24'h382107;
  endcase end
 endfunction
 function [23:0] verification(input [5:0] n);
  begin if(GEOMETRY_PROFILE && n>=GEOM_VERIFY_BASE)verification=geometry_write(n-GEOM_VERIFY_BASE);
  else case(n)
   0:verification=24'h430060;1:verification=24'h501f01;2:verification=24'h474020;
   3:verification=24'h474500;4:verification=24'h300a56;5:verification=24'h300b40;
   6:verification=24'h503d00;7:verification=24'h303521;
   8:verification={16'h3036,PLL_MULTIPLIER};
   default:verification=image_write(n-9);
  endcase end
 endfunction
 function [23:0] guard_write(input [3:0] n);
  begin case(n)
   0:guard_write=24'h501f01;1:guard_write=24'h430060;2:guard_write=24'h474020;
   3:guard_write=24'h474500;4:guard_write=24'h500183;5:guard_write=24'h350300;
   default:guard_write=24'h503d00;
  endcase end
 endfunction
 wire [23:0] check_value=verification(verify_index);
 wire [23:0] final_value=guard_write(index-358);
 wire [23:0] image_value=image_write(index-365);
 wire [23:0] geometry_value=geometry_write(index-GEOM_BASE);
 always @(posedge clk or negedge rstn)begin
  if(!rstn)begin
   state<=WAIT;return_state<=ADVANCE;index<=0;verify_index<=0;delay_left<=0;
   en_sync<=0;bar_sync<=0;retries<=0;go<=0;reading<=0;delay_skip<=0;address<=0;value<=0;expected<=0;
   config_ok<=0;fault<=0;bar_active<=0;format_readback<=0;retry_total<=0;
  end else begin
   en_sync<={en_sync[0],initial_en};bar_sync<={bar_sync[0],bar_request};go<=0;
   case(state)
    WAIT:if(en_sync[1])state<=ROM;
    ROM:begin
     reading<=0;retries<=0;return_state<=ADVANCE;
     if(index<358)begin
      if(rom_data==24'hffffff)begin delay_left<=DUMMY_DELAY;delay_skip<=1;state<=DELAY;end
      else begin address<=rom_data[23:8];value<=rom_data[7:0];state<=ISSUE;end
     end else if(index<365)begin address<=final_value[23:8];value<=final_value[7:0];state<=ISSUE;end
     else if(IMAGE_PROFILE && index<380)begin address<=image_value[23:8];value<=image_value[7:0];state<=ISSUE;end
     else if(GEOMETRY_PROFILE && index<GEOM_BASE+24)begin address<=geometry_value[23:8];value<=geometry_value[7:0];state<=ISSUE;end
     else begin verify_index<=0;state<=VERIFY;end
    end
    ISSUE:if(!busy)begin go<=1;state<=BUS_WAIT;end
    BUS_WAIT:if(done)begin
     if(error || (reading && received!=expected))begin
      if(retry_total!=255)retry_total<=retry_total+1'b1;
      if(retries<MAX_RETRIES)begin retries<=retries+1'b1;state<=ISSUE;end
      else begin fault<=1;state<=WAIT;end
     end else begin
      if(reading && address==16'h4300)format_readback<=received;
      state<=return_state;
     end
    end
    ADVANCE:begin
     index<=index+1'b1;
     if(index==1)begin delay_left<=RESET_DELAY;delay_skip<=0;state<=DELAY;end
     else state<=ROM;
    end
    DELAY:if(delay_left==0)begin
      // Dummy slots consume their old settling interval without invalid writes.
      if(delay_skip)index<=index+1'b1;
      state<=ROM;
     end else delay_left<=delay_left-1'b1;
    VERIFY:begin
     reading<=1;address<=check_value[23:8];expected<=check_value[7:0];retries<=0;
     return_state<=4'd10;state<=ISSUE;
    end
    10:if(verify_index==(GEOMETRY_PROFILE?GEOM_VERIFY_BASE+23:(IMAGE_PROFILE?23:(VERIFY_PLL?8:6))))begin config_ok<=1;state<=READY;end
       else begin verify_index<=verify_index+1'b1;state<=VERIFY;end
    READY:if(bar_sync[1]!=bar_active)begin
     reading<=0;address<=16'h503d;value<=bar_sync[1]?8'h80:8'h00;
     expected<=bar_sync[1]?8'h80:8'h00;retries<=0;return_state<=BAR_WRITE;state<=ISSUE;
    end
    BAR_WRITE:begin reading<=1;retries<=0;return_state<=BAR_READ;state<=ISSUE;end
    BAR_READ:begin bar_active<=expected[7];state<=READY;end
    default:state<=WAIT;
   endcase
   // Exhausted retries is a latched fault, never a false config-success loop.
   if(fault)begin state<=WAIT;go<=0;end
  end
 end
endmodule
`default_nettype wire
