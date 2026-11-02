`timescale 1ns/1ps
`default_nettype none
module out_pack #(parameter integer TEST_PAT=0, WORDS_PER_LINE=640, AW=28, V_ACT=720,RESERVE_PACKETS=0)(
 input wire clk,rstn,input wire [AW-1:0] dst_base,
 input wire we,input wire [15:0] ox,oy,pix,
 output reg w_req,output reg [AW-1:0] w_addr,output wire [7:0] w_beats,
 input wire w_ready,w_done,output wire [255:0] w_data,input wire w_adv,
 output reg overflow,output wire idle,output wire pixel_ready);
 reg [AW-1:0] row_offset,packet_base,packet_addr;
 reg [15:0] word_x;
 reg [255:0] assembly;
 reg [3:0] count;
 reg [AW-1:0] addr_mem[0:7];
 reg [255:0] data0;
 reg [255:0] data1;
 reg [255:0] data2;
 reg [255:0] data3;
 reg [255:0] data4;
 reg [255:0] data5;
 reg [255:0] data6;
 reg [255:0] data7;
 reg [3:0] wp,rp;
 wire empty=(wp==rp);
 wire full=(wp[3]!=rp[3]) && (wp[2:0]==rp[2:0]);
 wire [3:0] used=wp-rp;
 // Reserve one full packet for pixels already in the RAM/interpolation pipeline.
 assign pixel_ready=(used < 8-RESERVE_PACKETS);
 wire [15:0] color=TEST_PAT?16'hf800:pix;
 reg [1:0] st;
 reg [255:0] payload;
 assign w_data=payload;
 assign w_beats=8'd1;
 assign idle=empty && st==0 && count==0 && !we;
 always @(posedge clk) begin
  if(!rstn) begin row_offset<=0;packet_base<=0;packet_addr<=0;word_x<=0;assembly<=0;count<=0;wp<=0;overflow<=0;end
  else begin
   packet_addr<=packet_base+row_offset+word_x;
   if(we) begin
   if(count==0)begin row_offset<=oy*WORDS_PER_LINE;packet_base<=dst_base;word_x<=ox>>1;end
   if(count==15) begin
    count<=0;assembly<=0;
    if(oy<V_ACT) begin
     if(!full) begin
      case(wp[2:0])
       3'd0:data0<= {color,assembly[239:0]};
       3'd1:data1<= {color,assembly[239:0]};
       3'd2:data2<= {color,assembly[239:0]};
       3'd3:data3<= {color,assembly[239:0]};
       3'd4:data4<= {color,assembly[239:0]};
       3'd5:data5<= {color,assembly[239:0]};
       3'd6:data6<= {color,assembly[239:0]};
       3'd7:data7<= {color,assembly[239:0]};
      endcase
      addr_mem[wp[2:0]]<=packet_addr;
      wp<=wp+1'b1;
     end else overflow<=1;
    end
   end else begin assembly[count*16+:16]<=color;count<=count+1'b1;end
  end
 end
 end
 always @(posedge clk) begin
  if(!rstn) begin st<=0;rp<=0;w_req<=0;w_addr<=0;payload<=0;end
  else case(st)
   0:if(!empty) begin
      case(rp[2:0])
       3'd0:payload<=data0;
       3'd1:payload<=data1;
       3'd2:payload<=data2;
       3'd3:payload<=data3;
       3'd4:payload<=data4;
       3'd5:payload<=data5;
       3'd6:payload<=data6;
       3'd7:payload<=data7;
      endcase
      w_addr<=addr_mem[rp[2:0]];w_req<=1;st<=1;
     end
   1:if(w_ready) begin w_req<=0;st<=2;end
   2:if(w_adv) begin if(w_done) begin rp<=rp+1'b1;st<=0;end else st<=3;end
   3:if(w_done) begin rp<=rp+1'b1;st<=0;end
  endcase
 end
endmodule
`default_nettype wire
