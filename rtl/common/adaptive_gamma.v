`timescale 1ns/1ps
`default_nettype none
// Frame-adaptive RGB565 Gamma. No frame/line buffer, no backpressure.
// One source-clock output register delays pixel/DE/VS together. Reset bypasses.
module adaptive_gamma #(parameter integer WIDTH=1280,HEIGHT=720,DEBOUNCE_CYCLES=1000000)(
 input wire clk,rstn,vs,de,key_n,test_key_n,input wire [15:0] pixel,
 output reg vs_o,de_o,output reg [15:0] pixel_o,
 output reg active_enabled,output reg [1:0] active_curve,
 output reg [1:0] status_code,output reg status_toggle,
 output reg [1:0] active_test_mode,
 output reg [7:0] mean_luma_bcd,output reg mean_toggle);
 localparam integer TOTAL=WIDTH*HEIGHT;
 (* async_reg="true" *)reg [1:0] key_sync;
 reg key_stable,want_enabled;reg [19:0] debounce;
 (* async_reg="true" *)reg [1:0] test_key_sync;
 reg test_key_stable;reg [19:0] test_debounce;reg [1:0] want_test_mode;
 reg mean_busy;reg [2:0] mean_bit;reg [31:0] mean_remainder;reg [5:0] mean_work;
 reg mean_convert;reg [5:0] mean_result;
 reg vs_q,mark_q,de_q;reg [5:0] luma_q;
 reg armed;reg [20:0] count;reg [31:0] sum;
 reg [1:0] estimated_curve,proposal_last;reg proposal_seen;
 wire marker=vs && !vs_q;
 // T1/T2 are explicit digital stimulus modes, not natural low/high-light claims.
 wire [4:0] inv_r=5'd31-pixel[15:11],inv_b=5'd31-pixel[4:0];
 wire [5:0] inv_g=6'd63-pixel[10:5];
 wire [15:0] test_pixel=(active_test_mode==1)?
       {2'b0,pixel[15:13],2'b0,pixel[10:7],2'b0,pixel[4:2]}:
       (active_test_mode==2)?{(5'd31-(inv_r>>2)),(6'd63-(inv_g>>2)),(5'd31-(inv_b>>2))}:pixel;
 wire [5:0] red6={test_pixel[15:11],test_pixel[15]},blue6={test_pixel[4:0],test_pixel[4]};
 wire [7:0] weighted={2'b0,red6}+{1'b0,test_pixel[10:5],1'b0}+{2'b0,blue6};
 wire [31:0] mean_weight=TOTAL<<mean_bit;
 wire [5:0] mean_next=mean_work | ((mean_remainder>=mean_weight)?(6'd1<<mean_bit):6'd0);
 function [7:0] bcd6(input [5:0] n);
  reg [3:0] tens,ones;
  begin
   tens=(n>=60)?6:(n>=50)?5:(n>=40)?4:(n>=30)?3:(n>=20)?2:(n>=10)?1:0;
   ones=n-tens*10;bcd6={tens,ones};
  end
 endfunction
 function [1:0] choose_curve(input [31:0] s,input [1:0] previous);
  begin
   case(previous)
    1:choose_curve=(s<=TOTAL*24)?1:((s>TOTAL*46)?2:0);
    2:choose_curve=(s>=TOTAL*40)?2:((s<TOTAL*18)?1:0);
    default:choose_curve=(s<TOTAL*18)?1:((s>TOTAL*46)?2:0);
   endcase
  end
 endfunction
 function [4:0] gamma5(input [4:0] value,input [1:0] curve);
  begin case({curve,value})
   7'd32:gamma5=5'd0;
   7'd33:gamma5=5'd2;
   7'd34:gamma5=5'd4;
   7'd35:gamma5=5'd5;
   7'd36:gamma5=5'd7;
   7'd37:gamma5=5'd8;
   7'd38:gamma5=5'd9;
   7'd39:gamma5=5'd10;
   7'd40:gamma5=5'd11;
   7'd41:gamma5=5'd12;
   7'd42:gamma5=5'd13;
   7'd43:gamma5=5'd14;
   7'd44:gamma5=5'd15;
   7'd45:gamma5=5'd16;
   7'd46:gamma5=5'd17;
   7'd47:gamma5=5'd18;
   7'd48:gamma5=5'd19;
   7'd49:gamma5=5'd20;
   7'd50:gamma5=5'd21;
   7'd51:gamma5=5'd21;
   7'd52:gamma5=5'd22;
   7'd53:gamma5=5'd23;
   7'd54:gamma5=5'd24;
   7'd55:gamma5=5'd25;
   7'd56:gamma5=5'd26;
   7'd57:gamma5=5'd26;
   7'd58:gamma5=5'd27;
   7'd59:gamma5=5'd28;
   7'd60:gamma5=5'd29;
   7'd61:gamma5=5'd29;
   7'd62:gamma5=5'd30;
   7'd63:gamma5=5'd31;
   7'd64:gamma5=5'd0;
   7'd65:gamma5=5'd0;
   7'd66:gamma5=5'd1;
   7'd67:gamma5=5'd2;
   7'd68:gamma5=5'd2;
   7'd69:gamma5=5'd3;
   7'd70:gamma5=5'd4;
   7'd71:gamma5=5'd5;
   7'd72:gamma5=5'd6;
   7'd73:gamma5=5'd7;
   7'd74:gamma5=5'd8;
   7'd75:gamma5=5'd8;
   7'd76:gamma5=5'd9;
   7'd77:gamma5=5'd10;
   7'd78:gamma5=5'd11;
   7'd79:gamma5=5'd13;
   7'd80:gamma5=5'd14;
   7'd81:gamma5=5'd15;
   7'd82:gamma5=5'd16;
   7'd83:gamma5=5'd17;
   7'd84:gamma5=5'd18;
   7'd85:gamma5=5'd19;
   7'd86:gamma5=5'd20;
   7'd87:gamma5=5'd21;
   7'd88:gamma5=5'd23;
   7'd89:gamma5=5'd24;
   7'd90:gamma5=5'd25;
   7'd91:gamma5=5'd26;
   7'd92:gamma5=5'd27;
   7'd93:gamma5=5'd29;
   7'd94:gamma5=5'd30;
   7'd95:gamma5=5'd31;
   default:gamma5=value;
  endcase end
 endfunction
 function [5:0] gamma6(input [5:0] value,input [1:0] curve);
  begin case({curve,value})
   8'd64:gamma6=6'd0;
   8'd65:gamma6=6'd3;
   8'd66:gamma6=6'd5;
   8'd67:gamma6=6'd6;
   8'd68:gamma6=6'd8;
   8'd69:gamma6=6'd9;
   8'd70:gamma6=6'd11;
   8'd71:gamma6=6'd12;
   8'd72:gamma6=6'd13;
   8'd73:gamma6=6'd15;
   8'd74:gamma6=6'd16;
   8'd75:gamma6=6'd17;
   8'd76:gamma6=6'd18;
   8'd77:gamma6=6'd19;
   8'd78:gamma6=6'd20;
   8'd79:gamma6=6'd21;
   8'd80:gamma6=6'd23;
   8'd81:gamma6=6'd24;
   8'd82:gamma6=6'd25;
   8'd83:gamma6=6'd26;
   8'd84:gamma6=6'd27;
   8'd85:gamma6=6'd28;
   8'd86:gamma6=6'd29;
   8'd87:gamma6=6'd30;
   8'd88:gamma6=6'd31;
   8'd89:gamma6=6'd31;
   8'd90:gamma6=6'd32;
   8'd91:gamma6=6'd33;
   8'd92:gamma6=6'd34;
   8'd93:gamma6=6'd35;
   8'd94:gamma6=6'd36;
   8'd95:gamma6=6'd37;
   8'd96:gamma6=6'd38;
   8'd97:gamma6=6'd39;
   8'd98:gamma6=6'd40;
   8'd99:gamma6=6'd41;
   8'd100:gamma6=6'd41;
   8'd101:gamma6=6'd42;
   8'd102:gamma6=6'd43;
   8'd103:gamma6=6'd44;
   8'd104:gamma6=6'd45;
   8'd105:gamma6=6'd46;
   8'd106:gamma6=6'd46;
   8'd107:gamma6=6'd47;
   8'd108:gamma6=6'd48;
   8'd109:gamma6=6'd49;
   8'd110:gamma6=6'd50;
   8'd111:gamma6=6'd51;
   8'd112:gamma6=6'd51;
   8'd113:gamma6=6'd52;
   8'd114:gamma6=6'd53;
   8'd115:gamma6=6'd54;
   8'd116:gamma6=6'd55;
   8'd117:gamma6=6'd55;
   8'd118:gamma6=6'd56;
   8'd119:gamma6=6'd57;
   8'd120:gamma6=6'd58;
   8'd121:gamma6=6'd58;
   8'd122:gamma6=6'd59;
   8'd123:gamma6=6'd60;
   8'd124:gamma6=6'd61;
   8'd125:gamma6=6'd61;
   8'd126:gamma6=6'd62;
   8'd127:gamma6=6'd63;
   8'd128:gamma6=6'd0;
   8'd129:gamma6=6'd0;
   8'd130:gamma6=6'd1;
   8'd131:gamma6=6'd1;
   8'd132:gamma6=6'd2;
   8'd133:gamma6=6'd3;
   8'd134:gamma6=6'd3;
   8'd135:gamma6=6'd4;
   8'd136:gamma6=6'd5;
   8'd137:gamma6=6'd6;
   8'd138:gamma6=6'd6;
   8'd139:gamma6=6'd7;
   8'd140:gamma6=6'd8;
   8'd141:gamma6=6'd9;
   8'd142:gamma6=6'd10;
   8'd143:gamma6=6'd10;
   8'd144:gamma6=6'd11;
   8'd145:gamma6=6'd12;
   8'd146:gamma6=6'd13;
   8'd147:gamma6=6'd14;
   8'd148:gamma6=6'd15;
   8'd149:gamma6=6'd16;
   8'd150:gamma6=6'd17;
   8'd151:gamma6=6'd18;
   8'd152:gamma6=6'd19;
   8'd153:gamma6=6'd20;
   8'd154:gamma6=6'd21;
   8'd155:gamma6=6'd22;
   8'd156:gamma6=6'd23;
   8'd157:gamma6=6'd24;
   8'd158:gamma6=6'd25;
   8'd159:gamma6=6'd26;
   8'd160:gamma6=6'd27;
   8'd161:gamma6=6'd28;
   8'd162:gamma6=6'd29;
   8'd163:gamma6=6'd30;
   8'd164:gamma6=6'd31;
   8'd165:gamma6=6'd32;
   8'd166:gamma6=6'd33;
   8'd167:gamma6=6'd35;
   8'd168:gamma6=6'd36;
   8'd169:gamma6=6'd37;
   8'd170:gamma6=6'd38;
   8'd171:gamma6=6'd39;
   8'd172:gamma6=6'd40;
   8'd173:gamma6=6'd41;
   8'd174:gamma6=6'd43;
   8'd175:gamma6=6'd44;
   8'd176:gamma6=6'd45;
   8'd177:gamma6=6'd46;
   8'd178:gamma6=6'd47;
   8'd179:gamma6=6'd48;
   8'd180:gamma6=6'd50;
   8'd181:gamma6=6'd51;
   8'd182:gamma6=6'd52;
   8'd183:gamma6=6'd53;
   8'd184:gamma6=6'd54;
   8'd185:gamma6=6'd56;
   8'd186:gamma6=6'd57;
   8'd187:gamma6=6'd58;
   8'd188:gamma6=6'd59;
   8'd189:gamma6=6'd61;
   8'd190:gamma6=6'd62;
   8'd191:gamma6=6'd63;
   default:gamma6=value;
  endcase end
 endfunction
 wire [1:0] proposed=choose_curve(sum,estimated_curve);
 wire [1:0] next_status=want_enabled?(estimated_curve+2'd1):2'd0;
 always @(posedge clk)begin
  if(!rstn)begin
   key_sync<=3;key_stable<=1;want_enabled<=0;debounce<=0;
   test_key_sync<=3;test_key_stable<=1;test_debounce<=0;want_test_mode<=0;active_test_mode<=0;
   mean_busy<=0;mean_bit<=0;mean_remainder<=0;mean_work<=0;mean_luma_bcd<=0;mean_toggle<=0;
   mean_convert<=0;mean_result<=0;
   vs_q<=0;mark_q<=0;de_q<=0;luma_q<=0;
   armed<=0;count<=0;sum<=0;estimated_curve<=0;proposal_last<=0;proposal_seen<=0;
   active_enabled<=0;active_curve<=0;status_code<=0;status_toggle<=0;
   vs_o<=0;de_o<=0;pixel_o<=0;
  end else begin
   key_sync<={key_sync[0],key_n};
   if(key_sync[1]==key_stable)debounce<=0;
   else if(debounce==DEBOUNCE_CYCLES-1)begin
    key_stable<=key_sync[1];debounce<=0;
    if(!key_sync[1])want_enabled<=!want_enabled;
   end else debounce<=debounce+1'b1;
   test_key_sync<={test_key_sync[0],test_key_n};
   if(test_key_sync[1]==test_key_stable)test_debounce<=0;
   else if(test_debounce==DEBOUNCE_CYCLES-1)begin
    test_key_stable<=test_key_sync[1];test_debounce<=0;
    if(!test_key_sync[1])begin
     want_test_mode<=(want_test_mode==2)?0:want_test_mode+1'b1;
     // One-key demonstration: entering either stimulus enables adaptation;
     // returning to natural input restores bypass. KEY5 wins if both edges
     // debounce on the same clock. Actual pixels/state still commit at VS.
     want_enabled<=(want_test_mode!=2);
    end
   end else test_debounce<=test_debounce+1'b1;
   vs_q<=vs;mark_q<=marker;de_q<=de && !marker;luma_q<=weighted[7:2];
   // Publish only at the following marker, so short/overlong frames cannot
   // change the curve. Pipelined luma includes a last pixel adjacent to VS.
   if(mark_q)begin
    if(armed && count==TOTAL)begin
     mean_busy<=1;mean_bit<=5;mean_remainder<=sum;mean_work<=0;
     if(proposed==estimated_curve)proposal_seen<=0;
     else if(proposal_seen && proposal_last==proposed)begin
      estimated_curve<=proposed;proposal_seen<=0;
     end else begin proposal_last<=proposed;proposal_seen<=1;end
    end else proposal_seen<=0;
    armed<=1;count<=0;sum<=0;
   end else if(armed && de_q)begin
    if(count<TOTAL)begin count<=count+1'b1;sum<=sum+luma_q;end
    else count<=TOTAL+1;
   end
   // A six-cycle constant-divisor quotient gives a real 0..63 frame mean,
   // without a large combinatorial divider. Only completed frames start it.
   if(mean_busy && !(mark_q && armed && count==TOTAL))begin
    mean_work<=mean_next;
    if(mean_remainder>=mean_weight)mean_remainder<=mean_remainder-mean_weight;
    if(mean_bit==0)begin
     mean_busy<=0;mean_result<=mean_next;mean_convert<=1;
    end else mean_bit<=mean_bit-1'b1;
   end
   if(mean_convert)begin
    mean_convert<=0;mean_luma_bcd<=bcd6(mean_result);mean_toggle<=!mean_toggle;
   end
   if(marker)begin
    active_enabled<=want_enabled;active_curve<=estimated_curve;
    active_test_mode<=want_test_mode;
    if(next_status!=status_code || active_test_mode!=want_test_mode)begin
     status_code<=next_status;status_toggle<=!status_toggle;
    end
   end
   vs_o<=vs;de_o<=de;
   pixel_o<=active_enabled?{gamma5(test_pixel[15:11],active_curve),
                           gamma6(test_pixel[10:5],active_curve),gamma5(test_pixel[4:0],active_curve)}:test_pixel;
  end
 end
endmodule
`default_nettype wire
