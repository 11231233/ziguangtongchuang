`timescale 1ns/1ps
module tb_margin_writer #(parameter HEIGHT=972);
localparam WIDTH=1296,STRIDE=768,CHUNKS=6,SLOT=STRIDE*HEIGHT;
reg src=0,clk=0,rstn=0,vs=0,de=0;reg[15:0]pixel=0;
always #13 src=~src;always #5 clk=~clk;
wire req,ready,adv,done,overflow,frame_done,frame_valid;wire[27:0]addr;wire[7:0]beats;wire[255:0]data;
wire[2:0]wr_slot,frame_slot;wire[31:0]frame_seq;
frame_writer #(.H_ACT(WIDTH),.V_ACT(HEIGHT),.STRIDE_WORDS(STRIDE),.SLOT_WORDS(SLOT),.FLIP_V(1),.SLOT_COUNT(3)) dut(
.src_clk(src),.src_rstn(rstn),.src_vs(vs),.src_de(de),.src_pix(pixel),.ddr_clk(clk),.ddr_rstn(rstn),
.w_req(req),.w_addr(addr),.w_beats(beats),.w_ready(ready),.w_done(done),.w_data(data),.w_adv(adv),
.wr_slot(wr_slot),.led_overflow(overflow),.hold_valid(1'b0),.hold_slot(3'd0),
.frame_done(frame_done),.frame_valid(frame_valid),.frame_slot(frame_slot),.frame_seq(frame_seq));
function[15:0]rgb(input integer x,y);begin rgb=(((x*13+y*7)%32)<<11)|(((x+y*3)%64)<<5)|((x*3+y*5)%32);end endfunction
reg[31:0]rng=32'h12345;reg busy=0;integer beat=0,row=0,chunk=0,delay_count=0,transactions=0,checked=0,padding=0,j;
assign ready=!busy && rng[0];assign adv=busy && delay_count==0 && beat<16 && rng[2];
assign done=busy && beat==16 && delay_count==0;
always @(posedge clk)begin
 rng<={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
 if(!rstn)begin busy=0;beat=0;row=0;chunk=0;delay_count=0;end
 else begin
  if(delay_count>0)delay_count=delay_count-1;
  if(req && ready)begin
   if(addr!==((HEIGHT-1-row)*STRIDE+chunk*128) || beats!==16)$fatal(1,"Bad padded address row=%0d chunk=%0d addr=%0d",row,chunk,addr);
   busy=1;beat=0;delay_count=3;
  end else if(adv)begin
   for(j=0;j<16;j=j+1)begin
    if(chunk*256+beat*16+j<WIDTH)begin
     if(data[j*16+:16]!==rgb(chunk*256+beat*16+j,row))$fatal(1,"Lost real tail pixel row=%0d x=%0d",row,chunk*256+beat*16+j);
     checked=checked+1;
    end else begin
     if(data[j*16+:16]!==0)$fatal(1,"Row padding stole next-row data");padding=padding+1;
    end
   end
   beat=beat+1;if(beat==16)delay_count=3;
  end else if(done)begin
   busy=0;transactions=transactions+1;
   if(chunk==CHUNKS-1)begin chunk=0;row=row+1;end else chunk=chunk+1;
  end
 end
end
integer sx,sy;
initial begin
 repeat(5)@(negedge src);rstn=1;repeat(8)@(negedge src);vs=1;repeat(3)@(negedge src);vs=0;repeat(4)@(negedge src);
 for(sy=0;sy<HEIGHT;sy=sy+1)begin
  for(sx=0;sx<WIDTH;sx=sx+1)begin @(negedge src);de=1;pixel=rgb(sx,sy);end
  @(negedge src);de=0;repeat(4)@(negedge src);
 end
 wait(frame_done);@(negedge clk);
 if(!frame_valid || frame_seq!==1 || frame_slot!==0 || overflow || checked!=WIDTH*HEIGHT || padding!=(1536-WIDTH)*HEIGHT || transactions!=CHUNKS*HEIGHT)$fatal(1,"Incomplete padded frame");
 $display("MARGIN_WRITER PASS real_pixels=%0d padding_pixels=%0d bursts=%0d, last16 columns exact, row flip, stalls and completion",checked,padding,transactions);$finish;
end
initial begin #100000000;$fatal(1,"Timeout");end
endmodule
