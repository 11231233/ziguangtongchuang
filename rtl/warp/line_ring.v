`timescale 1ns / 1ps
// ============================================================================
// line_ring.v — 行环形缓冲：源行按顺序写入，矫正侧按 (u,v) 随机读 4 邻域
//
//   · 深度 ROWS 行（必须是 2 的幂），每行 W 像素，16bit RGB565
//   · 写：wr_en + wr_row + wr_x + wr_pix（源行到达时逐像素写入）
//   · 读：给 (u,v)，1 拍后 rd_pix 有效；rd_hit 表示该行仍在环内
//   · 供 warp_stream 做“逐行到达 + 逐像素取数”的实时矫正
// ============================================================================
`default_nettype none

module line_ring #(
    parameter integer W    = 256,
    parameter integer ROWS = 32
) (
    input  wire        clk,
    input  wire        rstn,

    // 写侧（源行）
    input  wire        wr_en,
    input  wire [15:0] wr_row,
    input  wire [15:0] wr_x,
    input  wire [15:0] wr_pix,

    // 读侧（矫正）
    input  wire [15:0] rd_u,
    input  wire [15:0] rd_v,
    output reg  [15:0] rd_pix,
    output reg         rd_hit,

    // 状态
    output reg  [15:0] ring_wr_row      // 已写到第几行（含）
);
    localparam integer WB = $clog2(W);
    localparam integer RB = $clog2(ROWS);

    reg [15:0] mem [0:W*ROWS-1];

    // ---------------- 写 ----------------
    wire [RB-1:0]  slot_w = wr_row[RB-1:0];
    wire [WB+RB-1:0] waddr = {slot_w, wr_x[WB-1:0]};

    always @(posedge clk) begin
        if (wr_en && wr_x < W) mem[waddr] <= wr_pix;
    end

    // ---------------- 行计数 ----------------
    always @(posedge clk) begin
        if (!rstn)               ring_wr_row <= 16'd0;
        else if (wr_en && wr_x == 0) ring_wr_row <= wr_row;
    end

    // ---------------- 读 ----------------
    wire [RB-1:0]    slot_r = rd_v[RB-1:0];
    wire [WB-1:0]    xi     = (rd_u >= W) ? (W-1) : rd_u[WB-1:0];
    wire [WB+RB-1:0] raddr  = {slot_r, xi};

    // 行是否还在环内：rd_v 必须在 [ring_wr_row-ROWS+1, ring_wr_row]
    wire signed [16:0] diff = $signed({1'b0, ring_wr_row}) - $signed({1'b0, rd_v});

    always @(posedge clk) begin
        if (!rstn) begin
            rd_pix <= 16'd0;
            rd_hit <= 1'b0;
        end else begin
            rd_pix <= mem[raddr];
            rd_hit <= (diff >= 0) && (diff < ROWS);
        end
    end

    wire _unused = &{1'b0, 1'b1};

endmodule

`default_nettype wire
