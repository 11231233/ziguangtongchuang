`timescale 1ns/1ps
module tb_host_ranges;
 reg clk=0,rst=0,bv=0,fs=0;reg [7:0] b=0;always #5 clk=~clk;
 wire active,ok,err;wire [7:0] seq;wire [447:0] coeff;
 warp_config dut(.clk(clk),.rstn(rst),.byte_valid(bv),.byte_data(b),.abort_packet(1'b0),.frame_start(fs),.release_host(1'b0),
  .active_coeff(coeff),.active(active),.packet_ok(ok),.packet_error(err),.active_sequence(seq));
 reg [7:0] bytes[0:557];integer i,j,good=0,bad=0;
 always @(posedge clk)begin if(ok)good<=good+1;if(err)bad<=bad+1;end
 initial begin
  $readmemh("sim/out/audit_host_ranges.hex",bytes);
  repeat(4)@(negedge clk);rst=1;
  for(j=0;j<9;j=j+1)begin
   for(i=0;i<62;i=i+1)begin @(negedge clk);bv=1;b=bytes[j*62+i];end
   @(negedge clk);bv=0;repeat(2)@(negedge clk);fs=1;@(negedge clk);fs=0;@(negedge clk);
   if(j<7 && (!active || seq!=17))$fatal(1,"INVALID COEFFICIENT BANK COMMITTED j=%d seq=%d",j,seq);
   if(j==7 && (!active || seq!=31))$fatal(1,"VALID RECOVERY LOST");
   if(j==8 && (!active || seq!=42))$fatal(1,"LEGAL SIGNED BOUNDARY REJECTED");
  end
  if(good!=3 || bad!=6)$fatal(1,"RANGE COUNTS good=%d bad=%d",good,bad);
  $display("HOST_RANGES PASS six valid-CRC invalid payloads rejected, active bank retained, recovery and signed endpoints");$finish;
 end
 initial begin #20000;$fatal(1,"HOST RANGE TIMEOUT");end
endmodule
