`timescale 1ns / 1ps
// ============================================================================
// tile_fetch.v — 把源图包围盒按行读进 tile RAM（64×64×16bit）
//
//   行地址：base + (v0+row)*stride + u0/2   （单位：32bit 字）
//   每行读 beats_per_row = bw/16 拍（1 拍 = 16 像素）
//   读回的数据先入 256bit FIFO，再以 16 像素/16 拍 的节奏写入 16bit tile RAM。
//   （取数比写入快，用 FIFO 吸收；64×64 块约 4.2k 拍完成，30fps 够用）
// ============================================================================
`default_nettype none

module tile_fetch #(
    parameter integer BW = 64,
    parameter integer BH = 64,
    parameter integer AW = 28
) (
    input  wire            clk,
    input  wire            rstn,

    input  wire            start,
    input  wire [AW-1:0]   base_addr,
    input  wire [15:0]     stride_words,
    input  wire [15:0]     u0, v0,
    input  wire [5:0]      bw, bh,

    // 读客户端（接 mem_hub r1）
    output reg             r_req,
    output reg  [AW-1:0]   r_addr,
    output wire [7:0]      r_beats,
    input  wire            r_ready,
    input  wire            r_done,
    input  wire [255:0]    r_data,
    input  wire            r_valid,
    input  wire            r_last,

    // tile RAM 写口
    output reg             we,
    output reg  [11:0]     waddr,
    output reg  [15:0]     wdata,

    output reg             busy,
    output reg             done
);

    localparam integer BPR = BW / 16;              // 每行拍数（BW=64 → 4）
    localparam [7:0] BPR8 = BW / 16;
    localparam integer BEATS = BPR * BH;           // 总拍数

    reg [15:0] row;
    reg [1:0]  fsm;

    // 读回数据 FIFO（256bit × 16）
    wire        fifo_we = r_valid;
    wire [255:0] fifo_dout;
    wire        fifo_re;
    wire        fifo_empty;
    wire [4:0]  fifo_cnt;

    async_fifo #(.DW(256), .AW(4)) u_fifo (
        .wclk  (clk),
        .wrst_n(rstn),
        .wen   (fifo_we),
        .wdata (r_data),
        .full  (),
        .rclk  (clk),
        .rrst_n(rstn),
        .ren   (fifo_re),
        .rdata (fifo_dout),
        .empty (fifo_empty),
        .rcount(fifo_cnt)
    );

    // 写侧计数
    reg [5:0] row_cnt;         // 当前行（0..63）
    reg [1:0] beat_col;        // 行内第几拍（0..3）
    reg [3:0] pix_cnt;         // 拍内像素 0..15
    reg [255:0] beat_buf;

    assign r_beats = BPR8;
    assign fifo_re = (fsm == 2'd2) && !fifo_empty && (pix_cnt == 4'd0);

    localparam F_IDLE = 2'd0, F_RUN = 2'd1, F_DRAIN = 2'd2;

    always @(posedge clk) begin
        if (!rstn) begin
            fsm <= F_IDLE; busy <= 1'b0; done <= 1'b0;
            r_req <= 1'b0; r_addr <= {AW{1'b0}};
            row <= 16'd0; row_cnt <= 6'd0; beat_col <= 2'd0; pix_cnt <= 4'd0;
            we <= 1'b0; waddr <= 12'd0; wdata <= 16'd0;
            beat_buf <= 256'd0;
        end else begin
            we   <= 1'b0;
            done <= 1'b0;

            case (fsm)
                F_IDLE: begin
                    if (start) begin
                        busy     <= 1'b1;
                        row      <= 16'd0;
                        row_cnt  <= 6'd0;
                        beat_col <= 2'd0;
                        r_addr   <= base_addr + v0 * stride_words + {1'b0, u0[15:1]};
                        r_req    <= 1'b1;
                        fsm      <= F_RUN;
                    end
                end

                F_RUN: begin
                    if (r_req && r_ready) r_req <= 1'b0;
                    if (r_done) begin
                        if (row == bh - 1) begin
                            fsm <= F_DRAIN;
                        end else begin
                            row    <= row + 16'd1;
                            r_addr <= r_addr + stride_words;
                            r_req  <= 1'b1;
                        end
                    end
                end

                F_DRAIN: begin
                    if (pix_cnt == 4'd0) begin
                        if (!fifo_empty) begin
                            beat_buf <= fifo_dout;
                            pix_cnt  <= 4'd1;
                        end
                    end else begin
                        we    <= 1'b1;
                        waddr <= (row_cnt << 6) + ({4'd0, beat_col} << 4) + {8'd0, pix_cnt};
                        wdata <= beat_buf[15:0];
                        beat_buf <= {16'd0, beat_buf[255:16]};
                        if (pix_cnt == 4'd15) begin
                            pix_cnt <= 4'd0;
                            if (beat_col == BPR - 1) begin
                                beat_col <= 2'd0;
                                if (row_cnt == bh - 1) begin
                                    busy <= 1'b0;
                                    done <= 1'b1;
                                    fsm  <= F_IDLE;
                                end else begin
                                    row_cnt <= row_cnt + 6'd1;
                                end
                            end else begin
                                beat_col <= beat_col + 2'd1;
                            end
                        end else begin
                            pix_cnt <= pix_cnt + 4'd1;
                        end
                    end
                end
            endcase
        end
    end

endmodule

`default_nettype wire
