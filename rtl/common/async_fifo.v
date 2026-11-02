`timescale 1ns / 1ps
// ============================================================================
// async_fifo.v — 双时钟异步 FIFO（gray 指针，读写各 2 级同步）
//
//   用途：像素时钟域 ↔ DDR 时钟域 的数据搬运。
//   深度 2^AW，宽度 DW。满/空标志保守但安全（多留 1 个空位）。
// ============================================================================
`default_nettype none

module async_fifo #(
    parameter integer DW = 32,
    parameter integer AW = 8
) (
    // 写侧
    input  wire            wclk,
    input  wire            wrst_n,      // 低有效，异步
    input  wire            wen,
    input  wire [DW-1:0]   wdata,
    output wire            full,
    // 读侧
    input  wire            rclk,
    input  wire            rrst_n,
    input  wire            ren,
    output wire [DW-1:0]   rdata,
    output wire            empty,
    output wire [AW:0]     rcount      // 读域看到的“可读拍数”（保守值）
);
    localparam integer N = 1 << AW;

    reg [DW-1:0] mem [0:N-1];

    reg  [AW:0] wbin = 0;
    reg  [AW:0] wgray = 0;
    reg  [AW:0] rbin = 0;
    reg  [AW:0] rgray = 0;

    // 跨域同步
    (* async_reg="true" *) reg [AW:0] wq1_rgray = 0, wq2_rgray = 0;
    (* async_reg="true" *) reg [AW:0] rq1_wgray = 0, rq2_wgray = 0;

    reg full_r = 0;
    // ---------------- 写侧 ----------------
    wire [AW:0] wbin_nxt   = wbin + (wen && !full);
    wire [AW:0] wgray_nxt  = (wbin_nxt >> 1) ^ wbin_nxt;
    wire        full_i     = (wgray_nxt == {~wq2_rgray[AW:AW-1], wq2_rgray[AW-2:0]});

    always @(posedge wclk or negedge wrst_n) begin
        if (!wrst_n) begin
            full_r <= 0;
            wbin  <= 0;
            wgray <= 0;
            wq1_rgray <= 0;
            wq2_rgray <= 0;
        end else begin
            full_r <= full_i;
            wq1_rgray <= rgray;
            wq2_rgray <= wq1_rgray;
            if (wen && !full) begin
                mem[wbin[AW-1:0]] <= wdata;
                wbin  <= wbin_nxt;
                wgray <= wgray_nxt;
            end
        end
    end

    // ---------------- 读侧 ----------------
    wire [AW:0] rbin_nxt  = rbin + (ren && !empty);
    wire [AW:0] rgray_nxt = (rbin_nxt >> 1) ^ rbin_nxt;
    wire        empty_i   = (rgray == rq2_wgray);

    always @(posedge rclk or negedge rrst_n) begin
        if (!rrst_n) begin
            rbin  <= 0;
            rgray <= 0;
            rq1_wgray <= 0;
            rq2_wgray <= 0;
        end else begin
            rq1_wgray <= wgray;
            rq2_wgray <= rq1_wgray;
            if (ren && !empty) begin
                rbin  <= rbin_nxt;
                rgray <= rgray_nxt;
            end
        end
    end

    function [AW:0] gray2bin(input [AW:0] g);
        integer i;
        begin
            gray2bin[AW] = g[AW];
            for (i = AW-1; i >= 0; i = i - 1)
                gray2bin[i] = gray2bin[i+1] ^ g[i];
        end
    endfunction

    wire [AW:0] wbin_sync = gray2bin(rq2_wgray);
    assign rcount = wbin_sync - rbin;

    // Synchronous look-ahead read. On a consumed head, fetch the next address
    // at this edge; otherwise keep prefetching the current head. Two-clock
    // pointer synchronization ensures a new write is readable before empty
    // deasserts. This preserves FWFT while allowing block RAM inference.
    reg [DW-1:0] read_head;
    always @(posedge rclk) read_head <= mem[rbin_nxt[AW-1:0]];
    assign rdata = read_head;
    assign full  = full_r;
    assign empty = empty_i;

endmodule

`default_nettype wire
