`timescale 1ns/1ps
`default_nettype none
// Two source-window banks overlap the next DDR fetch with rendering.
// One coordinate pipeline serves bbox and pixels, tagged for all 27 stages.
module warp_frame #(
 parameter integer AW=28,COLS=40,ROWS=23,WORDS_PER_LINE=640,
 parameter integer V_ACT=720,SRC_H=720,TILE=16,SRC_STRIDE=640,
 parameter integer BBOX_LOOKAHEAD=1, AFFINE_FRAC_BITS=16,
 parameter integer SRC_W=SRC_STRIDE*2,RADIAL_MODEL_LUT=0,
 parameter RADIAL_LUT_FILE=""
)(
 input wire clk,rstn,
 input wire signed [31:0] A,B,C,D,E,F,k1,k2,p1,p2,fx,fy,cx,cy,
 input wire [AW-1:0] src_base,dst_base,
 input wire start,input wire lut_enable,output reg busy,done,
 output wire r_req,output wire [AW-1:0] r_addr,output wire [7:0] r_beats,
 input wire r_ready,r_done,input wire [255:0] r_data,input wire r_valid,r_last,
 output wire w_req,output wire [AW-1:0] w_addr,output wire [7:0] w_beats,
 input wire w_ready,w_done,output wire [255:0] w_data,input wire w_adv,
 output wire overflow
);
 localparam P_FREE=0,P_BB=1,P_BWAIT=2,P_SET=3,P_FETCH=4,P_FWAIT=5,P_STOP=6,P_RAWLIMIT=7;
 reg [3:0] st;
 reg [15:0] tx,ty;
 reg [2:0] issue_corner,received_corner;
 reg bb_valid;reg [15:0] bb_x,bb_y;
 reg signed [16:0] mn_u,mx_u,mn_v,mx_v;
 reg [15:0] win_u,win_v;
 reg [6:0] fetch_width,fetch_height;
 reg [6:0] raw_width_limit,raw_height_limit;
 // Only a positive axis-aligned affine with zero distortion is monotonic
 // independently in x/y. Its corner bounds need just the bilinear neighbour,
 // not the nonlinear model's two-pixel guard. Pixel mapping is unchanged.
 wire no_distortion=RADIAL_MODEL_LUT?!lut_enable:(k1==0 && k2==0 && p1==0 && p2==0);
 wire axis_raw=(no_distortion && B==0 && D==0 && A>0 && E>0 && fx>0 && fy>0);
 reg fetch_start,fetch_bank;
 wire fetch_busy,fetch_done,fetch_we;
 wire [7:0] fetch_addr;wire [255:0] fetch_data;
 reg [1:0] valid_bank;
 reg [15:0] tile_x[0:1],tile_y[0:1],origin_u[0:1],origin_v[0:1];
 reg [6:0] bank_width[0:1],bank_height[0:1],render_width,render_height;
 reg render_bank,want_bank,render_active,render_started,render_start,all_rendered;
 reg [15:0] render_x,render_y,render_u,render_v;
 wire render_busy,pixel_request,pack_ready,pack_idle;
 wire [15:0] pixel_x,pixel_y;
 wire map_valid,map_in_frame;wire signed [15:0] map_ui,map_vi;
 wire [7:0] map_uf,map_vf;
 reg [26:0] bbox_tags;
 wire bbox_result=map_valid && bbox_tags[26];
 wire pixel_result=map_valid && !bbox_tags[26];
 wire signed [16:0] cu={map_ui[15],map_ui},cv={map_vi[15],map_vi};
 // Pause pixel issuance for four bbox inputs, without stalling earlier pixels.
 coord_map #(.W(SRC_W),.H(SRC_H),.AFFINE_FRAC_BITS(AFFINE_FRAC_BITS),
  .RADIAL_MODEL_LUT(RADIAL_MODEL_LUT),.RADIAL_LUT_FILE(RADIAL_LUT_FILE)) u_bbox(
  .clk(clk),.rstn(rstn),.A(A),.B(B),.C(C),.D(D),.E(E),.F(F),
  .k1(k1),.k2(k2),.p1(p1),.p2(p2),.fx(fx),.fy(fy),.cx(cx),.cy(cy),
  .valid_i(bb_valid || pixel_request),.x_i(bb_valid?bb_x:pixel_x),.y_i(bb_valid?bb_y:pixel_y),.lut_enable(lut_enable),
  .valid_o(map_valid),.u_q16(),.v_q16(),.in_frame(map_in_frame),
  .u_int(map_ui),.v_int(map_vi),.u_frac(map_uf),.v_frac(map_vf));
 always @(posedge clk)begin
  if(!rstn)bbox_tags<=0;else bbox_tags<={bbox_tags[25:0],bb_valid};
 end
 tile_fetch_v2 #(.BW(64),.BH(64),.AW(AW)) u_fetch(
  .clk(clk),.rstn(rstn),.start(fetch_start),.base_addr(src_base),.stride_words(SRC_STRIDE[15:0]),
  .u0(win_u),.v0(win_v),.bw(fetch_width),.bh(fetch_height),
  .r_req(r_req),.r_addr(r_addr),.r_beats(r_beats),.r_ready(r_ready),.r_done(r_done),
  .r_data(r_data),.r_valid(r_valid),.r_last(r_last),
  .we(fetch_we),.waddr(fetch_addr),.wdata(fetch_data),.busy(fetch_busy),.done(fetch_done));
 wire [5:0] qx0,qx1,qy0,qy1;
 wire [15:0] a00,a01,a10,a11,b00,b01,b10,b11;
 tile_ram_quad u_ram0(.clk(clk),.we(fetch_we && !fetch_bank),.waddr(fetch_addr),.wdata(fetch_data),
  .x0(qx0),.x1(qx1),.y0(qy0),.y1(qy1),.p00(a00),.p01(a01),.p10(a10),.p11(a11));
 tile_ram_quad u_ram1(.clk(clk),.we(fetch_we && fetch_bank),.waddr(fetch_addr),.wdata(fetch_data),
  .x0(qx0),.x1(qx1),.y0(qy0),.y1(qy1),.p00(b00),.p01(b01),.p10(b10),.p11(b11));
 wire wp_we;wire [15:0] wp_x,wp_y,wp_pix;
 warp_tile_stream #(.TILE(TILE),.SRC_W(SRC_W),.SRC_H(SRC_H),.CHECK_WINDOW(1)) u_warp(
  .clk(clk),.rstn(rstn),.start(render_start),.tx(render_x),.ty(render_y),.u0(render_u),.v0(render_v),
  .window_width(render_width),.window_height(render_height),
  .pixel_ready(pack_ready && !bb_valid),.map_request(pixel_request),.map_x(pixel_x),.map_y(pixel_y),
  .map_valid(pixel_result),.map_in_frame(map_in_frame),.map_ui(map_ui),.map_vi(map_vi),.map_uf(map_uf),.map_vf(map_vf),
  .x0(qx0),.x1(qx1),.y0(qy0),.y1(qy1),
  .p00(render_bank?b00:a00),.p01(render_bank?b01:a01),.p10(render_bank?b10:a10),.p11(render_bank?b11:a11),
  .we(wp_we),.ox(wp_x),.oy(wp_y),.pix(wp_pix),.busy(render_busy));
 out_pack #(.TEST_PAT(0),.AW(AW),.WORDS_PER_LINE(WORDS_PER_LINE),.V_ACT(V_ACT),.RESERVE_PACKETS(3)) u_pack(
  .clk(clk),.rstn(rstn),.dst_base(dst_base),.we(wp_we),.ox(wp_x),.oy(wp_y),.pix(wp_pix),
  .w_req(w_req),.w_addr(w_addr),.w_beats(w_beats),.w_ready(w_ready),.w_done(w_done),.w_data(w_data),.w_adv(w_adv),
  .overflow(overflow),.idle(pack_idle),.pixel_ready(pack_ready));
 function [6:0] clipped_width(input signed [17:0] n);
  begin clipped_width=(n<16)?16:((n>64)?64:((n+15)&18'h3fff0));end
 endfunction
 function [6:0] clipped_height(input signed [17:0] n);
  begin clipped_height=(n<1)?1:((n>64)?64:n);end
 endfunction
 function [6:0] raw_width(input signed [17:0] n,input [6:0] limit);
  begin raw_width=(n<16)?16:((n>$signed({11'd0,limit}))?limit:((n+15)&18'h3fff0));end
 endfunction
 function [6:0] raw_height(input signed [17:0] n,input [6:0] limit);
  begin raw_height=(n<1)?1:((n>$signed({11'd0,limit}))?limit:n);end
 endfunction
 integer i;
 always @(posedge clk)begin
  if(!rstn)begin
   busy<=0;done<=0;st<=P_STOP;tx<=0;ty<=0;issue_corner<=0;received_corner<=0;
   bb_valid<=0;bb_x<=0;bb_y<=0;mn_u<=0;mx_u<=0;mn_v<=0;mx_v<=0;
   win_u<=0;win_v<=0;fetch_width<=64;fetch_height<=64;fetch_start<=0;fetch_bank<=0;raw_width_limit<=64;raw_height_limit<=64;
   valid_bank<=0;render_bank<=0;want_bank<=0;render_active<=0;render_started<=0;
   render_start<=0;all_rendered<=0;render_x<=0;render_y<=0;render_u<=0;render_v<=0;render_width<=0;render_height<=0;
   for(i=0;i<2;i=i+1)begin tile_x[i]<=0;tile_y[i]<=0;origin_u[i]<=0;origin_v[i]<=0;bank_width[i]<=0;bank_height[i]<=0;end
  end else begin
   done<=0;bb_valid<=0;render_start<=0;fetch_start<=0;
   if(!busy)begin
    if(start)begin
     busy<=1;st<=P_FREE;tx<=0;ty<=0;issue_corner<=0;received_corner<=0;
     valid_bank<=0;fetch_bank<=0;want_bank<=0;render_active<=0;render_started<=0;all_rendered<=0;
    end
   end else begin
    // A render claim covers startup and drain, when render_busy itself is low.
    if(!render_active && !all_rendered && valid_bank[want_bank])begin
     render_bank<=want_bank;render_x<=tile_x[want_bank];render_y<=tile_y[want_bank];
     render_u<=origin_u[want_bank];render_v<=origin_v[want_bank];
     render_width<=bank_width[want_bank];render_height<=bank_height[want_bank];
     valid_bank[want_bank]<=0;render_start<=1;render_active<=1;render_started<=0;
    end else if(render_active)begin
     if(render_busy)render_started<=1;
     if(render_started && !render_busy)begin
      render_active<=0;render_started<=0;want_bank<=!want_bank;
      if(render_x+TILE>=WORDS_PER_LINE*2 && render_y+TILE>=V_ACT)all_rendered<=1;
     end
    end
    case(st)
     // Bbox uses only map arithmetic, not the target RAM bank. Compute it
     // while that bank is still draining; protect the actual fetch below.
     P_FREE:if(BBOX_LOOKAHEAD || (!valid_bank[fetch_bank] && !(render_active && render_bank==fetch_bank)))begin
      issue_corner<=0;received_corner<=0;st<=P_BB;
     end
     P_BB:begin
      case(issue_corner)
       0:begin bb_x<=tx;bb_y<=ty;end
       1:begin bb_x<=tx+TILE-1;bb_y<=ty;end
       2:begin bb_x<=tx;bb_y<=ty+TILE-1;end
       3:begin bb_x<=tx+TILE-1;bb_y<=ty+TILE-1;end
      endcase
      bb_valid<=1;
      if(issue_corner==3)st<=P_BWAIT;else issue_corner<=issue_corner+1'b1;
     end
     P_BWAIT:if(bbox_result)begin
      if(received_corner==0)begin mn_u<=cu;mx_u<=cu;mn_v<=cv;mx_v<=cv;end
      else begin
       if(cu<mn_u)mn_u<=cu;if(cu>mx_u)mx_u<=cu;
       if(cv<mn_v)mn_v<=cv;if(cv>mx_v)mx_v<=cv;
      end
      if(received_corner==3)st<=P_SET;else received_corner<=received_corner+1'b1;
     end
     P_SET:begin
      if(axis_raw)begin
       win_u<=(mn_u<=0)?0:((mn_u>SRC_W-16)?SRC_W-16:(mn_u&17'h1fff0));
       win_v<=(mn_v<=0)?0:((mn_v>SRC_H-1)?SRC_H-1:mn_v);
       st<=P_RAWLIMIT;
      end else begin
       win_u<=(mn_u<=2)?0:((((mn_u-2)&17'h1fff0)>SRC_W-64)?SRC_W-64:((mn_u-2)&17'h1fff0));
       win_v<=(mn_v<=2)?0:((mn_v-2)>SRC_H-64?SRC_H-64:mn_v-2);
       st<=P_FETCH;
      end
     end
     P_RAWLIMIT:begin
      raw_width_limit<=(win_u>SRC_W-64)?SRC_W-win_u:64;
      raw_height_limit<=(win_v>SRC_H-64)?SRC_H-win_v:64;
      st<=P_FETCH;
     end
     P_FETCH:if(!valid_bank[fetch_bank] && !(render_active && render_bank==fetch_bank))begin
      fetch_width<=axis_raw?raw_width($signed(mx_u)-$signed({1'b0,win_u})+18'sd2,raw_width_limit):clipped_width($signed(mx_u)-$signed({1'b0,win_u})+18'sd4);
      fetch_height<=axis_raw?raw_height($signed(mx_v)-$signed({1'b0,win_v})+18'sd2,raw_height_limit):clipped_height($signed(mx_v)-$signed({1'b0,win_v})+18'sd4);
      fetch_start<=1;st<=P_FWAIT;
     end
     P_FWAIT:if(fetch_done)begin
      tile_x[fetch_bank]<=tx;tile_y[fetch_bank]<=ty;origin_u[fetch_bank]<=win_u;origin_v[fetch_bank]<=win_v;
      bank_width[fetch_bank]<=fetch_width;bank_height[fetch_bank]<=fetch_height;
      valid_bank[fetch_bank]<=1;fetch_bank<=!fetch_bank;
      if(tx+TILE>=WORDS_PER_LINE*2)begin
       tx<=0;
       if(ty+TILE>=V_ACT)st<=P_STOP;
       else begin ty<=ty+TILE;st<=P_FREE;end
      end else begin tx<=tx+TILE;st<=P_FREE;end
     end
    endcase
    if(all_rendered && pack_idle)begin busy<=0;done<=1;end
   end
  end
 end
endmodule
`default_nettype wire
