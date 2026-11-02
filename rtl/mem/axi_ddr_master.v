`timescale 1ns / 1ps
// ============================================================================
// axi_ddr_master.v — 紫光同创 DDR3 IP 的 AXI 主机（写/读各一套，可并发）
//
// 与厂商 IP 的约定（从 DDR3 IP 例程 + wr_cmd_trans.v 反推并核对）：
//   · 数据位宽 256bit（一次 8 个 32bit 字 = 32 字节）
//   · **地址单位是 32bit 字**，不是字节：一次突发后地址 += beats*8
//   · awlen/arlen 4bit，单次突发最多 16 拍
//   · 写通道没有 wvalid 输入：wready 有效的每个周期 IP 都会吃掉 wdata，
//     所以主机必须在整条命令期间“持续供数”（调用方保证）
//   · 读通道 rready 常 1，调用方必须在命令期间持续接收
//
// 命令接口：
//   写：wr_req（电平）/ wr_addr / wr_beats(1..240)，被接受时 wr_ready 为 1；
//       接受后调用方必须连续给 wr_beats 个 256bit 数据，每拍 wr_dready=1 表示被吃走。
//       整条命令完成后 wr_done 出一拍脉冲。
//   读：rd_req / rd_addr / rd_beats，被接受后数据以 rd_dvalid 流出，
//       最后一拍 rd_dlast=1，整条命令完成后 rd_done 出一拍脉冲。
// ============================================================================
`default_nettype none

