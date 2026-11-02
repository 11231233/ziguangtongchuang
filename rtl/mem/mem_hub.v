`timescale 1ns / 1ps
// ============================================================================
// mem_hub.v — DDR3 多客户端访问：2 个写客户端 + 2 个读客户端 + 仲裁
//
//   写客户端：相机行写入（高优先级）、矫正结果写回（低）
//   读客户端：显示行读出（高优先级）、矫正源图块读（低）
//
//   仲裁粒度 = 一整条突发命令（1..240 拍）。命令一旦发出不会被抢占，
//   避免把一条 AXI 突发切断。显示读优先级最高，保证不欠载。
//
//   客户端协议：
//     写：c_wreq 拉高直到 c_wready 为 1；随后连续给 c_wbeats 拍 c_wdata，
//         每拍 c_wadv 为 1 表示被取走；完成后 c_wdone 出一拍。
//     读：c_rreq 拉高直到 c_rready 为 1；随后 c_rdata 每拍 c_rvalid=1，
//         末拍 c_rlast=1；整条命令结束 c_rdone 出一拍。
// ============================================================================
`default_nettype none

module mem_hub #(
    parameter integer AW = 28
) (
    input  wire            clk,         // DDR 用户时钟（100MHz）
    input  wire            rstn,

    // ---------------- 写客户端 0（相机，高优先级） ----------------
    input  wire            w0_req,
    input  wire [AW-1:0]   w0_addr,
    input  wire [7:0]      w0_beats,
    output wire            w0_ready,
    output wire            w0_done,
    input  wire [255:0]    w0_data,
    output wire            w0_adv,

    // ---------------- 写客户端 1（矫正写回，低优先级） ----------------
    input  wire            w1_req,
    input  wire [AW-1:0]   w1_addr,
    input  wire [7:0]      w1_beats,
    output wire            w1_ready,
    output wire            w1_done,
    input  wire [255:0]    w1_data,
    output wire            w1_adv,

    // ---------------- 读客户端 0（显示，高优先级） ----------------
    input  wire            r0_req,
    input  wire [AW-1:0]   r0_addr,
    input  wire [7:0]      r0_beats,
    output wire            r0_ready,
    output wire            r0_done,
    output wire [255:0]    r0_data,
    output wire            r0_valid,
    output wire            r0_last,

    // ---------------- 读客户端 1（矫正源图读，低优先级） ----------------
    input  wire            r1_req,
    input  wire [AW-1:0]   r1_addr,
    input  wire [7:0]      r1_beats,
    output wire            r1_ready,
    output wire            r1_done,
    output wire [255:0]    r1_data,
    output wire            r1_valid,
    output wire            r1_last,

    // ---------------- 到 AXI 主机 ----------------
    output wire            m_wr_req,
    output wire [AW-1:0]   m_wr_addr,
    output wire [7:0]      m_wr_beats,
    input  wire            m_wr_ready,
    input  wire            m_wr_done,
    output wire [255:0]    m_wr_data,
    input  wire            m_wr_adv,

    output wire            m_rd_req,
    output wire [AW-1:0]   m_rd_addr,
    output wire [7:0]      m_rd_beats,
    input  wire            m_rd_ready,
    input  wire            m_rd_done,
    input  wire [255:0]    m_rd_data,
    input  wire            m_rd_valid,
    input  wire            m_rd_last
);

    // =======================================================================
    //  写仲裁：w0 优先，其次 w1；占用到 m_wr_done
    // =======================================================================
    reg  w_busy = 1'b0;
    reg  w_grant = 1'b0;
    reg  w_accepted = 1'b0;

    // Bypass the idle arbitration register only while no command is owned.
    // If the master stalls, the sequential grant below reserves the chosen client.
    wire w_selected = w_busy ? w_grant : (!w0_req && w1_req);
    assign m_wr_req   = rstn && (w_busy ? !w_accepted : (w0_req || w1_req));
    assign m_wr_addr  = w_selected ? w1_addr  : w0_addr;
    assign m_wr_beats = w_selected ? w1_beats : w0_beats;
    assign m_wr_data  = w_selected ? w1_data  : w0_data;

    assign w0_ready = m_wr_req && (w_selected == 1'b0) && m_wr_ready;
    assign w1_ready = m_wr_req && (w_selected == 1'b1) && m_wr_ready;
    assign w0_done  = w_busy && (w_grant == 1'b0) && m_wr_done;
    assign w1_done  = w_busy && (w_grant == 1'b1) && m_wr_done;
    assign w0_adv   = w_busy && (w_grant == 1'b0) && m_wr_adv;
    assign w1_adv   = w_busy && (w_grant == 1'b1) && m_wr_adv;

    always @(posedge clk) begin
        if (!rstn) begin
            w_busy     <= 1'b0;
            w_grant    <= 1'b0;
            w_accepted <= 1'b0;
        end else if (!w_busy) begin
            if (w0_req) begin
                w_busy  <= 1'b1;
                w_grant <= 1'b0;
                w_accepted <= m_wr_ready;
            end else if (w1_req) begin
                w_busy  <= 1'b1;
                w_grant <= 1'b1;
                w_accepted <= m_wr_ready;
            end
        end else if (m_wr_done) begin
            w_busy     <= 1'b0;
            w_accepted <= 1'b0;
        end else if (m_wr_req && m_wr_ready) begin
            w_accepted <= 1'b1;
        end
    end

    // =======================================================================
    //  读仲裁：r0 优先，其次 r1；占用到 m_rd_done
    // =======================================================================
    reg  r_busy = 1'b0;
    reg  r_grant = 1'b0;
    reg  r_accepted = 1'b0;

    // Bypass the idle arbitration register only while no command is owned.
    // If the master stalls, the sequential grant below reserves the chosen client.
    wire r_selected = r_busy ? r_grant : (!r0_req && r1_req);
    assign m_rd_req   = rstn && (r_busy ? !r_accepted : (r0_req || r1_req));
    assign m_rd_addr  = r_selected ? r1_addr  : r0_addr;
    assign m_rd_beats = r_selected ? r1_beats : r0_beats;

    assign r0_ready = m_rd_req && (r_selected == 1'b0) && m_rd_ready;
    assign r1_ready = m_rd_req && (r_selected == 1'b1) && m_rd_ready;
    assign r0_done  = r_busy && (r_grant == 1'b0) && m_rd_done;
    assign r1_done  = r_busy && (r_grant == 1'b1) && m_rd_done;

    assign r0_data  = m_rd_data;
    assign r1_data  = m_rd_data;
    assign r0_valid = m_rd_valid && r_busy && (r_grant == 1'b0);
    assign r1_valid = m_rd_valid && r_busy && (r_grant == 1'b1);
    assign r0_last  = m_rd_last;
    assign r1_last  = m_rd_last;

    always @(posedge clk) begin
        if (!rstn) begin
            r_busy     <= 1'b0;
            r_grant    <= 1'b0;
            r_accepted <= 1'b0;
        end else if (!r_busy) begin
            if (r0_req) begin
                r_busy  <= 1'b1;
                r_grant <= 1'b0;
                r_accepted <= m_rd_ready;
            end else if (r1_req) begin
                r_busy  <= 1'b1;
                r_grant <= 1'b1;
                r_accepted <= m_rd_ready;
            end
        end else if (m_rd_done) begin
            r_busy     <= 1'b0;
            r_accepted <= 1'b0;
        end else if (m_rd_req && m_rd_ready) begin
            r_accepted <= 1'b1;
        end
    end

endmodule

`default_nettype wire
