`timescale 1ns / 1ps
// ============================================================================
// tb_tile_fetch.v — tile_fetch 单元测试：64×64 源图按包围盒搬进 tile RAM
// ============================================================================
`default_nettype none

module tb_tile_fetch;
    reg clk = 0, rstn = 0;
    always #5 clk = ~clk;

    reg  [15:0] src [0:4095];      // 源图像素（64×64）
    reg  [15:0] ram [0:4095];      // tile RAM 模型

    reg         start = 0;
    reg  [27:0] base_addr = 0;
    reg  [15:0] stride = 32;
    reg  [15:0] u0 = 0, v0 = 0;
    reg  [5:0]  bw = 64, bh = 64;

    wire        r_req, r_ready, r_done, r_valid, r_last;
    wire [27:0] r_addr;
    wire [7:0]  r_beats;
    wire [255:0] r_data;
    wire        we, busy, done;
    wire [11:0] waddr;
    wire [15:0] wdata;

    // tile RAM 模型
    always @(posedge clk) if (we) ram[waddr] <= wdata;

    tile_fetch #(.BW(64), .BH(64), .AW(28)) u_dut (
        .clk(clk), .rstn(rstn),
        .start(start), .base_addr(base_addr), .stride_words(stride),
        .u0(u0), .v0(v0), .bw(bw), .bh(bh),
        .r_req(r_req), .r_addr(r_addr), .r_beats(r_beats),
        .r_ready(r_ready), .r_done(r_done),
        .r_data(r_data), .r_valid(r_valid), .r_last(r_last),
        .we(we), .waddr(waddr), .wdata(wdata),
        .busy(busy), .done(done)
    );

    // ---------------- 读服务端：模拟 mem_hub r1 ----------------
    reg        r_ready_r = 0;
    reg        r_valid_r = 0, r_done_r = 0, r_last_r = 0;
    reg [255:0] r_data_r = 0;
    reg [27:0]  addr_l = 0;
    reg [3:0]   bcnt = 0;
    reg [2:0]   st = 0;

    assign r_ready = r_ready_r;
    assign r_valid = r_valid_r;
    assign r_done  = r_done_r;
    assign r_last  = r_last_r;
    assign r_data  = r_data_r;

    integer k;
    always @(posedge clk) begin
        r_done_r <= 0;
        case (st)
            3'd0: begin
                r_ready_r <= 1'b1;
                if (r_req && r_ready_r) begin
                    addr_l <= r_addr;
                    st <= 3'd1; bcnt <= 0;
                end
            end
            3'd1: begin
                r_ready_r <= 0; st <= 3'd2;
            end
            3'd2: begin
                // 组一拍 256bit = 16 像素
                for (k = 0; k < 16; k = k + 1)
                    r_data_r[k*16 +: 16] <= src[addr_l*2 + bcnt*16 + k];
                r_valid_r <= 1'b1;
                r_last_r  <= (bcnt == 3);
                st <= 3'd3;
            end
            3'd3: begin
                r_valid_r <= 0;
                if (bcnt == 3) begin
                    r_done_r <= 1'b1;
                    st <= 3'd0;
                end else begin
                    bcnt <= bcnt + 1;
                    st <= 3'd2;
                end
            end
            default: st <= 3'd0;
        endcase
    end

    // ---------------- 比对 ----------------
    integer i, errors = 0;
    initial begin
        for (i = 0; i < 4096; i = i + 1) begin
            src[i] = i[15:0] ^ 16'h5A5A;
            ram[i] = 16'hDEAD;
        end

        repeat (5) @(posedge clk);
        rstn = 1;
        repeat (2) @(posedge clk);
        @(posedge clk);
        start <= 1;
        @(posedge clk);
        start <= 0;

        i = 0;
        while (!busy && i < 1000) begin @(posedge clk); i = i + 1; end
        i = 0;
        while (busy && i < 20000) begin @(posedge clk); i = i + 1; end
        repeat (10) @(posedge clk);

        for (i = 0; i < 4096; i = i + 1) begin
            if (ram[i] !== src[i]) begin
                if (errors < 6) $display("TB_FETCH MISMATCH [%0d] ram=%04x src=%04x", i, ram[i], src[i]);
                errors = errors + 1;
            end
        end
        if (errors == 0) $display("TB_FETCH PASS: 4096 pixels moved");
        else             $display("TB_FETCH FAIL: %0d mismatches", errors);
        $finish;
    end

    initial begin
        #2000000;
        $display("TB_FETCH TIMEOUT busy=%b done=%b", busy, done);
        $finish;
    end

endmodule

`default_nettype wire