module axi_ddr_master #(
    parameter integer AW = 28
) (
    input  wire            clk,
    input  wire            rstn,

    // ---------------- 写命令/数据 ----------------
    input  wire            wr_req,
    input  wire [AW-1:0]   wr_addr,
    input  wire [7:0]      wr_beats,
    output wire            wr_ready,
    output reg             wr_done,
    input  wire [255:0]    wr_data,
    output wire            wr_dready,

    // ---------------- 读命令/数据 ----------------
    input  wire            rd_req,
    input  wire [AW-1:0]   rd_addr,
    input  wire [7:0]      rd_beats,
    output wire            rd_ready,
    output reg             rd_done,
    output wire [255:0]    rd_data,
    output wire            rd_dvalid,
    output wire            rd_dlast,

    // ---------------- 到 DDR3 IP 的 AXI ----------------
    output reg  [AW-1:0]   axi_awaddr,
    output wire [3:0]      axi_awid,
    output reg  [3:0]      axi_awlen,
    output reg             axi_awvalid,
    input  wire            axi_awready,

    output wire [255:0]    axi_wdata,
    output wire [31:0]     axi_wstrb,
    input  wire            axi_wready,
    input  wire            axi_wusero_last,

    output reg  [AW-1:0]   axi_araddr,
    output wire [3:0]      axi_arid,
    output reg  [3:0]      axi_arlen,
    output reg             axi_arvalid,
    input  wire            axi_arready,

    input  wire [255:0]    axi_rdata,
    input  wire            axi_rvalid,
    input  wire            axi_rlast,
    input  wire [3:0]      axi_rid
);

    assign axi_awid  = 4'd0;
    assign axi_arid  = 4'd0;
    assign axi_wdata = wr_data;
    assign axi_wstrb = {32{1'b1}};

    // =======================================================================
    //  写通道
    // =======================================================================
    localparam [1:0] W_IDLE = 2'd0, W_AW = 2'd1, W_DATA = 2'd2, W_DONE = 2'd3;

    reg  [1:0]    wst = W_IDLE;
    reg  [AW-1:0] w_addr;
    reg  [7:0]    w_left;        // 本次命令还剩多少拍
    reg  [4:0]    w_burst;       // 当前突发拍数（1..16）
    reg  [4:0]    w_cnt;         // 当前突发已发拍数
    reg  [7:0]    w_len_calc;

    wire  [7:0]   w_step = {w_burst, 3'b000};   // beats * 8（32bit 字）
    wire  [7:0]   w_left_nxt = w_left - w_burst;

    assign wr_ready  = (wst == W_IDLE);
    assign wr_dready = (wst == W_DATA) && axi_wready;

    always @(*) begin
        w_len_calc = (w_left > 8'd16) ? 8'd16 : w_left;
    end

    always @(posedge clk) begin
        if (!rstn) begin
            wst         <= W_IDLE;
            axi_awvalid <= 1'b0;
            axi_awaddr  <= {AW{1'b0}};
            axi_awlen   <= 4'd0;
            wr_done     <= 1'b0;
            w_addr      <= {AW{1'b0}};
            w_left      <= 8'd0;
            w_burst     <= 5'd1;
            w_cnt       <= 5'd0;
        end else begin
            wr_done <= 1'b0;
            case (wst)
                W_IDLE: begin
                    if (wr_req) begin
                        w_addr      <= wr_addr;
                        w_left      <= wr_beats;
                        axi_awaddr  <= wr_addr;
                        axi_awlen   <= (wr_beats > 8'd16) ? 4'd15 : (wr_beats[3:0] - 4'd1);
                        axi_awvalid <= 1'b1;
                        wst         <= W_AW;
                    end
                end
                W_AW: begin
                    // awlen 与 awaddr 在 awvalid 拉高的同一拍就已经稳定
                    if (axi_awready) begin
                        axi_awvalid <= 1'b0;
                        w_burst     <= w_len_calc[4:0];
                        w_cnt       <= 5'd0;
                        wst         <= W_DATA;
                    end
                end
                W_DATA: begin
                    if (axi_wready) begin
                        if (w_cnt == w_burst - 5'd1) begin
                            w_cnt <= 5'd0;
                            if (w_left <= w_burst) begin
                                wst     <= W_DONE;
                                wr_done <= 1'b1;
                            end else begin
                                w_left      <= w_left - w_burst;
                                w_addr      <= w_addr + w_step;
                                axi_awaddr  <= w_addr + w_step;
                                axi_awlen   <= (w_left_nxt > 8'd16) ? 4'd15
                                                                    : (w_left_nxt[3:0] - 4'd1);
                                axi_awvalid <= 1'b1;
                                wst         <= W_AW;
                            end
                        end else begin
                            w_cnt <= w_cnt + 5'd1;
                        end
                    end
                end
                W_DONE: begin
                    wst <= W_IDLE;
                end
                default: wst <= W_IDLE;
            endcase
        end
    end

    // =======================================================================
    //  读通道
    // =======================================================================
    localparam [1:0] R_IDLE = 2'd0, R_AR = 2'd1, R_DATA = 2'd2;

    reg  [1:0]    rst_rd = R_IDLE;
    reg  [AW-1:0] r_addr;
    reg  [7:0]    r_left;
    reg  [4:0]    r_burst;
    reg  [7:0]    r_len_calc;

    wire  [7:0]   r_step = {r_burst, 3'b000};
    wire  [7:0]   r_left_nxt = r_left - r_burst;

    assign rd_ready  = (rst_rd == R_IDLE);
    assign rd_data   = axi_rdata;
    assign rd_dvalid = axi_rvalid;
    assign rd_dlast  = axi_rlast;

    always @(*) begin
        r_len_calc = (r_left > 8'd16) ? 8'd16 : r_left;
    end

    always @(posedge clk) begin
        if (!rstn) begin
            rst_rd      <= R_IDLE;
            axi_arvalid <= 1'b0;
            axi_araddr  <= {AW{1'b0}};
            axi_arlen   <= 4'd0;
            rd_done     <= 1'b0;
            r_addr      <= {AW{1'b0}};
            r_left      <= 8'd0;
            r_burst     <= 5'd1;
        end else begin
            rd_done <= 1'b0;
            case (rst_rd)
                R_IDLE: begin
                    if (rd_req) begin
                        r_addr      <= rd_addr;
                        r_left      <= rd_beats;
                        axi_araddr  <= rd_addr;
                        axi_arlen   <= (rd_beats > 8'd16) ? 4'd15 : (rd_beats[3:0] - 4'd1);
                        axi_arvalid <= 1'b1;
                        rst_rd      <= R_AR;
                    end
                end
                R_AR: begin
                    if (axi_arready) begin
                        axi_arvalid <= 1'b0;
                        r_burst     <= r_len_calc[4:0];
                        rst_rd      <= R_DATA;
                    end
                end
                R_DATA: begin
                    if (axi_rvalid && axi_rlast) begin
                        if (r_left <= r_burst) begin
                            rd_done <= 1'b1;
                            rst_rd  <= R_IDLE;
                        end else begin
                            r_left      <= r_left - r_burst;
                            r_addr      <= r_addr + r_step;
                            axi_araddr  <= r_addr + r_step;
                            axi_arlen   <= (r_left_nxt > 8'd16) ? 4'd15
                                                                : (r_left_nxt[3:0] - 4'd1);
                            axi_arvalid <= 1'b1;
                            rst_rd      <= R_AR;
                        end
                    end
                end
                default: rst_rd <= R_IDLE;
            endcase
        end
    end

endmodule

`default_nettype wire
