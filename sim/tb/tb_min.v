`timescale 1ns / 1ps
// 最小化：只跑 tile_fetch，读服务端永远 ready 且立刻给 1 拍数据
module tb_min;
    reg clk = 0, rstn = 0;
    always #5 clk = ~clk;

    reg start = 0;
    wire r_req, r_ready, r_done, r_valid, r_last, we, busy, done;
    wire [27:0] r_addr;
    wire [7:0]  r_beats;
    wire [255:0] r_data;
    wire [11:0] waddr;
    wire [15:0] wdata;

    assign r_ready = 1'b1;
    assign r_valid = 1'b0;
    assign r_done  = 1'b0;
    assign r_last  = 1'b0;
    assign r_data  = 256'd0;

    tile_fetch #(.BW(64), .BH(64), .AW(28)) u_dut (
        .clk(clk), .rstn(rstn),
        .start(start), .base_addr(28'd0), .stride_words(16'd32),
        .u0(16'd0), .v0(16'd0), .bw(6'd64), .bh(6'd64),
        .r_req(r_req), .r_addr(r_addr), .r_beats(r_beats),
        .r_ready(r_ready), .r_done(r_done),
        .r_data(r_data), .r_valid(r_valid), .r_last(r_last),
        .we(we), .waddr(waddr), .wdata(wdata),
        .busy(busy), .done(done)
    );

    integer cyc = 0;
    always @(posedge clk) cyc <= cyc + 1;

    initial begin
        repeat (3) @(posedge clk);
        rstn = 1;
        repeat (2) @(posedge clk);
        start <= 1;
        @(posedge clk);
        start <= 0;
        repeat (2000) @(posedge clk);
        $display("MIN: cyc=%0d busy=%b done=%b r_req=%b", cyc, busy, done, r_req);
        $finish;
    end
endmodule
