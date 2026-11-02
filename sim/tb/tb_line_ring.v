`timescale 1ns / 1ps
// ============================================================================
// tb_line_ring.v — 行环形缓冲单元测试
//   写入 64 行 × 64 像素（值 = {row[7:0], x[7:0]}），
//   然后对每行回读全部列，比对内容与 hit 标志。
// ============================================================================
`default_nettype none

module tb_line_ring;
    localparam integer W = 64;
    localparam integer ROWS = 32;

    reg clk = 0, rstn = 0;
    always #5 clk = ~clk;

    reg        wr_en = 0;
    reg [15:0] wr_row = 0, wr_x = 0, wr_pix = 0;
    reg [15:0] rd_u = 0, rd_v = 0;
    wire [15:0] rd_pix;
    wire        rd_hit;
    wire [15:0] ring_wr_row;

    line_ring #(.W(W), .ROWS(ROWS)) u_dut (
        .clk(clk), .rstn(rstn),
        .wr_en(wr_en), .wr_row(wr_row), .wr_x(wr_x), .wr_pix(wr_pix),
        .rd_u(rd_u), .rd_v(rd_v), .rd_pix(rd_pix), .rd_hit(rd_hit),
        .ring_wr_row(ring_wr_row)
    );

    integer r, c, errors = 0;
    reg [15:0] exp;

    initial begin
        repeat (3) @(posedge clk);
        rstn = 1;
        repeat (2) @(posedge clk);

        // ---- 写 64 行 ----
        for (r = 0; r < 64; r = r + 1) begin
            for (c = 0; c < W; c = c + 1) begin
                @(posedge clk);
                wr_en  <= 1;
                wr_row <= r;
                wr_x   <= c;
                wr_pix <= {r[7:0], c[7:0]};
            end
        end
        @(posedge clk);
        wr_en <= 0;
        repeat (2) @(posedge clk);

        // ---- 回读最近 32 行（都应在环内）----
        for (r = 32; r < 64; r = r + 1) begin
            for (c = 0; c < W; c = c + 1) begin
                @(posedge clk);
                rd_u <= c;
                rd_v <= r;
                @(posedge clk);
                @(posedge clk);
                exp = {r[7:0], c[7:0]};
                if (!rd_hit) begin
                    if (errors < 5) $display("TB_RING MISS r=%0d c=%0d (hit=0)", r, c);
                    errors = errors + 1;
                end else if (rd_pix !== exp) begin
                    if (errors < 5) $display("TB_RING DATA r=%0d c=%0d got=%04x exp=%04x", r, c, rd_pix, exp);
                    errors = errors + 1;
                end
            end
        end

        // ---- 回读已淘汰的行（应 hit=0）----
        rd_u <= 0; rd_v <= 0;
        @(posedge clk); @(posedge clk);
        if (rd_hit) begin
            $display("TB_RING FAIL: 已淘汰的行仍报 hit");
            errors = errors + 1;
        end

        if (errors == 0) $display("TB_RING PASS: 64x%0d written, last %0d rows read back", W, ROWS);
        else             $display("TB_RING FAIL: %0d errors", errors);
        $finish;
    end

    initial begin
        #5000000;
        $display("TB_RING TIMEOUT");
        $finish;
    end

endmodule

`default_nettype wire
