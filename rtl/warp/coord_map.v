`timescale 1ns/1ps
`default_nettype none
// Reverse Brown-Conrady mapping, 27 clocks, one coordinate/clock.
// A/B/D/E may use Q24; C/F and every downstream stage remain Q16.
// Normalized coordinates are supported in [-4,+4]; other values mark invalid.
module coord_map #(parameter integer W=1280,H=720,AFFINE_FRAC_BITS=16,
 parameter integer RADIAL_MODEL_LUT=0,parameter RADIAL_LUT_FILE="")(
 input wire clk,rstn,input wire signed [31:0] A,B,C,D,E,F,k1,k2,p1,p2,fx,fy,cx,cy,
 input wire valid_i,input wire [15:0] x_i,y_i,input wire lut_enable,
 output reg valid_o,output reg signed [31:0] u_q16,v_q16,
 output reg in_frame,output reg signed [15:0] u_int,v_int,
 output reg [7:0] u_frac,v_frac);
 wire signed [17:0] aa=$signed(A[17:0]),bb=$signed(B[17:0]),dd=$signed(D[17:0]),ee=$signed(E[17:0]);
 wire signed[17:0]kk1=RADIAL_MODEL_LUT?18'sd0:$signed(k1[17:0]);
 wire signed[17:0]kk2=RADIAL_MODEL_LUT?18'sd0:$signed(k2[17:0]);
 // In LUT mode disabled means true RAW: both radial and tangential bypass.
 // Like all other coefficients, lut_enable must be committed per frame and
 // held until the 27-stage pipeline drains.
 wire signed[17:0]pp1=(RADIAL_MODEL_LUT && !lut_enable)?18'sd0:$signed(p1[17:0]);
 wire signed[17:0]pp2=(RADIAL_MODEL_LUT && !lut_enable)?18'sd0:$signed(p2[17:0]);
 wire signed [16:0] xx=$signed({1'b0,x_i}),yy=$signed({1'b0,y_i});
reg valid1;
reg signed [35:0] s1_axll;
reg signed [35:0] s1_axlh;
reg signed [35:0] s1_axhl;
reg signed [35:0] s1_axhh;
reg signed [35:0] s1_byll;
reg signed [35:0] s1_bylh;
reg signed [35:0] s1_byhl;
reg signed [35:0] s1_byhh;
reg signed [35:0] s1_dxll;
reg signed [35:0] s1_dxlh;
reg signed [35:0] s1_dxhl;
reg signed [35:0] s1_dxhh;
reg signed [35:0] s1_eyll;
reg signed [35:0] s1_eylh;
reg signed [35:0] s1_eyhl;
reg signed [35:0] s1_eyhh;
reg valid2;
reg signed [36:0] s2_axcross;
reg signed [35:0] s2_axll;
reg signed [35:0] s2_axhh;
reg signed [36:0] s2_bycross;
reg signed [35:0] s2_byll;
reg signed [35:0] s2_byhh;
reg signed [36:0] s2_dxcross;
reg signed [35:0] s2_dxll;
reg signed [35:0] s2_dxhh;
reg signed [36:0] s2_eycross;
reg signed [35:0] s2_eyll;
reg signed [35:0] s2_eyhh;
reg valid3;
reg signed [34:0] s3_ax;
reg signed [34:0] s3_by;
reg signed [34:0] s3_dx;
reg signed [34:0] s3_ey;
reg valid4;
reg signed [31:0] s4_ux;
reg signed [31:0] s4_uy;
reg valid5;
reg signed [35:0] s5_mxll;
reg signed [35:0] s5_mxlh;
reg signed [35:0] s5_mxhl;
reg signed [35:0] s5_mxhh;
reg signed [35:0] s5_myll;
reg signed [35:0] s5_mylh;
reg signed [35:0] s5_myhl;
reg signed [35:0] s5_myhh;
reg signed [35:0] s5_mxyll;
reg signed [35:0] s5_mxylh;
reg signed [35:0] s5_mxyhl;
reg signed [35:0] s5_mxyhh;
reg signed [31:0] s5_ux;
reg signed [31:0] s5_uy;
reg signed [0:0] s5_ok;
reg valid6;
reg signed [36:0] s6_mxcross;
reg signed [35:0] s6_mxll;
reg signed [35:0] s6_mxhh;
reg signed [36:0] s6_mycross;
reg signed [35:0] s6_myll;
reg signed [35:0] s6_myhh;
reg signed [36:0] s6_mxycross;
reg signed [35:0] s6_mxyll;
reg signed [35:0] s6_mxyhh;
reg signed [31:0] s6_ux;
reg signed [31:0] s6_uy;
reg signed [0:0] s6_ok;
reg valid7;
reg signed [43:0] s7_mx;
reg signed [43:0] s7_my;
reg signed [43:0] s7_mxy;
reg signed [31:0] s7_ux;
reg signed [31:0] s7_uy;
reg signed [0:0] s7_ok;
reg valid8;
reg signed [31:0] s8_r2;
reg signed [31:0] s8_qx;
reg signed [31:0] s8_qy;
reg signed [31:0] s8_qxy;
reg signed [31:0] s8_ux;
reg signed [31:0] s8_uy;
reg signed [0:0] s8_ok;
wire signed[31:0]lut_factor;wire lut_valid,lut_in_range;
reg signed[31:0]lut_factor_delay[0:5];reg[5:0]lut_ok_delay;reg[16:0]lut_modes;integer lut_j;
generate if(RADIAL_MODEL_LUT)begin:g_radial_lut
 radial_lut #(.ROM_FILE(RADIAL_LUT_FILE)) u_radial(.clk(clk),.rstn(rstn),.valid_i(valid8),.r2_q16(s8_r2),
  .valid_o(lut_valid),.in_range_o(lut_in_range),.factor_q16(lut_factor));
end else begin:g_legacy_radial
 assign lut_factor=0;assign lut_valid=0;assign lut_in_range=0;
end endgenerate
always @(posedge clk)begin
 if(!rstn)begin
  lut_modes<=0;lut_ok_delay<=0;for(lut_j=0;lut_j<6;lut_j=lut_j+1)lut_factor_delay[lut_j]<=0;
 end else begin
  lut_modes<={lut_modes[15:0],(RADIAL_MODEL_LUT && lut_enable)};
  lut_factor_delay[0]<=lut_factor;lut_ok_delay<={lut_ok_delay[4:0],(lut_valid && lut_in_range)};
  for(lut_j=1;lut_j<6;lut_j=lut_j+1)lut_factor_delay[lut_j]<=lut_factor_delay[lut_j-1];
 end
