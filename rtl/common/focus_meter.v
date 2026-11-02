`timescale 1ns/1ps
`default_nettype none
// Passive source-image measurement. No pixel, DE or VS is modified.
// Central-half ROI squared horizontal/vertical luminance-gradient energy.
// Relative focusing aid only: noise, lighting and target content also affect it.
module focus_meter #(
 parameter integer WIDTH=1280,HEIGHT=720,SCORE_SHIFT=22
)(input wire clk,rstn,vs,de,input wire [15:0] pixel,
 output reg [15:0] score_bcd,output reg score_toggle);
 localparam integer X0=WIDTH/4,X1=WIDTH*3/4,Y0=HEIGHT/4,Y1=HEIGHT*3/4;
 reg [7:0] line_memory[0:WIDTH-1];
 reg [11:0] x,y;
 reg vs_d,armed;
 wire marker=vs&&!vs_d;
 wire accept=armed&&de&&!marker;
 wire [7:0] r={pixel[15:11],pixel[15:13]};
 wire [7:0] g={pixel[10:5],pixel[10:9]};
 wire [7:0] b={pixel[4:0],pixel[4:2]};
 wire [9:0] luma_sum={2'b0,r}+{1'b0,g,1'b0}+{2'b0,b};
 wire [7:0] luma=luma_sum[9:2];
 reg [7:0] previous,above_d,left_d,luma_d;
 reg v0,roi0,first0,last0,v1,roi1,first1,last1;
 reg v_diff,roi_diff,first_diff,last_diff,v_sq,roi_sq,first_sq,last_sq;
 reg [7:0] dx,dy;
 reg [15:0] square_x,square_y;
 wire [15:0] sx=dx*dx,sy=dy*dy;
 reg [16:0] energy;
 reg [35:0] total;
 wire [35:0] scaled=total>>SCORE_SHIFT;
 reg [15:0] shift_bin,shift_bcd,adjusted;
 reg [4:0] bits_left;integer i;
 always @*begin
  adjusted=shift_bcd;
  for(i=0;i<4;i=i+1)
   if(shift_bcd[i*4+:4]>=5)adjusted[i*4+:4]=shift_bcd[i*4+:4]+4'd3;
 end
 // Registered old-data read and write infer one dual-port line RAM.
 // The first row is excluded from the ROI, so RAM initialization is unnecessary.
 always @(posedge clk)if(accept)begin
  above_d<=line_memory[x];line_memory[x]<=luma;
 end
 always @(posedge clk)begin
  if(!rstn)begin
   x<=0;y<=0;vs_d<=0;armed<=0;previous<=0;left_d<=0;luma_d<=0;
   v0<=0;roi0<=0;first0<=0;last0<=0;v1<=0;roi1<=0;first1<=0;last1<=0;
   v_diff<=0;roi_diff<=0;first_diff<=0;last_diff<=0;
   v_sq<=0;roi_sq<=0;first_sq<=0;last_sq<=0;
   dx<=0;dy<=0;square_x<=0;square_y<=0;
   energy<=0;total<=0;shift_bin<=0;shift_bcd<=0;bits_left<=0;
   score_bcd<=0;score_toggle<=0;
  end else begin
   vs_d<=vs;v0<=accept;v_diff<=v0;v_sq<=v_diff;v1<=v_sq;
   if(marker)begin x<=0;y<=0;armed<=1;end
   else if(accept)begin
    if(x==WIDTH-1)begin
     x<=0;
     if(y==HEIGHT-1)armed<=0;else y<=y+1'b1;
    end else x<=x+1'b1;
   end
   if(accept)begin
    luma_d<=luma;left_d<=previous;previous<=luma;
    roi0<=x>=X0&&x<X1&&y>=Y0&&y<Y1;
    first0<=x==X0&&y==Y0;last0<=x==WIDTH-1&&y==HEIGHT-1;
   end
   if(v0)begin
    dx<=(luma_d>=left_d)?luma_d-left_d:left_d-luma_d;
    dy<=(luma_d>=above_d)?luma_d-above_d:above_d-luma_d;
    roi_diff<=roi0;first_diff<=first0;last_diff<=last0;
   end
   if(v_diff)begin
    square_x<=sx;square_y<=sy;
    roi_sq<=roi_diff;first_sq<=first_diff;last_sq<=last_diff;
   end
   if(v_sq)begin
    energy<={1'b0,square_x}+{1'b0,square_y};roi1<=roi_sq;first1<=first_sq;last1<=last_sq;
   end
   // Reset at the first ROI sample, not VS. This preserves an old frame's
   // in-flight final sample if the next marker immediately follows its pixels.
   if(v1&&roi1)total<=first1?{19'd0,energy}:total+energy;
   if(v1&&last1)begin
    shift_bin<=(scaled>9999)?16'd9999:scaled[15:0];shift_bcd<=0;bits_left<=16;
   end else if(bits_left!=0)begin
    shift_bcd<={adjusted[14:0],shift_bin[15]};shift_bin<={shift_bin[14:0],1'b0};bits_left<=bits_left-1'b1;
    if(bits_left==1)begin score_bcd<={adjusted[14:0],shift_bin[15]};score_toggle<=!score_toggle;end
   end
  end
 end
endmodule
`default_nettype wire
