`timescale 1ns / 1ps
// ============================================================================
// axi_mem_model.v — DDR3 IP 的 AXI 从机行为模型（仅用于仿真）
//   行为约定与 IQ 主机一致：地址单位 32bit 字，一次突发 8 字/拍，
//   awlen/arlen = 拍数-1，wready 常 1，读延迟固定。
// ============================================================================
`default_nettype none

module axi_mem_model #(
    parameter integer AW        = 28,
    parameter integer MEM_WORDS = 1 << 16,   // 256K 字 = 1MB
    parameter integer RD_LAT    = 8
) (
    input  wire            clk,
    input  wire            rstn,

    input  wire [AW-1:0]   axi_awaddr,
    input  wire [3:0]      axi_awlen,
    input  wire            axi_awvalid,
    output reg             axi_awready,
    input  wire [255:0]    axi_wdata,
    output wire            axi_wready,

    input  wire [AW-1:0]   axi_araddr,
    input  wire [3:0]      axi_arlen,
    input  wire            axi_arvalid,
    output reg             axi_arready,
    output reg  [255:0]    axi_rdata,
    output reg             axi_rvalid,
    output reg             axi_rlast,
    input  wire            axi_rready
);

    reg [31:0] mem [0:MEM_WORDS-1];

    assign axi_wready = 1'b1;

    // ---------------- 写 ----------------
    reg        w_active = 1'b0;
    reg [AW-1:0] w_addr;
    reg [3:0]  w_left;

    always @(posedge clk) begin
        if (!rstn) begin
            axi_awready <= 1'b1;
            w_active    <= 1'b0;
            w_addr      <= {AW{1'b0}};
            w_left      <= 4'd0;
        end else begin
            if (!w_active) begin
                axi_awready <= 1'b1;
                if (axi_awvalid) begin
                    axi_awready <= 1'b0;
                    w_addr      <= axi_awaddr;
                    w_left      <= axi_awlen;
                    w_active    <= 1'b1;
                end
            end else begin
                // 每拍吃 8 个 32bit 字
                begin : wr_beat
                    integer i;
                    for (i = 0; i < 8; i = i + 1)
                        mem[w_addr[AW-1:0] + i] = axi_wdata[i*32 +: 32];
                end
                w_addr <= w_addr + 8;
                if (w_left == 4'd0) begin
                    w_active    <= 1'b0;
                    axi_awready <= 1'b1;
                end else begin
                    w_left <= w_left - 4'd1;
                end
            end
        end
    end

    // ---------------- 读 ----------------
    reg        r_active = 1'b0;
    reg [AW-1:0] r_addr;
    reg [3:0]  r_left;
    reg [7:0]  r_wait = 8'd0;

    always @(posedge clk) begin
        if (!rstn) begin
            axi_arready <= 1'b1;
            r_active    <= 1'b0;
            axi_rvalid  <= 1'b0;
            axi_rlast   <= 1'b0;
            axi_rdata   <= 256'd0;
            r_wait      <= 8'd0;
        end else begin
            if (!r_active) begin
                axi_arready <= 1'b1;
                axi_rvalid  <= 1'b0;
                axi_rlast   <= 1'b0;
                if (axi_arvalid) begin
                    axi_arready <= 1'b0;
                    r_addr      <= axi_araddr;
                    r_left      <= axi_arlen;
                    r_active    <= 1'b1;
                    r_wait      <= RD_LAT[7:0];
                end
            end else if (r_wait != 8'd0) begin
                r_wait <= r_wait - 8'd1;
            end else begin
                axi_rvalid <= 1'b1;
                axi_rlast  <= (r_left == 4'd0);
                begin : rd_beat
                    integer i;
                    for (i = 0; i < 8; i = i + 1)
                        axi_rdata[i*32 +: 32] = mem[r_addr[AW-1:0] + i];
                end
                r_addr <= r_addr + 8;
                if (r_left == 4'd0) begin
                    r_active    <= 1'b0;
                    axi_rvalid  <= 1'b1;   // 最后一拍
                    axi_arready <= 1'b1;
                end else begin
                    r_left <= r_left - 4'd1;
                end
            end
        end
    end

endmodule

`default_nettype wire
