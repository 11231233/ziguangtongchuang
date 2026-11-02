`timescale 1ns/1ps
`default_nettype none
// SRC/OUT are frames per second, CALC is whole milliseconds of FPGA work.
// Clock-domain transfer uses a stable one-second snapshot plus a toggle.
// Digits and enable change only at VS; the video pipeline gains no extra stage.
module metrics_osd #(parameter integer DEBOUNCE_CYCLES=742500, SINGLE_CAMERA=0,DIAGNOSTICS=1,PIPELINE_FONT=0,SHOW_ANGLE=0)(
 input wire clk,rstn,vs,de,key_n,camera_selected,fusion_enabled,fusion_used,frozen,
 input wire [1:0] format2,display_quality,
 input wire [204:0] probe,
 input wire [18:0] c2_status,input wire c2_status_toggle,c2_phase,
 output wire overlay_active,
 input wire [11:0] x,y,input wire [15:0] pixel,
 input wire [85:0] snapshot,input wire snapshot_toggle,
 input wire [12:0] angle_bcd,input wire angle_toggle,
 output wire [15:0] result,output reg enabled);
 (* async_reg="true" *)reg [2:0] toggle_sync;
 (* async_reg="true" *)reg [1:0] key_sync;
 reg [85:0] pending,visible;
 reg vs_d;
 // Stable angle bus is held between source-frame commits. Synchronize its
 // toggle, capture after settling, then publish only at display VS.
 (* async_reg="true" *) reg [2:0] angle_sync;
 reg [12:0] angle_pending,angle_visible;
 always @(posedge clk)begin
  if(!rstn)begin angle_sync<=0;angle_pending<=0;angle_visible<=0;end
  else if(SHOW_ANGLE)begin
   angle_sync<={angle_sync[1:0],angle_toggle};
   if(angle_sync[2]!=angle_sync[1])angle_pending<=angle_bcd;
   if(vs&&!vs_d)angle_visible<=angle_pending;
  end
 end
 (* async_reg="true" *)reg [2:0] c2_toggle_sync;
 (* async_reg="true" *)reg [1:0] c2_phase_pix;
 reg [18:0] c2_pending,c2_visible;reg phase_visible;
 always @(posedge clk)begin
  if(!rstn)begin c2_toggle_sync<=0;c2_phase_pix<=0;c2_pending<=0;c2_visible<=0;phase_visible<=0;end
  else begin
   c2_toggle_sync<={c2_toggle_sync[1:0],c2_status_toggle};c2_phase_pix<={c2_phase_pix[0],c2_phase};
   if(c2_toggle_sync[2]!=c2_toggle_sync[1])c2_pending<=c2_status;
   if(vs&&!vs_d)begin c2_visible<=c2_pending;phase_visible<=c2_phase_pix[1];end
  end
 end
 function [7:0] hexchar(input [3:0] n);
  begin hexchar=(n<10)?("0"+n):("A"+n-10);end
 endfunction
 (* async_reg="true" *)reg [1:0] camera_sync;
 reg camera_visible;
 (* async_reg="true" *)reg [1:0] frozen_sync;reg frozen_visible;
 (* async_reg="true" *)reg [3:0] fusion_sync1,fusion_sync2;reg [3:0] fusion_visible;
 reg stable_key,want_enabled;
 reg [19:0] debounce;
 always @(posedge clk)begin
  if(!rstn)begin
   frozen_sync<=0;frozen_visible<=0;fusion_sync1<=0;fusion_sync2<=0;fusion_visible<=0;camera_sync<=0;camera_visible<=0;toggle_sync<=0;key_sync<=3;pending<=0;visible<=0;stable_key<=1;
   want_enabled<=1;enabled<=1;vs_d<=0;debounce<=0;
  end else begin
   fusion_sync1<={fusion_enabled,fusion_used,format2};fusion_sync2<=fusion_sync1;
   camera_sync<={camera_sync[0],camera_selected};
   frozen_sync<={frozen_sync[0],frozen};
   toggle_sync<={toggle_sync[1:0],snapshot_toggle};key_sync<={key_sync[0],key_n};vs_d<=vs;
   if(toggle_sync[2]!=toggle_sync[1])pending<=snapshot;
   if(vs&&!vs_d)begin visible<=pending;enabled<=want_enabled;camera_visible<=camera_sync[1];fusion_visible<=fusion_sync2;frozen_visible<=frozen_sync[1];end
   if(key_sync[1]==stable_key)debounce<=0;
   else if(debounce==DEBOUNCE_CYCLES-1)begin
    stable_key<=key_sync[1];debounce<=0;
    if(!key_sync[1])want_enabled<=!want_enabled;
   end else debounce<=debounce+1'b1;
  end
 end
 function [63:0] font(input [7:0] c);
  begin case(c)
   "0":font=64'h3c666e7666663c00; "1":font=64'h1838181818187e00;
   "2":font=64'h3c66060c30607e00; "3":font=64'h3c66061c06663c00;
   "4":font=64'h0c1c3c6c7e0c0c00; "5":font=64'h7e607c0606663c00;
   "6":font=64'h1c30607c66663c00; "7":font=64'h7e66060c18181800;
   "8":font=64'h3c66663c66663c00; "9":font=64'h3c66663e060c3800;
   "S":font=64'h3c60603c06067c00; "R":font=64'h7c66667c6c666600;
   "C":font=64'h3c66606060663c00; "O":font=64'h3c66666666663c00;
   "U":font=64'h6666666666663c00; "T":font=64'h7e18181818181800;
   "F":font=64'h7e60607c60606000; "P":font=64'h7c66667c60606000;
   "A":font=64'h183c66667e666600; "L":font=64'h6060606060607e00;
   "Y":font=64'h6666663c18183c00;
   "B":font=64'h7c66667c66667c00; "D":font=64'h786c6666666c7800;
   "E":font=64'h7e60607c60607e00; "I":font=64'h7e18181818187e00;
   "N":font=64'h66767e7e6e666600;
   "Q":font=64'h3c6666666e3c0600;
   "V":font=64'h66666666663c1800;
   "G":font=64'h3c66606e66663e00;
   "M":font=64'h63777f6b63636300;
   "H":font=64'h6666667e66666600; "W":font=64'h6363636b7f776300;
   "K":font=64'h666c7870786c6600; ".":font=64'h0000000000181800;
   "Z":font=64'h7e060c1830607e00; "-":font=64'h0000007e00000000;
   "+":font=64'h0018187e18180000;
   default:font=0;
  endcase end
 endfunction
 wire [11:0] relx=x-12'd16,rely=y-12'd16;
 wire [4:0] line=rely[8:4];wire [3:0] column=relx[7:4];
 reg [7:0] character;
 reg [11:0] number;
 always @*begin
  character=" ";number=(line==0)?visible[35:24]:(line==1)?visible[23:12]:visible[11:0];
  if(line<2)begin
   case(column)
    0:character=(line==0)?"S":"O";
    1:character=(line==0)?"R":"U";
    2:character=(line==0)?"C":"T";
    4:character="0"+number[11:8];5:character="0"+number[7:4];6:character="0"+number[3:0];
    8:character="F";9:character="P";10:character="S";
   endcase
  end else if(line==2)begin
   case(column)
    0:character="C";1:character="A";2:character="L";3:character="C";
    5:character="0"+number[11:8];6:character="0"+number[7:4];7:character="0"+number[3:0];
    9:character="M";10:character="S";
   endcase
  end else if(line==3)begin
   // Bit 41: host coefficients active; bit 40: local correction enabled.
   // Local strength/zoom are active-frame state, not pending button requests.
   case(column)
    0:character=visible[41]?"H":visible[40]?"C":"R";
    1:character=visible[41]?"S":visible[40]?"O":"A";
    2:character=visible[41]?"T":visible[40]?"R":"W";
    4:character="M";
    5:character="1";
    7:character="Z";
    8:character=visible[41]?"-":("0"+{6'd0,visible[37:36]});
    10:character="H";11:character=frozen_visible?"1":"0";
   endcase
  end else if(line==4)begin
   case(column)
    0:character="P";1:character="C";2:character="K";
    4:character="0"+visible[57:54];5:character="0"+visible[53:50];
    6:character="0"+visible[49:46];7:character=".";8:character="0"+visible[45:42];
    10:character="M";
   endcase
  end else if(line==5)begin
   case(column)
    0:character="F";1:character="O";2:character="C";
    4:character="0"+visible[73:70];5:character="0"+visible[69:66];
    6:character="0"+visible[65:62];7:character="0"+visible[61:58];
    9:character="G";10:character="0"+{6'd0,visible[75:74]};
   endcase
  end else if(line==6)begin
   case(column)
    0:character="Y";2:character="0"+visible[83:80];3:character="0"+visible[79:76];
    5:character="T";6:character="0"+{6'd0,visible[85:84]};
    8:character=fusion_visible[3]?"F":"C";9:character=fusion_visible[3]?(fusion_visible[2]?"1":"0"):(camera_visible?"2":"1");
    10:character=(SINGLE_CAMERA && !DIAGNOSTICS)?" ":"R";11:character=(SINGLE_CAMERA && !DIAGNOSTICS)?" ":("0"+{6'd0,fusion_visible[1:0]});
   endcase
  end else if(line==7)begin
   case(column)
    0:character="Q";2:character="0"+{6'd0,display_quality};
    4:if(SHOW_ANGLE)character="A";
    6:if(SHOW_ANGLE)character=angle_visible[12]?"-":"+";
    7:if(SHOW_ANGLE)character="0"+angle_visible[11:8];
    8:if(SHOW_ANGLE)character="0"+angle_visible[7:4];
    9:if(SHOW_ANGLE)character="0"+angle_visible[3:0];
   endcase
  end else if(line==8)begin
   case(column)
    0:character="I";1:character="0"+c2_visible[0];
    3:character="E";4:character="0"+c2_visible[1];
    6:character="D";7:character=hexchar(c2_visible[10:7]);8:character=hexchar(c2_visible[6:3]);
    10:character="B";11:character="0"+c2_visible[2];
   endcase
  end else if(line==9)begin
   case(column)
    0:character="S";1:character="0"+phase_visible;
    3:character="N";4:character=hexchar(c2_visible[18:15]);5:character=hexchar(c2_visible[14:11]);
   endcase
  end else if(SINGLE_CAMERA && DIAGNOSTICS && line>=10 && line<=13)begin
   if(column==0)character="0"+(line-10)*2;
   else if(column>=2 && column<=5)character=hexchar(probe[((line-10)*2)*16+(5-column)*4+:4]);
   else if(column>=7 && column<=10)character=hexchar(probe[((line-10)*2+1)*16+(10-column)*4+:4]);
  end else if(SINGLE_CAMERA && DIAGNOSTICS && line==14)begin
   if(column==0)character="O";else if(column>=1 && column<=4)character=hexchar(probe[128+(4-column)*4+:4]);
   else if(column==6)character="A";else if(column>=7 && column<=10)character=hexchar(probe[144+(10-column)*4+:4]);
  end else if(SINGLE_CAMERA && DIAGNOSTICS && line==15)begin
   case(column)
    0:character="V";1:character="0"+probe[204];3:character="M";4:character=hexchar(probe[167:164]);5:character=hexchar(probe[163:160]);
   endcase
   if(column>=7 && column<=11)character=hexchar(probe[168+(11-column)*4+:4]);
  end else if(SINGLE_CAMERA && DIAGNOSTICS && line==16)begin
   case(column)
    0:character="T";1:character=hexchar(probe[203:200]);2:character=hexchar(probe[199:196]);
    4:character="R";5:character=hexchar(probe[195:192]);6:character=hexchar(probe[191:188]);
   endcase
  end
 end
 wire in_box=de && x>=16 && x<208 && y>=16 && y<(SINGLE_CAMERA?(DIAGNOSTICS?288:144):176);
 // Optional boundary between status/character selection and glyph lookup.
 // Delay pixel/box in the same stage; the caller must delay video sync by one cycle.
 reg [7:0] glyph_character;
 reg [5:0] glyph_position;
 reg glyph_overlay;
 reg [15:0] glyph_pixel;
 always @(posedge clk)begin
  if(!rstn)begin glyph_character<=0;glyph_position<=0;glyph_overlay<=0;glyph_pixel<=0;end
  else begin glyph_character<=character;glyph_position<={rely[3:1],relx[3:1]};
   glyph_overlay<=enabled && in_box;glyph_pixel<=pixel;end
 end
 wire [63:0] bitmap=font(PIPELINE_FONT?glyph_character:character);
 wire [5:0] bitmap_position=PIPELINE_FONT?glyph_position:{rely[3:1],relx[3:1]};
 wire ink=bitmap[63-bitmap_position];
 assign overlay_active=PIPELINE_FONT?glyph_overlay:(enabled && in_box);
 assign result=overlay_active?(ink?16'hffff:16'h0000):(PIPELINE_FONT?glyph_pixel:pixel);
endmodule
`default_nettype wire
