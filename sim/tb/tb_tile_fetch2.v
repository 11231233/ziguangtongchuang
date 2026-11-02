`timescale 1ns / 1ps
// ============================================================================
// tb_tile_fetch2.v — tile_fetch_v2 + tile_ram16 联合验证
//   源图 64×64（值 = {row[7:0], col[7:0]}），读服务端模拟 mem_hub，
//   取完后通过 tile_ram16 的 16bit 口逐像素回读比对。
// ============================================================================
`default_nettype none

module tb_tile_fetch2;
    reg clk = 0, rstn = 0;
    always #5 clk = ~clk;

    reg  [15:0] src [0:4095];

    reg         start = 0;
    reg  [27:0] base_addr = 0;
    reg  [15:0] stride = 32;
    reg  [15:0] u0 = 0, v0 = 0;
    reg  [6:0]  bw = 64, bh = 64;

    wire        r_req, r_ready, r_done, r_valid, r_last;
    wire [27:0] r_addr;
    wire [7:0]  r_beats;
    wire [255:0] r_data;
    wire        we, busy, done;
    wire [7:0]  waddr;
    wire [255:0] wdata;

    reg  [5:0]  row = 0, col = 0;
    wire [15:0] rdata;

    tile_fetch_v2 #(.BW(64), .BH(64), .AW(28)) u_fetch (
        .clk(clk), .rstn(rstn),
        .start(start), .base_addr(base_addr), .stride_words(stride),
        .u0(u0), .v0(v0), .bw(bw), .bh(bh),
        .r_req(r_req), .r_addr(r_addr), .r_beats(r_beats),
        .r_ready(r_ready), .r_done(r_done),
        .r_data(r_data), .r_valid(r_valid), .r_last(r_last),
        .we(we), .waddr(waddr), .wdata(wdata),
        .busy(busy), .done(done)
    );

    tile_ram16 u_ram (
        .clk(clk), .we(we), .waddr(waddr), .wdata(wdata),
        .row(row), .col(col), .rdata(rdata)
    );

    // ---------------- 读服务端（4 拍/行，模拟 256bit 突发） ----------------
    reg        r_ready_r = 0, r_valid_r = 0, r_done_r = 0, r_last_r = 0;
    reg [255:0] r_data_r = 0;
    reg [27:0]  addr_l = 0;
    reg [2:0]   st = 0;
    reg [1:0]   beat = 0;
    integer k;

    assign r_ready = r_ready_r;
    assign r_valid = r_valid_r;
    assign r_done  = r_done_r;
    assign r_last  = r_last_r;
    assign r_data  = r_data_r;

    always @(posedge clk) begin
        r_done_r <= 0;
        case (st)
            3'd0: begin
                r_ready_r <= 1'b1;
                if (r_req && r_ready_r) begin
                    addr_l <= r_addr; beat <= 0; st <= 3'd1;
                end
            end
            3'd1: begin r_ready_r <= 0; st <= 3'd2; end
            3'd2: begin
                for (k = 0; k < 16; k = k + 1)
                    r_data_r[k*16 +: 16] <= src[addr_l*2 + beat*16 + k];
                r_valid_r <= 1'b1; r_last_r <= (beat == 3);
                st <= 3'd3;
            end
            3'd3: begin
                r_valid_r <= 0;
                if (beat == 3) begin r_done_r <= 1'b1; st <= 3'd0; end
                else begin beat <= beat + 1; st <= 3'd2; end
            end
            default: st <= 3'd0;
        endcase
    end

    // ---------------- 比对 ----------------
    integer r, c, errors = 0;
    initial begin
        for (k = 0; k < 4096; k = k + 1) src[k] = {k[11:6], k[5:0]};

        repeat (5) @(posedge clk);
        rstn = 1;
        repeat (2) @(posedge clk);
        @(posedge clk); start <= 1; @(posedge clk); start <= 0;

        while (!busy) @(posedge clk);
        while (busy) @(posedge clk);
        repeat (5) @(posedge clk);

        for (r = 0; r < 64; r = r + 1) begin
            for (c = 0; c < 64; c = c + 1) begin
                @(posedge clk);
                row <= r[5:0]; col <= c[5:0];
                @(posedge clk);
                @(posedge clk);
                if (rdata !== src[r*64 + c]) begin
                    if (errors < 6)
                        $display("TB_FETCH2 MISMATCH (%0d,%0d) got=%04x exp=%04x", r, c, rdata, src[r*64+c]);
                    errors = errors + 1;
                end
            end
        end

        if (errors == 0) $display("TB_FETCH2 PASS: 4096 pixels");
        else             $display("TB_FETCH2 FAIL: %0d", errors);
        $finish;
    end

    initial begin
        #3000000;
        $display("TB_FETCH2 TIMEOUT busy=%b done=%b row=%0d st=%0d bcnt=%0d srvst=%0d beat=%0d rreq=%b rrdy=%b rdone=%b rvalid=%b", busy, done, u_fetch.row, u_fetch.st, u_fetch.bcnt, st, beat, r_req, r_ready, r_done, r_valid);
        $finish;
    end

endmodule

`default_nettype wire
