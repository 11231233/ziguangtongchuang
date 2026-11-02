`timescale 1ns/1ps
module tb_gamma_capture;
 reg sclk=0,dclk=0,rstn=0,vs=0,de=0,key_n=1;reg [15:0] pixel=0;
 always #7 sclk=~sclk;always #5 dclk=~dclk;
 wire gv,gd;wire [15:0] gp;wire en;wire [1:0] curve;
 adaptive_gamma #(.WIDTH(256),.HEIGHT(2),.DEBOUNCE_CYCLES(3)) gamma(
  .clk(sclk),.rstn(rstn),.vs(vs),.de(de),.pixel(pixel),.key_n(key_n),.test_key_n(1'b1),
  .vs_o(gv),.de_o(gd),.pixel_o(gp),.active_enabled(en),.active_curve(curve),.status_code(),.status_toggle());
 wire req;wire [27:0] addr;wire [7:0] beats;wire [255:0] data;
 reg ready=0,done=0,adv=0;wire frame_done,valid,overflow;
 frame_writer #(.H_ACT(256),.V_ACT(2),.FLIP_V(1)) fw(
  .src_clk(sclk),.src_rstn(rstn),.src_vs(gv),.src_de(gd),.src_pix(gp),
  .ddr_clk(dclk),.ddr_rstn(rstn),.w_req(req),.w_addr(addr),.w_beats(beats),
  .w_ready(ready),.w_done(done),.w_data(data),.w_adv(adv),.wr_slot(),.led_overflow(overflow),
  .hold_valid(1'b0),.hold_slot(3'd0),.frame_done(frame_done),.frame_valid(valid),.frame_slot(),.frame_seq());
 reg [15:0] expected[0:2047];integer produced=0,consumed=0,frames=0,commands=0;
 reg armed=0;integer a,b,c;real power_value;
 always @(posedge sclk)if(rstn)begin
  if(vs)armed=1;
  else if(armed&&de)begin
   a=pixel[15:11];b=pixel[10:5];c=pixel[4:0];
   if(en && curve!=0)begin
    power_value=(curve==1)?0.75:1.25;
    a=$rtoi(31.0*$pow(a/31.0,power_value)+0.5);
    b=$rtoi(63.0*$pow(b/63.0,power_value)+0.5);
    c=$rtoi(31.0*$pow(c/31.0,power_value)+0.5);
   end
   expected[produced]={a[4:0],b[5:0],c[4:0]};produced=produced+1;
  end
 end
 integer beat,j;reg [27:0] command_addr;reg busy=0;reg [255:0] sampled;
 always @(negedge dclk)begin
  ready=0;done=0;adv=0;
  if(rstn)begin
   if(!busy&&req)begin
    if(beats!=16)$fatal(1,"CAPTURE BURST LENGTH");
    command_addr=addr;
    // Six protected slots start at slot zero; source row order is written
    // to flipped destination rows without changing any pixel within a row.
    if(addr!==((commands/2)*460800+((commands%2)==0?128:0)))$fatal(1,"GAMMA FRAME/ROW ADDRESS");
    ready=1;busy=1;beat=0;commands=commands+1;
   end else if(busy)begin
    if(beat<16)begin
     sampled=data;
     for(j=0;j<16;j=j+1)begin
      if(consumed>=produced || sampled[j*16+:16]!==expected[consumed])
       $fatal(1,"GAMMA CAPTURE PIXEL %0d got %h expected %h",consumed,sampled[j*16+:16],expected[consumed]);
      consumed=consumed+1;
     end
     adv=1;beat=beat+1;
    end else begin done=1;busy=0;end
   end
  end
 end
 always @(posedge dclk)if(rstn&&frame_done)frames=frames+1;
 task send_frame(input integer ramp);integer n;begin
  @(negedge sclk);vs=1;de=0;@(negedge sclk);vs=0;
  for(n=0;n<512;n=n+1)begin
   de=1;pixel=ramp?(n*123+17):16'h2104;@(negedge sclk);
   if(n%11==4)begin de=0;@(negedge sclk);end
  end
  de=0;repeat(120)@(negedge sclk);
 end endtask
 initial begin
  repeat(5)@(negedge sclk);rstn=1;
  send_frame(0);send_frame(0);send_frame(0);
  key_n=0;repeat(15)@(negedge sclk);key_n=1;repeat(15)@(negedge sclk);
  send_frame(1);
  if(!en || curve!=1)$fatal(1,"INTEGRATION DID NOT EXERCISE GAMMA");
  wait(frames==4);repeat(10)@(negedge dclk);
  if(overflow || !valid || produced!=2048 || consumed!=2048 || commands!=8)$fatal(1,"INTEGRATION COMPLETION");
  $display("GAMMA_CAPTURE PASS: independent clocks, 4 complete frames, 2048 RGB565 pixels against independent Gamma formula, exact flipped DDR addresses, first/last pixels and blanking");$finish;
 end
 initial begin #1000000;$fatal(1,"GAMMA CAPTURE TIMEOUT");end
endmodule
