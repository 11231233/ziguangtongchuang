`timescale 1ns / 1ps
// ============================================================================
// reset_sync.v — 异步置位、同步释放的复位同步器
//
// 为什么需要它：
//   复位信号经常在 A 时钟域产生、却接到 B 时钟域触发器的同步复位端，
//   这会形成一条真实的跨域时序路径（PDS 报 CLKOUT1 → CLKOUT0 setup 违例），
//   上板则可能出现各触发器退出复位的时间不一致。
//   标准做法：每个时钟域各自做一次“异步拉低、同步释放”。
// ============================================================================
`default_nettype none

module reset_sync (
    input  wire clk,        // 目标时钟域
    input  wire arst_n,     // 异步复位输入（低有效），可以来自任意时钟域
    output wire rst_n       // 同步释放后的复位（低有效）
);
    reg [1:0] sync = 2'b00;
    always @(posedge clk or negedge arst_n) begin
        if (!arst_n) sync <= 2'b00;
        else         sync <= {sync[0], 1'b1};
    end
    assign rst_n = sync[1];
endmodule

`default_nettype wire