end
reg valid9;
reg signed [35:0] s9_mk1ll;
reg signed [35:0] s9_mk1lh;
reg signed [35:0] s9_mk1hl;
reg signed [35:0] s9_mk1hh;
reg signed [35:0] s9_mr4ll;
reg signed [35:0] s9_mr4lh;
reg signed [35:0] s9_mr4hl;
reg signed [35:0] s9_mr4hh;
reg signed [35:0] s9_mt1ll;
reg signed [35:0] s9_mt1lh;
reg signed [35:0] s9_mt1hl;
reg signed [35:0] s9_mt1hh;
reg signed [35:0] s9_mt2ll;
reg signed [35:0] s9_mt2lh;
reg signed [35:0] s9_mt2hl;
reg signed [35:0] s9_mt2hh;
reg signed [31:0] s9_sx;
reg signed [31:0] s9_sy;
reg signed [31:0] s9_ux;
reg signed [31:0] s9_uy;
reg signed [0:0] s9_ok;
reg valid10;
reg signed [36:0] s10_mk1cross;
reg signed [35:0] s10_mk1ll;
reg signed [35:0] s10_mk1hh;
reg signed [36:0] s10_mr4cross;
reg signed [35:0] s10_mr4ll;
reg signed [35:0] s10_mr4hh;
reg signed [36:0] s10_mt1cross;
reg signed [35:0] s10_mt1ll;
reg signed [35:0] s10_mt1hh;
reg signed [36:0] s10_mt2cross;
reg signed [35:0] s10_mt2ll;
reg signed [35:0] s10_mt2hh;
reg signed [31:0] s10_sx;
reg signed [31:0] s10_sy;
reg signed [31:0] s10_ux;
reg signed [31:0] s10_uy;
reg signed [0:0] s10_ok;
reg valid11;
reg signed [49:0] s11_mk1;
reg signed [51:0] s11_mr4;
reg signed [49:0] s11_mt1;
reg signed [49:0] s11_mt2;
reg signed [31:0] s11_sx;
reg signed [31:0] s11_sy;
reg signed [31:0] s11_ux;
reg signed [31:0] s11_uy;
reg signed [0:0] s11_ok;
reg valid12;
reg signed [31:0] s12_rad1;
reg signed [31:0] s12_r4;
reg signed [31:0] s12_t1;
reg signed [31:0] s12_t2;
reg signed [35:0] s12_mpxll;
reg signed [35:0] s12_mpxlh;
reg signed [35:0] s12_mpxhl;
reg signed [35:0] s12_mpxhh;
reg signed [35:0] s12_mpyll;
reg signed [35:0] s12_mpylh;
reg signed [35:0] s12_mpyhl;
reg signed [35:0] s12_mpyhh;
reg signed [31:0] s12_ux;
reg signed [31:0] s12_uy;
reg signed [0:0] s12_ok;
reg valid13;
reg signed [31:0] s13_rad1;
reg signed [31:0] s13_r4;
reg signed [31:0] s13_t1;
reg signed [31:0] s13_t2;
reg signed [36:0] s13_mpxcross;
reg signed [35:0] s13_mpxll;
reg signed [35:0] s13_mpxhh;
reg signed [36:0] s13_mpycross;
reg signed [35:0] s13_mpyll;
reg signed [35:0] s13_mpyhh;
reg signed [31:0] s13_ux;
reg signed [31:0] s13_uy;
reg signed [0:0] s13_ok;
reg valid14;
reg signed [31:0] s14_rad1;
reg signed [31:0] s14_r4;
reg signed [31:0] s14_t1;
reg signed [31:0] s14_t2;
reg signed [49:0] s14_mpx;
reg signed [49:0] s14_mpy;
reg signed [31:0] s14_ux;
reg signed [31:0] s14_uy;
reg signed [0:0] s14_ok;
reg valid15;
reg signed [35:0] s15_mk2ll;
reg signed [35:0] s15_mk2lh;
reg signed [35:0] s15_mk2hl;
reg signed [35:0] s15_mk2hh;
reg signed [31:0] s15_rad1;
reg signed [31:0] s15_tx;
reg signed [31:0] s15_ty;
reg signed [31:0] s15_ux;
reg signed [31:0] s15_uy;
reg signed [0:0] s15_ok;
reg valid16;
reg signed [36:0] s16_mk2cross;
reg signed [35:0] s16_mk2ll;
reg signed [35:0] s16_mk2hh;
reg signed [31:0] s16_rad1;
reg signed [31:0] s16_tx;
reg signed [31:0] s16_ty;
reg signed [31:0] s16_ux;
reg signed [31:0] s16_uy;
reg signed [0:0] s16_ok;
reg valid17;
reg signed [49:0] s17_mk2;
reg signed [31:0] s17_rad1;
reg signed [31:0] s17_tx;
reg signed [31:0] s17_ty;
reg signed [31:0] s17_ux;
reg signed [31:0] s17_uy;
reg signed [0:0] s17_ok;
reg valid18;
reg signed [31:0] s18_rad;
reg signed [31:0] s18_tx;
reg signed [31:0] s18_ty;
reg signed [31:0] s18_ux;
reg signed [31:0] s18_uy;
reg signed [0:0] s18_ok;
reg valid19;
reg signed [35:0] s19_mxll;
reg signed [35:0] s19_mxlh;
reg signed [35:0] s19_mxhl;
reg signed [35:0] s19_mxhh;
reg signed [35:0] s19_myll;
reg signed [35:0] s19_mylh;
reg signed [35:0] s19_myhl;
reg signed [35:0] s19_myhh;
reg signed [31:0] s19_tx;
reg signed [31:0] s19_ty;
reg signed [0:0] s19_ok;
reg valid20;
reg signed [36:0] s20_mxcross;
reg signed [35:0] s20_mxll;
reg signed [35:0] s20_mxhh;
reg signed [36:0] s20_mycross;
reg signed [35:0] s20_myll;
reg signed [35:0] s20_myhh;
reg signed [31:0] s20_tx;
reg signed [31:0] s20_ty;
reg signed [0:0] s20_ok;
reg valid21;
reg signed [53:0] s21_mx;
reg signed [53:0] s21_my;
reg signed [31:0] s21_tx;
reg signed [31:0] s21_ty;
reg signed [0:0] s21_ok;
reg valid22;
reg signed [31:0] s22_xd;
reg signed [31:0] s22_yd;
reg signed [0:0] s22_ok;
reg valid23;
reg signed [35:0] s23_mull;
reg signed [35:0] s23_mulh;
reg signed [35:0] s23_muhl;
reg signed [35:0] s23_muhh;
reg signed [35:0] s23_mvll;
reg signed [35:0] s23_mvlh;
reg signed [35:0] s23_mvhl;
reg signed [35:0] s23_mvhh;
reg signed [0:0] s23_ok;
reg valid24;
reg signed [36:0] s24_mucross;
reg signed [35:0] s24_mull;
reg signed [35:0] s24_muhh;
reg signed [36:0] s24_mvcross;
reg signed [35:0] s24_mvll;
reg signed [35:0] s24_mvhh;
reg signed [0:0] s24_ok;
reg valid25;
reg signed [63:0] s25_mu;
reg signed [63:0] s25_mv;
reg signed [0:0] s25_ok;
reg valid26;
reg signed [31:0] s26_u;
reg signed [31:0] s26_v;
reg signed [0:0] s26_ok;
wire signed [17:0] m1_ax_a=aa;
wire signed [16:0] m1_ax_b=xx;
wire signed [17:0] m1_ax_al=$signed({1'b0,m1_ax_a[16:0]}),m1_ax_ah=m1_ax_a>>>17;
wire signed [17:0] m1_ax_bl=$signed({1'b0,m1_ax_b[16:0]}),m1_ax_bh=m1_ax_b>>>17;
wire signed [17:0] m1_by_a=bb;
wire signed [16:0] m1_by_b=yy;
wire signed [17:0] m1_by_al=$signed({1'b0,m1_by_a[16:0]}),m1_by_ah=m1_by_a>>>17;
wire signed [17:0] m1_by_bl=$signed({1'b0,m1_by_b[16:0]}),m1_by_bh=m1_by_b>>>17;
wire signed [17:0] m1_dx_a=dd;
wire signed [16:0] m1_dx_b=xx;
wire signed [17:0] m1_dx_al=$signed({1'b0,m1_dx_a[16:0]}),m1_dx_ah=m1_dx_a>>>17;
wire signed [17:0] m1_dx_bl=$signed({1'b0,m1_dx_b[16:0]}),m1_dx_bh=m1_dx_b>>>17;
wire signed [17:0] m1_ey_a=ee;
wire signed [16:0] m1_ey_b=yy;
wire signed [17:0] m1_ey_al=$signed({1'b0,m1_ey_a[16:0]}),m1_ey_ah=m1_ey_a>>>17;
wire signed [17:0] m1_ey_bl=$signed({1'b0,m1_ey_b[16:0]}),m1_ey_bh=m1_ey_b>>>17;
wire signed [21:0] m3_mx_a=$signed(s4_ux[21:0]);
wire signed [21:0] m3_mx_b=$signed(s4_ux[21:0]);
wire signed [17:0] m3_mx_al=$signed({1'b0,m3_mx_a[16:0]}),m3_mx_ah=m3_mx_a>>>17;
wire signed [17:0] m3_mx_bl=$signed({1'b0,m3_mx_b[16:0]}),m3_mx_bh=m3_mx_b>>>17;
wire signed [21:0] m3_my_a=$signed(s4_uy[21:0]);
wire signed [21:0] m3_my_b=$signed(s4_uy[21:0]);
wire signed [17:0] m3_my_al=$signed({1'b0,m3_my_a[16:0]}),m3_my_ah=m3_my_a>>>17;
wire signed [17:0] m3_my_bl=$signed({1'b0,m3_my_b[16:0]}),m3_my_bh=m3_my_b>>>17;
wire signed [21:0] m3_mxy_a=$signed(s4_ux[21:0]);
wire signed [21:0] m3_mxy_b=$signed(s4_uy[21:0]);
wire signed [17:0] m3_mxy_al=$signed({1'b0,m3_mxy_a[16:0]}),m3_mxy_ah=m3_mxy_a>>>17;
wire signed [17:0] m3_mxy_bl=$signed({1'b0,m3_mxy_b[16:0]}),m3_mxy_bh=m3_mxy_b>>>17;
wire signed [17:0] m5_mk1_a=kk1;
wire signed [31:0] m5_mk1_b=s8_r2;
wire signed [17:0] m5_mk1_al=$signed({1'b0,m5_mk1_a[16:0]}),m5_mk1_ah=m5_mk1_a>>>17;
wire signed [17:0] m5_mk1_bl=$signed({1'b0,m5_mk1_b[16:0]}),m5_mk1_bh=m5_mk1_b>>>17;
wire signed [25:0] m5_mr4_a=$signed(s8_r2[25:0]);
wire signed [25:0] m5_mr4_b=$signed(s8_r2[25:0]);
wire signed [17:0] m5_mr4_al=$signed({1'b0,m5_mr4_a[16:0]}),m5_mr4_ah=m5_mr4_a>>>17;
wire signed [17:0] m5_mr4_bl=$signed({1'b0,m5_mr4_b[16:0]}),m5_mr4_bh=m5_mr4_b>>>17;
wire signed [17:0] m5_mt1_a=pp1;
wire signed [31:0] m5_mt1_b=s8_qxy;
wire signed [17:0] m5_mt1_al=$signed({1'b0,m5_mt1_a[16:0]}),m5_mt1_ah=m5_mt1_a>>>17;
wire signed [17:0] m5_mt1_bl=$signed({1'b0,m5_mt1_b[16:0]}),m5_mt1_bh=m5_mt1_b>>>17;
wire signed [17:0] m5_mt2_a=pp2;
wire signed [31:0] m5_mt2_b=s8_qxy;
wire signed [17:0] m5_mt2_al=$signed({1'b0,m5_mt2_a[16:0]}),m5_mt2_ah=m5_mt2_a>>>17;
wire signed [17:0] m5_mt2_bl=$signed({1'b0,m5_mt2_b[16:0]}),m5_mt2_bh=m5_mt2_b>>>17;
wire signed [17:0] m6_mpx_a=pp2;
wire signed [31:0] m6_mpx_b=s11_sx;
wire signed [17:0] m6_mpx_al=$signed({1'b0,m6_mpx_a[16:0]}),m6_mpx_ah=m6_mpx_a>>>17;
wire signed [17:0] m6_mpx_bl=$signed({1'b0,m6_mpx_b[16:0]}),m6_mpx_bh=m6_mpx_b>>>17;
wire signed [17:0] m6_mpy_a=pp1;
wire signed [31:0] m6_mpy_b=s11_sy;
wire signed [17:0] m6_mpy_al=$signed({1'b0,m6_mpy_a[16:0]}),m6_mpy_ah=m6_mpy_a>>>17;
wire signed [17:0] m6_mpy_bl=$signed({1'b0,m6_mpy_b[16:0]}),m6_mpy_bh=m6_mpy_b>>>17;
wire signed [17:0] m7_mk2_a=kk2;
wire signed [31:0] m7_mk2_b=s14_r4;
wire signed [17:0] m7_mk2_al=$signed({1'b0,m7_mk2_a[16:0]}),m7_mk2_ah=m7_mk2_a>>>17;
wire signed [17:0] m7_mk2_bl=$signed({1'b0,m7_mk2_b[16:0]}),m7_mk2_bh=m7_mk2_b>>>17;
wire signed [21:0] m9_mx_a=$signed(s18_ux[21:0]);
wire signed [31:0] m9_mx_b=s18_rad;
wire signed [17:0] m9_mx_al=$signed({1'b0,m9_mx_a[16:0]}),m9_mx_ah=m9_mx_a>>>17;
wire signed [17:0] m9_mx_bl=$signed({1'b0,m9_mx_b[16:0]}),m9_mx_bh=m9_mx_b>>>17;
wire signed [21:0] m9_my_a=$signed(s18_uy[21:0]);
wire signed [31:0] m9_my_b=s18_rad;
wire signed [17:0] m9_my_al=$signed({1'b0,m9_my_a[16:0]}),m9_my_ah=m9_my_a>>>17;
wire signed [17:0] m9_my_bl=$signed({1'b0,m9_my_b[16:0]}),m9_my_bh=m9_my_b>>>17;
wire signed [31:0] m11_mu_a=fx;
wire signed [31:0] m11_mu_b=s22_xd;
wire signed [17:0] m11_mu_al=$signed({1'b0,m11_mu_a[16:0]}),m11_mu_ah=m11_mu_a>>>17;
wire signed [17:0] m11_mu_bl=$signed({1'b0,m11_mu_b[16:0]}),m11_mu_bh=m11_mu_b>>>17;
wire signed [31:0] m11_mv_a=fy;
wire signed [31:0] m11_mv_b=s22_yd;
wire signed [17:0] m11_mv_al=$signed({1'b0,m11_mv_a[16:0]}),m11_mv_ah=m11_mv_a>>>17;
wire signed [17:0] m11_mv_bl=$signed({1'b0,m11_mv_b[16:0]}),m11_mv_bh=m11_mv_b>>>17;
wire signed [63:0] calc_u=((s25_mu+64'sd32768)>>>16)+cx;
wire signed [63:0] calc_v=((s25_mv+64'sd32768)>>>16)+cy;
// Sum both Q24 products before rounding, so cancellation and half-LSB cases
// do not receive two independent rounding errors. Widen before adding.
wire signed [35:0] affine_x_sum=$signed({s3_ax[34],s3_ax})+$signed({s3_by[34],s3_by});
wire signed [35:0] affine_y_sum=$signed({s3_dx[34],s3_dx})+$signed({s3_ey[34],s3_ey});
function signed [35:0] affine_to_q16(input signed [35:0] sum);
begin
 if(AFFINE_FRAC_BITS==24)affine_to_q16=(sum+36'sd128)>>>8;
 else affine_to_q16=sum;
end
endfunction
function signed [31:0] sat32(input signed [63:0] a);
begin if(a>64'sd2147483647)sat32=32'sh7fffffff;else if(a< -64'sd2147483648)sat32=32'sh80000000;else sat32=a[31:0];end
endfunction
always @(posedge clk)begin
 if(!rstn)begin
valid1<=0;s1_axll<=0;s1_axlh<=0;s1_axhl<=0;s1_axhh<=0;s1_byll<=0;s1_bylh<=0;s1_byhl<=0;s1_byhh<=0;s1_dxll<=0;s1_dxlh<=0;s1_dxhl<=0;s1_dxhh<=0;s1_eyll<=0;s1_eylh<=0;s1_eyhl<=0;s1_eyhh<=0;
 end else begin
valid1<=valid_i;
if(valid_i)begin
s1_axll<=m1_ax_al*m1_ax_bl;
s1_axlh<=m1_ax_al*m1_ax_bh;
s1_axhl<=m1_ax_ah*m1_ax_bl;
s1_axhh<=m1_ax_ah*m1_ax_bh;
s1_byll<=m1_by_al*m1_by_bl;
s1_bylh<=m1_by_al*m1_by_bh;
s1_byhl<=m1_by_ah*m1_by_bl;
s1_byhh<=m1_by_ah*m1_by_bh;
s1_dxll<=m1_dx_al*m1_dx_bl;
s1_dxlh<=m1_dx_al*m1_dx_bh;
s1_dxhl<=m1_dx_ah*m1_dx_bl;
s1_dxhh<=m1_dx_ah*m1_dx_bh;
s1_eyll<=m1_ey_al*m1_ey_bl;
s1_eylh<=m1_ey_al*m1_ey_bh;
s1_eyhl<=m1_ey_ah*m1_ey_bl;
s1_eyhh<=m1_ey_ah*m1_ey_bh;
end
 end
end
always @(posedge clk)begin
 if(!rstn)begin
valid2<=0;s2_axcross<=0;s2_axll<=0;s2_axhh<=0;s2_bycross<=0;s2_byll<=0;s2_byhh<=0;s2_dxcross<=0;s2_dxll<=0;s2_dxhh<=0;s2_eycross<=0;s2_eyll<=0;s2_eyhh<=0;
 end else begin
valid2<=valid1;
if(valid1)begin
s2_axcross<=s1_axlh+s1_axhl;
s2_axll<=s1_axll;
s2_axhh<=s1_axhh;
s2_bycross<=s1_bylh+s1_byhl;
s2_byll<=s1_byll;
s2_byhh<=s1_byhh;
s2_dxcross<=s1_dxlh+s1_dxhl;
s2_dxll<=s1_dxll;
s2_dxhh<=s1_dxhh;
s2_eycross<=s1_eylh+s1_eyhl;
s2_eyll<=s1_eyll;
s2_eyhh<=s1_eyhh;
end
 end
end
always @(posedge clk)begin
 if(!rstn)begin
valid3<=0;s3_ax<=0;s3_by<=0;s3_dx<=0;s3_ey<=0;
 end else begin
valid3<=valid2;
if(valid2)begin
s3_ax<=$signed({{28{s2_axll[35]}},s2_axll})+($signed({{27{s2_axcross[36]}},s2_axcross})<<<17)+($signed({{28{s2_axhh[35]}},s2_axhh})<<<34);
s3_by<=$signed({{28{s2_byll[35]}},s2_byll})+($signed({{27{s2_bycross[36]}},s2_bycross})<<<17)+($signed({{28{s2_byhh[35]}},s2_byhh})<<<34);
s3_dx<=$signed({{28{s2_dxll[35]}},s2_dxll})+($signed({{27{s2_dxcross[36]}},s2_dxcross})<<<17)+($signed({{28{s2_dxhh[35]}},s2_dxhh})<<<34);
s3_ey<=$signed({{28{s2_eyll[35]}},s2_eyll})+($signed({{27{s2_eycross[36]}},s2_eycross})<<<17)+($signed({{28{s2_eyhh[35]}},s2_eyhh})<<<34);
end
 end
end
always @(posedge clk)begin
 if(!rstn)begin
valid4<=0;s4_ux<=0;s4_uy<=0;
 end else begin
valid4<=valid3;
if(valid3)begin
s4_ux<=affine_to_q16(affine_x_sum)+C;
s4_uy<=affine_to_q16(affine_y_sum)+F;
end
 end
end
always @(posedge clk)begin
 if(!rstn)begin
valid5<=0;s5_mxll<=0;s5_mxlh<=0;s5_mxhl<=0;s5_mxhh<=0;s5_myll<=0;s5_mylh<=0;s5_myhl<=0;s5_myhh<=0;s5_mxyll<=0;s5_mxylh<=0;s5_mxyhl<=0;s5_mxyhh<=0;s5_ux<=0;s5_uy<=0;s5_ok<=0;
 end else begin
valid5<=valid4;
if(valid4)begin
s5_mxll<=m3_mx_al*m3_mx_bl;
s5_mxlh<=m3_mx_al*m3_mx_bh;
s5_mxhl<=m3_mx_ah*m3_mx_bl;
s5_mxhh<=m3_mx_ah*m3_mx_bh;
s5_myll<=m3_my_al*m3_my_bl;
s5_mylh<=m3_my_al*m3_my_bh;
s5_myhl<=m3_my_ah*m3_my_bl;
s5_myhh<=m3_my_ah*m3_my_bh;
s5_mxyll<=m3_mxy_al*m3_mxy_bl;
s5_mxylh<=m3_mxy_al*m3_mxy_bh;
s5_mxyhl<=m3_mxy_ah*m3_mxy_bl;
s5_mxyhh<=m3_mxy_ah*m3_mxy_bh;
s5_ux<=s4_ux;
s5_uy<=s4_uy;
s5_ok<=(s4_ux>=-32'sd262144 && s4_ux<=32'sd262144 && s4_uy>=-32'sd262144 && s4_uy<=32'sd262144);
end
 end
end
always @(posedge clk)begin
 if(!rstn)begin
valid6<=0;s6_mxcross<=0;s6_mxll<=0;s6_mxhh<=0;s6_mycross<=0;s6_myll<=0;s6_myhh<=0;s6_mxycross<=0;s6_mxyll<=0;s6_mxyhh<=0;s6_ux<=0;s6_uy<=0;s6_ok<=0;
 end else begin
valid6<=valid5;
if(valid5)begin
s6_mxcross<=s5_mxlh+s5_mxhl;
s6_mxll<=s5_mxll;
s6_mxhh<=s5_mxhh;
s6_mycross<=s5_mylh+s5_myhl;
s6_myll<=s5_myll;
s6_myhh<=s5_myhh;
s6_mxycross<=s5_mxylh+s5_mxyhl;
s6_mxyll<=s5_mxyll;
s6_mxyhh<=s5_mxyhh;
s6_ux<=s5_ux;
s6_uy<=s5_uy;
s6_ok<=s5_ok;
end
 end
end
always @(posedge clk)begin
 if(!rstn)begin
valid7<=0;s7_mx<=0;s7_my<=0;s7_mxy<=0;s7_ux<=0;s7_uy<=0;s7_ok<=0;
 end else begin
valid7<=valid6;
if(valid6)begin
s7_mx<=$signed({{28{s6_mxll[35]}},s6_mxll})+($signed({{27{s6_mxcross[36]}},s6_mxcross})<<<17)+($signed({{28{s6_mxhh[35]}},s6_mxhh})<<<34);
s7_my<=$signed({{28{s6_myll[35]}},s6_myll})+($signed({{27{s6_mycross[36]}},s6_mycross})<<<17)+($signed({{28{s6_myhh[35]}},s6_myhh})<<<34);
s7_mxy<=$signed({{28{s6_mxyll[35]}},s6_mxyll})+($signed({{27{s6_mxycross[36]}},s6_mxycross})<<<17)+($signed({{28{s6_mxyhh[35]}},s6_mxyhh})<<<34);
s7_ux<=s6_ux;
s7_uy<=s6_uy;
s7_ok<=s6_ok;
end
 end
end
always @(posedge clk)begin
 if(!rstn)begin
valid8<=0;s8_r2<=0;s8_qx<=0;s8_qy<=0;s8_qxy<=0;s8_ux<=0;s8_uy<=0;s8_ok<=0;
 end else begin
valid8<=valid7;
if(valid7)begin
s8_r2<=(s7_mx+s7_my+45'sd32768)>>>16;
s8_qx<=(s7_mx+45'sd32768)>>>16;
s8_qy<=(s7_my+45'sd32768)>>>16;
s8_qxy<=(s7_mxy+45'sd32768)>>>16;
s8_ux<=s7_ux;
s8_uy<=s7_uy;
s8_ok<=s7_ok;
end
 end
end
always @(posedge clk)begin
 if(!rstn)begin
valid9<=0;s9_mk1ll<=0;s9_mk1lh<=0;s9_mk1hl<=0;s9_mk1hh<=0;s9_mr4ll<=0;s9_mr4lh<=0;s9_mr4hl<=0;s9_mr4hh<=0;s9_mt1ll<=0;s9_mt1lh<=0;s9_mt1hl<=0;s9_mt1hh<=0;s9_mt2ll<=0;s9_mt2lh<=0;s9_mt2hl<=0;s9_mt2hh<=0;s9_sx<=0;s9_sy<=0;s9_ux<=0;s9_uy<=0;s9_ok<=0;
 end else begin
valid9<=valid8;
if(valid8)begin
s9_mk1ll<=m5_mk1_al*m5_mk1_bl;
s9_mk1lh<=m5_mk1_al*m5_mk1_bh;
s9_mk1hl<=m5_mk1_ah*m5_mk1_bl;
s9_mk1hh<=m5_mk1_ah*m5_mk1_bh;
s9_mr4ll<=m5_mr4_al*m5_mr4_bl;
s9_mr4lh<=m5_mr4_al*m5_mr4_bh;
s9_mr4hl<=m5_mr4_ah*m5_mr4_bl;
s9_mr4hh<=m5_mr4_ah*m5_mr4_bh;
s9_mt1ll<=m5_mt1_al*m5_mt1_bl;
s9_mt1lh<=m5_mt1_al*m5_mt1_bh;
s9_mt1hl<=m5_mt1_ah*m5_mt1_bl;
s9_mt1hh<=m5_mt1_ah*m5_mt1_bh;
s9_mt2ll<=m5_mt2_al*m5_mt2_bl;
s9_mt2lh<=m5_mt2_al*m5_mt2_bh;
s9_mt2hl<=m5_mt2_ah*m5_mt2_bl;
s9_mt2hh<=m5_mt2_ah*m5_mt2_bh;
s9_sx<=s8_r2+(s8_qx<<<1);
s9_sy<=s8_r2+(s8_qy<<<1);
s9_ux<=s8_ux;
s9_uy<=s8_uy;
s9_ok<=s8_ok;
end
 end
end
always @(posedge clk)begin
 if(!rstn)begin
valid10<=0;s10_mk1cross<=0;s10_mk1ll<=0;s10_mk1hh<=0;s10_mr4cross<=0;s10_mr4ll<=0;s10_mr4hh<=0;s10_mt1cross<=0;s10_mt1ll<=0;s10_mt1hh<=0;s10_mt2cross<=0;s10_mt2ll<=0;s10_mt2hh<=0;s10_sx<=0;s10_sy<=0;s10_ux<=0;s10_uy<=0;s10_ok<=0;
 end else begin
valid10<=valid9;
if(valid9)begin
s10_mk1cross<=s9_mk1lh+s9_mk1hl;
s10_mk1ll<=s9_mk1ll;
s10_mk1hh<=s9_mk1hh;
s10_mr4cross<=s9_mr4lh+s9_mr4hl;
s10_mr4ll<=s9_mr4ll;
s10_mr4hh<=s9_mr4hh;
s10_mt1cross<=s9_mt1lh+s9_mt1hl;
s10_mt1ll<=s9_mt1ll;
s10_mt1hh<=s9_mt1hh;
s10_mt2cross<=s9_mt2lh+s9_mt2hl;
s10_mt2ll<=s9_mt2ll;
s10_mt2hh<=s9_mt2hh;
s10_sx<=s9_sx;
s10_sy<=s9_sy;
s10_ux<=s9_ux;
s10_uy<=s9_uy;
s10_ok<=s9_ok;
end
 end
end
always @(posedge clk)begin
 if(!rstn)begin
valid11<=0;s11_mk1<=0;s11_mr4<=0;s11_mt1<=0;s11_mt2<=0;s11_sx<=0;s11_sy<=0;s11_ux<=0;s11_uy<=0;s11_ok<=0;
 end else begin
valid11<=valid10;
if(valid10)begin
s11_mk1<=$signed({{28{s10_mk1ll[35]}},s10_mk1ll})+($signed({{27{s10_mk1cross[36]}},s10_mk1cross})<<<17)+($signed({{28{s10_mk1hh[35]}},s10_mk1hh})<<<34);
s11_mr4<=$signed({{28{s10_mr4ll[35]}},s10_mr4ll})+($signed({{27{s10_mr4cross[36]}},s10_mr4cross})<<<17)+($signed({{28{s10_mr4hh[35]}},s10_mr4hh})<<<34);
s11_mt1<=$signed({{28{s10_mt1ll[35]}},s10_mt1ll})+($signed({{27{s10_mt1cross[36]}},s10_mt1cross})<<<17)+($signed({{28{s10_mt1hh[35]}},s10_mt1hh})<<<34);
s11_mt2<=$signed({{28{s10_mt2ll[35]}},s10_mt2ll})+($signed({{27{s10_mt2cross[36]}},s10_mt2cross})<<<17)+($signed({{28{s10_mt2hh[35]}},s10_mt2hh})<<<34);
s11_sx<=s10_sx;
s11_sy<=s10_sy;
s11_ux<=s10_ux;
s11_uy<=s10_uy;
s11_ok<=s10_ok;
end
 end
end
always @(posedge clk)begin
 if(!rstn)begin
valid12<=0;s12_rad1<=0;s12_r4<=0;s12_t1<=0;s12_t2<=0;s12_mpxll<=0;s12_mpxlh<=0;s12_mpxhl<=0;s12_mpxhh<=0;s12_mpyll<=0;s12_mpylh<=0;s12_mpyhl<=0;s12_mpyhh<=0;s12_ux<=0;s12_uy<=0;s12_ok<=0;
 end else begin
valid12<=valid11;
if(valid11)begin
s12_rad1<=32'sd65536+((s11_mk1+50'sd32768)>>>16);
s12_r4<=(s11_mr4+52'sd32768)>>>16;
s12_t1<=(s11_mt1+50'sd32768)>>>16;
s12_t2<=(s11_mt2+50'sd32768)>>>16;
s12_mpxll<=m6_mpx_al*m6_mpx_bl;
s12_mpxlh<=m6_mpx_al*m6_mpx_bh;
s12_mpxhl<=m6_mpx_ah*m6_mpx_bl;
s12_mpxhh<=m6_mpx_ah*m6_mpx_bh;
s12_mpyll<=m6_mpy_al*m6_mpy_bl;
s12_mpylh<=m6_mpy_al*m6_mpy_bh;
s12_mpyhl<=m6_mpy_ah*m6_mpy_bl;
s12_mpyhh<=m6_mpy_ah*m6_mpy_bh;
s12_ux<=s11_ux;
s12_uy<=s11_uy;
s12_ok<=s11_ok;
end
 end
end
always @(posedge clk)begin
 if(!rstn)begin
valid13<=0;s13_rad1<=0;s13_r4<=0;s13_t1<=0;s13_t2<=0;s13_mpxcross<=0;s13_mpxll<=0;s13_mpxhh<=0;s13_mpycross<=0;s13_mpyll<=0;s13_mpyhh<=0;s13_ux<=0;s13_uy<=0;s13_ok<=0;
 end else begin
valid13<=valid12;
if(valid12)begin
s13_rad1<=s12_rad1;
s13_r4<=s12_r4;
s13_t1<=s12_t1;
s13_t2<=s12_t2;
s13_mpxcross<=s12_mpxlh+s12_mpxhl;
s13_mpxll<=s12_mpxll;
s13_mpxhh<=s12_mpxhh;
s13_mpycross<=s12_mpylh+s12_mpyhl;
s13_mpyll<=s12_mpyll;
s13_mpyhh<=s12_mpyhh;
s13_ux<=s12_ux;
s13_uy<=s12_uy;
s13_ok<=s12_ok;
end
 end
end
always @(posedge clk)begin
 if(!rstn)begin
valid14<=0;s14_rad1<=0;s14_r4<=0;s14_t1<=0;s14_t2<=0;s14_mpx<=0;s14_mpy<=0;s14_ux<=0;s14_uy<=0;s14_ok<=0;
 end else begin
valid14<=valid13;
if(valid13)begin
s14_rad1<=s13_rad1;
s14_r4<=s13_r4;
s14_t1<=s13_t1;
s14_t2<=s13_t2;
s14_mpx<=$signed({{28{s13_mpxll[35]}},s13_mpxll})+($signed({{27{s13_mpxcross[36]}},s13_mpxcross})<<<17)+($signed({{28{s13_mpxhh[35]}},s13_mpxhh})<<<34);
s14_mpy<=$signed({{28{s13_mpyll[35]}},s13_mpyll})+($signed({{27{s13_mpycross[36]}},s13_mpycross})<<<17)+($signed({{28{s13_mpyhh[35]}},s13_mpyhh})<<<34);
s14_ux<=s13_ux;
s14_uy<=s13_uy;
s14_ok<=s13_ok;
end
 end
end
always @(posedge clk)begin
 if(!rstn)begin
valid15<=0;s15_mk2ll<=0;s15_mk2lh<=0;s15_mk2hl<=0;s15_mk2hh<=0;s15_rad1<=0;s15_tx<=0;s15_ty<=0;s15_ux<=0;s15_uy<=0;s15_ok<=0;
 end else begin
valid15<=valid14;
if(valid14)begin
s15_mk2ll<=m7_mk2_al*m7_mk2_bl;
s15_mk2lh<=m7_mk2_al*m7_mk2_bh;
s15_mk2hl<=m7_mk2_ah*m7_mk2_bl;
s15_mk2hh<=m7_mk2_ah*m7_mk2_bh;
s15_rad1<=s14_rad1;
s15_tx<=(s14_t1<<<1)+((s14_mpx+50'sd32768)>>>16);
s15_ty<=(s14_t2<<<1)+((s14_mpy+50'sd32768)>>>16);
s15_ux<=s14_ux;
s15_uy<=s14_uy;
s15_ok<=s14_ok;
end
 end
end
always @(posedge clk)begin
 if(!rstn)begin
valid16<=0;s16_mk2cross<=0;s16_mk2ll<=0;s16_mk2hh<=0;s16_rad1<=0;s16_tx<=0;s16_ty<=0;s16_ux<=0;s16_uy<=0;s16_ok<=0;
 end else begin
valid16<=valid15;
if(valid15)begin
s16_mk2cross<=s15_mk2lh+s15_mk2hl;
s16_mk2ll<=s15_mk2ll;
s16_mk2hh<=s15_mk2hh;
s16_rad1<=s15_rad1;
s16_tx<=s15_tx;
s16_ty<=s15_ty;
s16_ux<=s15_ux;
s16_uy<=s15_uy;
s16_ok<=s15_ok;
end
 end
end
always @(posedge clk)begin
 if(!rstn)begin
valid17<=0;s17_mk2<=0;s17_rad1<=0;s17_tx<=0;s17_ty<=0;s17_ux<=0;s17_uy<=0;s17_ok<=0;
 end else begin
valid17<=valid16;
if(valid16)begin
s17_mk2<=$signed({{28{s16_mk2ll[35]}},s16_mk2ll})+($signed({{27{s16_mk2cross[36]}},s16_mk2cross})<<<17)+($signed({{28{s16_mk2hh[35]}},s16_mk2hh})<<<34);
s17_rad1<=s16_rad1;
s17_tx<=s16_tx;
s17_ty<=s16_ty;
s17_ux<=s16_ux;
s17_uy<=s16_uy;
s17_ok<=s16_ok;
end
 end
end
always @(posedge clk)begin
 if(!rstn)begin
valid18<=0;s18_rad<=0;s18_tx<=0;s18_ty<=0;s18_ux<=0;s18_uy<=0;s18_ok<=0;
 end else begin
valid18<=valid17;
if(valid17)begin
s18_rad<=lut_modes[16]?lut_factor_delay[5]:(s17_rad1+((s17_mk2+50'sd32768)>>>16));
s18_tx<=s17_tx;
s18_ty<=s17_ty;
s18_ux<=s17_ux;
s18_uy<=s17_uy;
s18_ok<=s17_ok && (!lut_modes[16] || lut_ok_delay[5]);
end
 end
end
always @(posedge clk)begin
 if(!rstn)begin
valid19<=0;s19_mxll<=0;s19_mxlh<=0;s19_mxhl<=0;s19_mxhh<=0;s19_myll<=0;s19_mylh<=0;s19_myhl<=0;s19_myhh<=0;s19_tx<=0;s19_ty<=0;s19_ok<=0;
 end else begin
valid19<=valid18;
if(valid18)begin
s19_mxll<=m9_mx_al*m9_mx_bl;
s19_mxlh<=m9_mx_al*m9_mx_bh;
s19_mxhl<=m9_mx_ah*m9_mx_bl;
s19_mxhh<=m9_mx_ah*m9_mx_bh;
s19_myll<=m9_my_al*m9_my_bl;
s19_mylh<=m9_my_al*m9_my_bh;
s19_myhl<=m9_my_ah*m9_my_bl;
s19_myhh<=m9_my_ah*m9_my_bh;
s19_tx<=s18_tx;
s19_ty<=s18_ty;
s19_ok<=s18_ok;
end
 end
end
always @(posedge clk)begin
 if(!rstn)begin
valid20<=0;s20_mxcross<=0;s20_mxll<=0;s20_mxhh<=0;s20_mycross<=0;s20_myll<=0;s20_myhh<=0;s20_tx<=0;s20_ty<=0;s20_ok<=0;
 end else begin
valid20<=valid19;
if(valid19)begin
s20_mxcross<=s19_mxlh+s19_mxhl;
s20_mxll<=s19_mxll;
s20_mxhh<=s19_mxhh;
s20_mycross<=s19_mylh+s19_myhl;
s20_myll<=s19_myll;
s20_myhh<=s19_myhh;
s20_tx<=s19_tx;
s20_ty<=s19_ty;
s20_ok<=s19_ok;
end
 end
end
always @(posedge clk)begin
 if(!rstn)begin
valid21<=0;s21_mx<=0;s21_my<=0;s21_tx<=0;s21_ty<=0;s21_ok<=0;
 end else begin
valid21<=valid20;
if(valid20)begin
s21_mx<=$signed({{28{s20_mxll[35]}},s20_mxll})+($signed({{27{s20_mxcross[36]}},s20_mxcross})<<<17)+($signed({{28{s20_mxhh[35]}},s20_mxhh})<<<34);
s21_my<=$signed({{28{s20_myll[35]}},s20_myll})+($signed({{27{s20_mycross[36]}},s20_mycross})<<<17)+($signed({{28{s20_myhh[35]}},s20_myhh})<<<34);
s21_tx<=s20_tx;
s21_ty<=s20_ty;
s21_ok<=s20_ok;
end
 end
end
always @(posedge clk)begin
 if(!rstn)begin
valid22<=0;s22_xd<=0;s22_yd<=0;s22_ok<=0;
 end else begin
valid22<=valid21;
if(valid21)begin
s22_xd<=((s21_mx+54'sd32768)>>>16)+s21_tx;
s22_yd<=((s21_my+54'sd32768)>>>16)+s21_ty;
s22_ok<=s21_ok;
end
 end
end
always @(posedge clk)begin
 if(!rstn)begin
valid23<=0;s23_mull<=0;s23_mulh<=0;s23_muhl<=0;s23_muhh<=0;s23_mvll<=0;s23_mvlh<=0;s23_mvhl<=0;s23_mvhh<=0;s23_ok<=0;
 end else begin
valid23<=valid22;
if(valid22)begin
s23_mull<=m11_mu_al*m11_mu_bl;
s23_mulh<=m11_mu_al*m11_mu_bh;
s23_muhl<=m11_mu_ah*m11_mu_bl;
s23_muhh<=m11_mu_ah*m11_mu_bh;
s23_mvll<=m11_mv_al*m11_mv_bl;
s23_mvlh<=m11_mv_al*m11_mv_bh;
s23_mvhl<=m11_mv_ah*m11_mv_bl;
s23_mvhh<=m11_mv_ah*m11_mv_bh;
s23_ok<=s22_ok;
end
 end
end
always @(posedge clk)begin
 if(!rstn)begin
valid24<=0;s24_mucross<=0;s24_mull<=0;s24_muhh<=0;s24_mvcross<=0;s24_mvll<=0;s24_mvhh<=0;s24_ok<=0;
 end else begin
valid24<=valid23;
if(valid23)begin
s24_mucross<=s23_mulh+s23_muhl;
s24_mull<=s23_mull;
s24_muhh<=s23_muhh;
s24_mvcross<=s23_mvlh+s23_mvhl;
s24_mvll<=s23_mvll;
s24_mvhh<=s23_mvhh;
s24_ok<=s23_ok;
end
 end
end
always @(posedge clk)begin
 if(!rstn)begin
valid25<=0;s25_mu<=0;s25_mv<=0;s25_ok<=0;
 end else begin
valid25<=valid24;
if(valid24)begin
s25_mu<=$signed({{28{s24_mull[35]}},s24_mull})+($signed({{27{s24_mucross[36]}},s24_mucross})<<<17)+($signed({{28{s24_muhh[35]}},s24_muhh})<<<34);
s25_mv<=$signed({{28{s24_mvll[35]}},s24_mvll})+($signed({{27{s24_mvcross[36]}},s24_mvcross})<<<17)+($signed({{28{s24_mvhh[35]}},s24_mvhh})<<<34);
s25_ok<=s24_ok;
end
 end
end
always @(posedge clk)begin
 if(!rstn)begin
valid26<=0;s26_u<=0;s26_v<=0;s26_ok<=0;
 end else begin
valid26<=valid25;
if(valid25)begin
s26_u<=sat32(calc_u);
s26_v<=sat32(calc_v);
s26_ok<=s25_ok;
end
 end
end
always @(posedge clk)begin
 if(!rstn)begin valid_o<=0;u_q16<=0;v_q16<=0;u_int<=0;v_int<=0;u_frac<=0;v_frac<=0;in_frame<=0;end
 else begin
 valid_o<=valid26;u_q16<=s26_u;v_q16<=s26_v;
 u_int<=s26_u[31:16];v_int<=s26_v[31:16];u_frac<=s26_u[15:8];v_frac<=s26_v[15:8];
 in_frame<=s26_ok && s26_u>=0 && s26_u<=((W-1)<<16) && s26_v>=0 && s26_v<=((H-1)<<16);
 end
end
endmodule
`default_nettype wire
