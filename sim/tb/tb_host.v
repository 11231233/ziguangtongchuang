`timescale 1ns/1ps
module tb_host;
 reg clk=0,rstn=0,rx=1,fs=0,release_host=0;
 always #5 clk=~clk;
 wire valid,bad,active,ok,err;wire [7:0] data,seq;wire [447:0] coeff;
 uart_rx #(.CLK_HZ(100),.BAUD(10)) ur(.clk(clk),.rstn(rstn),.rx(rx),.valid(valid),.data(data),.framing_error(bad));
 warp_config #(.TIMEOUT_CYCLES(2000)) cfg(.clk(clk),.rstn(rstn),.byte_valid(valid),.byte_data(data),
  .abort_packet(bad),.frame_start(fs),.release_host(release_host),.active_coeff(coeff),.active(active),
  .packet_ok(ok),.packet_error(err),.active_sequence(seq));
 reg [7:0] bytes[0:61];reg [447:0] expected[0:0];
 integer good_count=0,error_count=0;
 always @(posedge clk)begin if(ok)good_count<=good_count+1;if(err)error_count<=error_count+1;end
 task send_byte(input [7:0] b);integer bitno;
  begin rx=0;repeat(10)@(negedge clk);
   for(bitno=0;bitno<8;bitno=bitno+1)begin rx=b[bitno];repeat(10)@(negedge clk);end
   rx=1;repeat(12)@(negedge clk);
  end
 endtask
 task boundary;begin fs=1;@(negedge clk);fs=0;@(negedge clk);end endtask
 integer i;
 reg done=0;wire tx,tvalid,tbad;wire [7:0] tdata;wire [31:0] last_cycles,frames;
 warp_telemetry #(.CLK_HZ(100),.BAUD(10)) tm(.clk(clk),.rstn(rstn),.frame_start(fs),.frame_done(done),
  .sequence_id(seq),.tx(tx),.last_cycles(last_cycles),.completed_frames(frames));
 uart_rx #(.CLK_HZ(100),.BAUD(10)) monitor(.clk(clk),.rstn(rstn),.rx(tx),.valid(tvalid),.data(tdata),.framing_error(tbad));
 reg [7:0] status[0:13];integer count=0;
 always @(posedge clk)if(tvalid)begin status[count]<=tdata;count<=count+1;end
 function [15:0] crc_byte(input [15:0] crc,input [7:0] value);
  reg [15:0] c;integer j;
  begin c=crc^{value,8'd0};for(j=0;j<8;j=j+1)c=c[15]?((c<<1)^16'h1021):(c<<1);crc_byte=c;end
 endfunction
 reg [15:0] crc;
 initial begin
  $readmemh("sim/out/host_packet.hex",bytes);$readmemh("sim/out/host_coeff.hex",expected);
  repeat(5)@(negedge clk);rstn=1;repeat(5)@(negedge clk);
  for(i=0;i<62;i=i+1)send_byte(bytes[i]);
  if(good_count!=1 || active)$fatal(1,"PACKET NOT ATOMIC");boundary;
  if(!active || coeff!==expected[0] || seq!=37)$fatal(1,"HOST CONFIG CONTENT");
  // Bad CRC must retain the previously committed bank.
  for(i=0;i<62;i=i+1)send_byte(i==20?(bytes[i]^8'h01):bytes[i]);
  boundary;if(good_count!=1 || error_count!=1 || coeff!==expected[0])$fatal(1,"BAD CRC ACCEPTED");
  // Truncated packet times out and receiver can immediately accept a fresh one.
  for(i=0;i<8;i=i+1)send_byte(bytes[i]);
  repeat(2100)@(negedge clk);
  for(i=0;i<62;i=i+1)send_byte(bytes[i]);
  if(good_count!=2 || error_count!=2)$fatal(1,"TIMEOUT RECOVERY");
  // Releasing host mode in midframe must wait for the next boundary.
  release_host=1;@(negedge clk);release_host=0;@(negedge clk);
  if(!active)$fatal(1,"MIDFRAME RELEASE");boundary;
  if(active)$fatal(1,"RELEASE NOT APPLIED");
  // Confirm physical TX -> RX status framing and CRC.
  repeat(123)@(negedge clk);done=1;@(negedge clk);done=0;
  repeat(1700)@(negedge clk);
  if(count!=14 || status[0]!=8'ha5 || status[1]!=8'h5b || status[2]!=1 || status[3]!=37 || frames!=1)
   $fatal(1,"STATUS FRAME count=%d",count);
  if({status[7],status[6],status[5],status[4]}!==last_cycles)$fatal(1,"STATUS CYCLES");
  crc=16'hffff;for(i=2;i<12;i=i+1)crc=crc_byte(crc,status[i]);
  if({status[12],status[13]}!=crc)$fatal(1,"STATUS CRC");
  $display("HOST PASS: UART, CRC, corrupt/truncated recovery, atomic bank, frame-boundary release, measured telemetry");$finish;
 end
 initial begin #1000000;$fatal(1,"HOST TIMEOUT");end
endmodule
