`timescale 1ns/1ps
module tb_quality_720p;
 reg clk=0,rstn=0,vs=0,hs=0,de=0,cycle_n=1,overlay=0;
 reg [15:0] pixel=0,osd_pixel=0;always #5 clk=~clk;
 wire vo,ho,deo;wire[23:0] rgb;wire[1:0] mode;
 quality_display dut(.clk(clk),.rstn(rstn),.vs(vs),.hs(hs),.de(de),.cycle_n(cycle_n),
  .pixel(pixel),.osd_pixel(osd_pixel),.osd_overlay(overlay),
  .vs_o(vo),.hs_o(ho),.de_o(deo),.rgb_o(rgb),.active_mode(mode));
 integer pv=0,ph=0,pd=0,ld=0,pov=0,pr=0,pg=0,pb=0,py=0,ly=0;
 integer nr,ng,nb,ny,dr,dg,db,delta,em=1,x,y,phase,count=0,total=0;
 integer ix,iy;reg[15:0] ip,op;reg[23:0] expected;
 function integer clip(input integer value);begin clip=(value<0)?0:(value>255)?255:value;end endfunction
 task send;
  input integer iv,ih,id,ic;input[15:0] value,osd;input integer ov;
  begin
   @(negedge clk);vs=iv;hs=ih;de=id;cycle_n=ic;pixel=value;osd_pixel=osd;overlay=ov;
   nr=value[15:11]*8+value[15:13];ng=value[10:5]*4+value[10:9];nb=value[4:0]*8+value[4:2];
   ny=(nr+2*ng+nb)/4;delta=0;
   if(em==2 && pd && ld && id && !pov)begin
    delta=(2*py-ly-ny);
    // Floor division by eight, independently of RTL arithmetic shifts.
    delta=(delta>=0)?delta/8:-((-delta+7)/8);
    if(delta>8)delta=8;if(delta< -8)delta=-8;
   end
   dr=clip(pr+delta);dg=clip(pg+delta);db=clip(pb+delta);
   if(!pd)expected=0;
   else if(em==0)expected={(pr[7:3]),3'b0,(pg[7:2]),2'b0,(pb[7:3]),3'b0};
   else expected={dr[7:0],dg[7:0],db[7:0]};
   @(posedge clk);#1;
   if(vo!==pv[0] || ho!==ph[0] || deo!==pd[0] || rgb!==expected)
    $fatal(1,"720P QUALITY MISMATCH Q%0d x=%0d y=%0d rgb=%h expect=%h sync=%b%b%b",em,x,y,rgb,expected,vo,ho,deo);
   if(pd)begin count=count+1;total=total+1;end
   ly=py;ld=pd;py=ny;
   if(ov)begin pr=osd[15:11]*8+osd[15:13];pg=osd[10:5]*4+osd[10:9];pb=osd[4:0]*8+osd[4:2];end
   else begin pr=nr;pg=ng;pb=nb;end
   pv=iv;ph=ih;pd=id;pov=ov;
  end
 endtask
 initial begin
  repeat(3)@(negedge clk);rstn=1;
  for(phase=0;phase<3;phase=phase+1)begin
   if(phase!=0)begin send(0,0,0,0,0,0,0);send(0,0,0,0,0,0,0);send(0,0,0,1,0,0,0);end
   send(1,0,0,1,0,0,0);em=(phase==0)?1:(phase==1)?2:0;
   if(mode!==em[1:0])$fatal(1,"720P MODE");
   send(0,0,0,1,0,0,0);count=0;
   for(y=0;y<750;y=y+1)begin
    for(x=0;x<1650;x=x+1)begin
     ix=(x/8+y)%32;iy=(x/3+2*y)%64;
     ip={ix[4:0],iy[5:0],x[4:0]};op=(x[3]^y[3])?16'hffff:0;
     send(y>=725 && y<730,x>=1390 && x<1430,x<1280 && y<720,1,ip,op,
       x>=16 && x<208 && y>=16 && y<176);
    end
   end
   send(0,0,0,1,0,0,0);
   if(count!=921600)$fatal(1,"720P PIXEL COUNT %0d",count);
   $display("QUALITY_720P FRAME PASS Q%0d pixels=%0d 1650x750 stream",em,count);
  end
  if(total!=2764800)$fatal(1,"TOTAL COUNT");
  $display("QUALITY_720P PASS 2764800 active pixels exact, three full HDMI timing frames, overlay and boundaries");$finish;
 end
endmodule
