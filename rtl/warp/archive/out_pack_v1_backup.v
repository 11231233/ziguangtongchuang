`timescale 1ns / 1ps
// ============================================================================
// out_pack.v — 矫正像素流 → 256bit 突发写 DDR
//
//   warp_tile 逐像素输出 (ox,oy,pix,we)，本模块把同一行的 16 个像素打包成
//   一个 256bit 拍（32 字节 = 16 像素），通过 mem_hub 的写客户端（w1）突发写回。
//
//   行内地址：dst_base + oy*WORDS_PER_LINE + (ox/2)，单位 32bit 字。
//   一条命令 2 拍（一个 tile 行 = 32 像素 = 64 字节 = 2 拍）。
// ============================================================================
`default_nettype none

module out_pack #(
    parameter integer TEST_PAT = 0,   // 1 = 整帧写固定色，用于判断显示端是否读矫正槽
    parameter integer WORDS_PER_LINE = 640,
    parameter integer AW = 28
) (
    input  wire            clk,
    input  wire            rstn,

    // 目标帧基址（32bit 字）
    input  wire [AW-1:0]   dst_base,

    // 像素流（warp_tile 输出）
    input  wire            we,
    input  wire [15:0]     ox, oy,
    input  wire [15:0]     pix,

    // DDR 写客户端（mem_hub w1）
    output reg             w_req,
    output reg  [AW-1:0]   w_addr,
    output reg  [7:0]      w_beats,
    input  wire            w_ready,
    input  wire            w_done,
    output wire [255:0]    w_data,
    input  wire            w_adv,

    // 诊断
    output reg             overflow
);

    // 打包缓冲：两拍（2×256bit）足够覆盖一个 32 像素行
    reg [255:0] line_buf [0:1];
    reg [1:0]   beat_cnt;      // 已填好的拍数
    reg [3:0]   pix_cnt;       // 当前拍内像素数
    reg [255:0] cur;
    reg [15:0]  cur_oy;
    reg [AW-1:0] addr_lat;      // 本行第 0 拍的写地址（打包完成时锁存）
    reg [15:0]  row_x0;        // 本行起始 x

    // 写命令 FSM
    reg [1:0]   st;
    localparam S_IDLE = 2'd0, S_CMD = 2'd1, S_DATA = 2'd2;
    reg [1:0]   send_beat;

    wire [15:0] pix_w = TEST_PAT ? 16'hF800 : pix;   // F800 = 纯红

    assign w_data = line_buf[send_beat];

    // 两拍发完 → 清打包计数（放在打包块里消费，避免多驱动）
    wire beat_clear = (st == S_DATA) && w_adv && (send_beat == 2'd1);

    // ---------------------------------------------------------------- 打包
    always @(posedge clk) begin
        if (!rstn) begin
            beat_cnt <= 2'd0;
            pix_cnt  <= 4'd0;
            cur      <= 256'd0;
        end else if (beat_clear) begin
            beat_cnt <= 2'd0;
        end else if (we) begin
            if (pix_cnt == 4'd15) begin
                // 本拍 16 个像素：低 240 位已存 0..14，最高 16 位是第 15 个
                if (beat_cnt < 2'd2) begin
                    line_buf[beat_cnt] <= {pix_w, cur[239:0]};
                    beat_cnt <= beat_cnt + 2'd1;
                end else begin
                    overflow <= 1'b1;
                end
                cur     <= 256'd0;
                pix_cnt <= 4'd0;
            end else begin
                cur[{pix_cnt, 4'b0000} +: 16] <= pix_w;
                pix_cnt <= pix_cnt + 4'd1;
            end
            cur_oy <= oy;
            if (pix_cnt == 4'd0) row_x0 <= ox;
            // 第 2 拍（本行最后一拍）落下的那一刻，把整行起始地址锁存
            if (pix_cnt == 4'd15 && beat_cnt == 2'd1)
                addr_lat <= dst_base + oy * WORDS_PER_LINE + ((ox - 16'd31) >> 1);   // 本拍第一个像素的 x
        end
    end

    // ---------------------------------------------------------------- 写命令
    always @(posedge clk) begin
        if (!rstn) begin
            st <= S_IDLE; w_req <= 1'b0; w_addr <= {AW{1'b0}};
            w_beats <= 8'd0; send_beat <= 2'd0;
        end else begin
            case (st)
                S_IDLE: begin
                    if (beat_cnt == 2'd2) begin
                        w_addr  <= addr_lat;
                        w_beats <= 8'd2;
                        w_req   <= 1'b1;
                        st      <= S_CMD;
                    end
                end
                S_CMD: begin
                    if (w_ready) begin
                        w_req <= 1'b0;
                        send_beat <= 2'd0;
                        st <= S_DATA;
                    end
                end
                S_DATA: begin
                    if (w_adv) begin
                        if (send_beat == 2'd1) begin
                            st <= S_IDLE;
                        end else begin
                            send_beat <= send_beat + 2'd1;
                        end
                    end
                end
            endcase
        end
    end

endmodule

`default_nettype wire
