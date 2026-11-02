`timescale 1ns/1ps
module tb_display_retire;
reg pc=0,dc=0,rstn=0,vs=0,ls=0,wr=1;
always #7 pc=~pc;always #5 dc=~dc;
wire req,shown,seen,under;wire[27:0]addr;wire[7:0]beats;wire[15:0]pix;
reg ready=0,valid=0,done=0;integer j;
disp_reader #(.H_ACT(256),.V_ACT(2),.SLOT_WORDS(256),.EXTERNAL_LINE(1)) dut(
.pix_clk(pc),.pix_rstn(rstn),.vs(vs),.hs(1'b0),.de(1'b0),.pix_out(pix),.wr_slot(wr),.frame_valid(1'b1),.shown_slot(shown),.frame_seen(seen),.line_start(ls),.line_y(10'd0),
.ddr_clk(dc),.ddr_rstn(rstn),.r_req(req),.r_addr(addr),.r_beats(beats),.r_ready(ready),.r_done(done),.r_data(256'd0),.r_valid(valid),.r_last(1'b0),.led_underrun(under));
initial begin
 repeat(5)@(negedge pc);rstn=1;vs=1;repeat(10)@(negedge pc);vs=0;
 @(negedge pc);ls=1;@(negedge pc);ls=0;
 wait(req);if(addr!=0)$fatal(1,"OLD SLOT ADDRESS");
 // Old row remains outstanding across the vertical blank and front-slot switch.
 @(negedge pc);wr=0;vs=1;repeat(15)@(negedge pc);
 if(!dut.rd_slot || shown)$fatal(1,"OLD SLOT RELEASED BEFORE DDR DRAIN");
 @(negedge dc);ready=1;@(negedge dc);ready=0;
 for(j=0;j<16;j=j+1)begin valid=1;@(negedge dc);end
 valid=0;done=1;@(negedge dc);done=0;
 repeat(10)@(negedge dc);
 if(!shown)$fatal(1,"SLOT ACK NEVER RECOVERED");
 $display("DISPLAY_RETIRE PASS: old source is protected until stalled DDR row finishes across VS");$finish;
end
initial begin #20000;$fatal(1,"TIMEOUT RETIRE");end
endmodule
