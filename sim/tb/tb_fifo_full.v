`timescale 1ns/1ps
module tb_fifo_full;
reg wc=0,rc=0,rstn=0;always #7 wc=~wc;always #11 rc=~rc;
reg [15:0] nwrite=0;integer nread=0,ct=0;reg saw_full=0;
wire full,empty;wire [15:0] data;wire [4:0] count;
wire wen=nwrite<500;wire ren=ct>60 && !empty;
async_fifo #(.DW(16),.AW(4)) dut(.wclk(wc),.wrst_n(rstn),.wen(wen),.wdata(nwrite),.full(full),.rclk(rc),.rrst_n(rstn),.ren(ren),.rdata(data),.empty(empty),.rcount(count));
always @(posedge wc) if(rstn) begin if(wen&&!full)nwrite<=nwrite+1'b1;if(full)saw_full<=1;end
always @(posedge rc) if(rstn) begin ct<=ct+1;if(ren) begin if(data!==nread[15:0])$fatal(1,"FIFO ORDER");nread<=nread+1;end end
initial begin #100;rstn=1;wait(nread==500);#100;if(!empty||!saw_full)$fatal(1,"FIFO END");$display("FIFO_FULL PASS: 500 words, fill, wrap, drain, unrelated clocks");$finish;end
initial begin #50000;$fatal(1,"TIMEOUT FIFO");end
endmodule
