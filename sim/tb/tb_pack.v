`timescale 1ns/1ps
module tb_pack;
reg clk=0,rstn=0,we=0;always #5 clk=~clk;
reg [15:0] ox=0,oy=0,pix=0;
wire req,ready,done,adv,ovf,idle;wire [27:0] addr;wire [7:0] beats;wire [255:0] data;
out_pack dut(.clk(clk),.rstn(rstn),.dst_base(28'd1000000),.we(we),.ox(ox),.oy(oy),.pix(pix),.w_req(req),.w_addr(addr),.w_beats(beats),.w_ready(ready),.w_done(done),.w_data(data),.w_adv(adv),.overflow(ovf),.idle(idle));
reg [31:0] rng=32'habc;always @(posedge clk)rng<={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
reg busy=0;integer tail=0,n=0,k,yy;
assign ready=!busy&&rng[0];assign adv=busy&&tail==0&&rng[2];assign done=busy&&tail==1;
always @(posedge clk)begin
 if(req&&ready) begin busy<=1;yy=(n==80)?719:n;if(addr!=1000000+yy*640||beats!=1)$fatal(1,"PACK ADDRESS");end
 if(adv)begin
  for(k=0;k<16;k=k+1)if(data[k*16+:16]!==((yy*16+k)&16'hffff))$fatal(1,"PACK DATA");
  n<=n+1;tail<=7;
 end
 if(tail>0)begin tail<=tail-1;if(tail==1)busy<=0;end
end
integer y,x;
initial begin
 repeat(5)@(negedge clk);rstn=1;
 for(y=0;y<82;y=y+1)begin
  for(x=0;x<16;x=x+1)begin
   @(negedge clk);we=1;ox=x;oy=y<80?y:(y==80?719:720);pix=oy*16+x;
   @(negedge clk);we=0;
  end
 end
 repeat(500)@(negedge clk);
 if(n!=81||ovf||!idle)$fatal(1,"PACK END n=%d ovf=%b idle=%b",n,ovf,idle);
 $display("PACK PASS: 81 unique packets, random stalls, row720 suppressed, fully drained");$finish;
end
initial begin #1000000;$fatal(1,"TIMEOUT PACK");end
endmodule
