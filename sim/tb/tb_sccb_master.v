`timescale 1ns/1ps
module tb_sccb_master;
 reg clk=0,rstn=0,start=0,read_i=0;always #5 clk=~clk;
 reg[15:0] address=16'h1234;reg[7:0] value=8'ha5;reg[3:0] mask=0;
 wire busy,done,error,scl;wire[7:0] data;tri1 sda;
 sccb_checked_master #(.TICK_DIV(2)) dut(.clk(clk),.rstn(rstn),.start(start),.read_i(read_i),.address(address),.write_data(value),
  .busy(busy),.done(done),.error(error),.read_data(data),.scl(scl),.sda(sda));
 sccb_sensor_model sensor(.scl(scl),.sda(sda),.nack_all(1'b0),.nack_mask(mask),.nack_format_once(1'b0),.bad_format_read_once(1'b0));
 task transact;begin @(negedge clk);start=1;@(negedge clk);start=0;wait(done);@(negedge clk);end endtask
 integer n;
 initial begin
  #1;rstn=0;repeat(4)@(negedge clk);rstn=1;
  transact;if(error || sensor.memory[16'h1234]!==8'ha5)$fatal(1,"WRITE");
  read_i=1;transact;if(error || data!==8'ha5)$fatal(1,"READ");read_i=0;
  for(n=0;n<4;n=n+1)begin mask=1<<n;transact;if(!error)$fatal(1,"NACK BYTE %0d LOST",n);end
  mask=0;value=8'h3c;transact;if(error)$fatal(1,"ERROR NOT CLEARED NEXT TRANSACTION");
  read_i=1;transact;if(error || data!==8'h3c)$fatal(1,"READ AFTER RECOVERY");
  $display("SCCB_MASTER PASS pointer STOP/read, data byte, four individual ACK failures retained and clean recovery");$finish;
 end
 initial begin #200000;$fatal(1,"MASTER TIMEOUT");end
endmodule
