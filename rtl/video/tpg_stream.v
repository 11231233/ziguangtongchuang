`timescale 1ns / 1ps
// ============================================================================
// tpg_stream.v — 测试图案发生器（替代摄像头，走同一条 DDR3→HDMI 通路）
//   输出与 OV5640 采集端相同的接口：vs / de / rgb565，1 像素/时钟。
//   图案：8 段彩条 + 64 像素网格 + 中心十字。
//   用途：摄像头没接/没调通时，先证明“DDR3 帧缓存 + HDMI 输出”链路是好的。
// ============================================================================
`default_nettype none

module tpg_stream #(
    parameter integer H_ACT = 1280,
    parameter integer V_ACT = 720,
    parameter integer H_TOT = 1650,
    parameter integer V_TOT = 750
) (
    input  wire        clk,        // 37.125MHz
    input  wire        rst_n,
    output reg         vs,
    output reg         de,
    output reg  [15:0] rgb565
);

    reg [11:0] hcnt, vcnt;
    reg [11:0] xs, ys;

    always @(posedge clk) begin
        if (!rst_n) begin
            hcnt <= 12'd0;
            vcnt <= 12'd0;
        end else if (hcnt == H_TOT - 1) begin
            hcnt <= 12'd0;
            vcnt <= (vcnt == V_TOT - 1) ? 12'd0 : vcnt + 12'd1;
        end else begin
            hcnt <= hcnt + 12'd1;
        end
    end

    // 与 720p 时序一致：H_SYNC=40, H_BP=220, V_SYNC=5, V_BP=20
    wire h_act = (hcnt >= 12'd260) && (hcnt < 12'd260 + H_ACT);
    wire v_act = (vcnt >= 12'd25 ) && (vcnt < 12'd25  + V_ACT);
    wire de_c  = h_act && v_act;

    always @(posedge clk) begin
        xs <= h_act ? (hcnt - 12'd260) : 12'd0;
        ys <= v_act ? (vcnt - 12'd25 ) : 12'd0;
    end

    // ---- 彩条颜色（8 段）----
    reg [2:0]  bar;
    reg [15:0] bar_rgb;
    always @(*) begin
        bar = xs[11:9];
        case (bar)
            3'd0: bar_rgb = 16'hF800;   // 红
            3'd1: bar_rgb = 16'hFFE0;   // 黄
            3'd2: bar_rgb = 16'h07E0;   // 绿
            3'd3: bar_rgb = 16'h07FF;   // 青
            3'd4: bar_rgb = 16'h001F;   // 蓝
            3'd5: bar_rgb = 16'hF81F;   // 品红
            3'd6: bar_rgb = 16'h0000;   // 黑
            3'd7: bar_rgb = 16'hFFFF;   // 白
            default: bar_rgb = 16'h0000;
        endcase
    end

    wire grid = (xs[5:0] == 6'd0) || (ys[5:0] == 6'd0);
    wire cross_line = ((xs > 12'd636) && (xs < 12'd644)) || ((ys > 12'd356) && (ys < 12'd364));
    wire [15:0] pix_c = cross_line ? 16'hFFFF : (grid ? 16'h0000 : bar_rgb);

    always @(posedge clk) begin
        if (!rst_n) begin
            vs     <= 1'b0;
            de     <= 1'b0;
            rgb565 <= 16'd0;
        end else begin
            vs     <= (vcnt < 12'd5);
            de     <= de_c;
            rgb565 <= pix_c;
        end
    end

endmodule

`default_nettype wire
