`timescale 1ns / 1ps
// ============================================================================
// tile_fetch_v2.v — 把源图包围盒按行读进 256bit 宽的 tile RAM
//
//   与 v1 的区别：不再用“256bit 数据 → 16bit RAM 串行拆写”（那条路径仿真不收敛），
//   而是直接把每个 256bit 拍写成一个 RAM 字，读侧由 tile_ram16 做 16:1 选择。
//
//   地址：base + (v0+row)*stride + u0/2   （单位：32bit 字）
//   每行 beats = bw/16（bw ≤ 64 → ≤4 拍）
//   完成时 done 出一拍。
// ============================================================================
`default_nettype none

module tile_fetch_v2 #(
    parameter integer BW = 64,
    parameter integer BH = 64,
    parameter integer AW = 28,
    parameter integer STRIDE = 640      // 源图每行字数（常量，避免地址路径上的变量乘法）
) (
    input  wire            clk,
    input  wire            rstn,

    input  wire            start,
    input  wire [AW-1:0]   base_addr,
    input  wire [15:0]     stride_words,
    input  wire [15:0]     u0, v0,
    input  wire [6:0]      bw, bh,

    // 读客户端（接 mem_hub r1）
    output reg             r_req,
    output reg  [AW-1:0]   r_addr,
    output wire [7:0]      r_beats,
    input  wire            r_ready,
    input  wire            r_done,
    input  wire [255:0]    r_data,
    input  wire            r_valid,
    input  wire            r_last,

    // 256bit tile RAM 写口
    output reg             we,
    output reg  [7:0]      waddr,        // 行*4 + 行内拍号
    output reg  [255:0]    wdata,

    output reg             busy,
    output reg             done
);

    localparam integer BPR = BW / 16;    // 每行拍数

    reg [1:0] st;
    localparam F_IDLE = 2'd0, F_RUN = 2'd1, F_TAIL = 2'd2;

    reg [15:0] row;
    reg [1:0]  bcnt;                     // 行内第几拍（写地址用）

    assign r_beats = {5'd0, bw[6:4]};    // beats/行 = bw/16（bw≤64 → ≤4）

    always @(posedge clk) begin
        if (!rstn) begin
            st <= F_IDLE; busy <= 1'b0; done <= 1'b0;
            r_req <= 1'b0; r_addr <= {AW{1'b0}};
            row <= 16'd0; bcnt <= 2'd0;
            we <= 1'b0; waddr <= 8'd0; wdata <= 256'd0;
        end else begin
            we   <= 1'b0;
            done <= 1'b0;

            case (st)
                F_IDLE: begin
                    if (start) begin
                        busy    <= 1'b1;
                        row     <= 16'd0;
                        bcnt    <= 2'd0;
                        r_addr  <= base_addr + v0 * stride_words + {1'b0, u0[15:1]};
                        r_req   <= 1'b1;
                        st      <= F_RUN;
                    end
                end

                F_RUN: begin
                    if (r_req && r_ready) r_req <= 1'b0;

                    if (r_valid) begin
                        we    <= 1'b1;
                        waddr <= {row[5:0], bcnt};
                        wdata <= r_data;
                        bcnt  <= bcnt + 2'd1;
                    end

                    if (r_done) begin
                        bcnt <= 2'd0;
                        if (row == bh - 16'd1) begin
                            st <= F_TAIL;
                        end else begin
                            row    <= row + 16'd1;
                            r_addr <= r_addr + stride_words;
                            r_req  <= 1'b1;
                        end
                    end
                end

                F_TAIL: begin
                    busy <= 1'b0;
                    done <= 1'b1;
                    st   <= F_IDLE;
                end

                default: st <= F_IDLE;
            endcase
        end
    end

endmodule

`default_nettype wire
