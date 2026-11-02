`timescale 1ns / 1ps
// ============================================================================
// tb_warp_frame.v — 整帧矫正调度联调仿真
//
//   源帧 192×96（sim/out/frame_src.txt，由 tools/gen_frame_test.py 生成）
//   输出 128×64，分 4×2 个 32×32 块
//   读服务端模拟 mem_hub r1；写侧把 out_pack 的突发写进 dst 数组
//   最后与 sim/out/frame_expect.txt 比对
// ============================================================================
`default_nettype none

module tb_warp_frame;
    `include "../out/frame_coef.vh"

    localparam integer OUT_W = 128;
    localparam integer OUT_H = 64;
    localparam integer SRC_W = 192;
    localparam integer SRC_H = 96;
    localparam integer SRC_STRIDE = SRC_W / 2;      // 96 字/行
    localparam integer WORDS_LINE = OUT_W / 2;      // 64 字/行
    localparam [27:0]  DST_BASE = 28'd20000;

    reg clk = 0, rstn = 0;
    always #5 clk = ~clk;

    reg  [15:0] src [0:SRC_W*SRC_H-1];
    reg  [15:0] dst [0:OUT_W*OUT_H-1];
    integer i, n, fd, code, err;

    reg         start = 0;
    wire        busy, done, ovf;

    wire        r_req, r_ready, r_done, r_valid, r_last;
    wire [27:0] r_addr;
    wire [7:0]  r_beats;
    wire [255:0] r_data;

    wire        w_req, w_ready, w_done, w_adv;
    wire [27:0] w_addr;
    wire [7:0]  w_beats;
    wire [255:0] w_data;

    warp_frame #(.AW(28), .COLS(OUT_W/32), .ROWS(OUT_H/32),
                 .WORDS_PER_LINE(WORDS_LINE), .SRC_STRIDE(SRC_STRIDE)) u_dut (
        .clk(clk), .rstn(rstn),
        .A(A), .B(B), .C(C), .D(D), .E(E), .F(F),
        .k1(K1), .k2(K2), .p1(P1), .p2(P2),
        .fx(FX), .fy(FY), .cx(CX), .cy(CY),
        .src_base(28'd0), .dst_base(DST_BASE),
        .start(start), .busy(busy), .done(done),
        .r_req(r_req), .r_addr(r_addr), .r_beats(r_beats),
        .r_ready(r_ready), .r_done(r_done),
        .r_data(r_data), .r_valid(r_valid), .r_last(r_last),
        .w_req(w_req), .w_addr(w_addr), .w_beats(w_beats),
        .w_ready(w_ready), .w_done(w_done), .w_data(w_data), .w_adv(w_adv),
        .overflow(ovf)
    );

    // ---------------- 读服务端 ----------------
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
                if (r_req && r_ready_r) begin addr_l <= r_addr; beat <= 0; st <= 3'd1; end
            end
            3'd1: begin r_ready_r <= 0; st <= 3'd2; end
            3'd2: begin
                for (k = 0; k < 16; k = k + 1)
                    r_data_r[k*16 +: 16] <= src[addr_l*2 + beat*16 + k];
                r_valid_r <= 1; r_last_r <= (beat == r_beats[1:0] - 1);
                st <= 3'd3;
            end
            3'd3: begin
                r_valid_r <= 0;
                if (beat == r_beats[1:0] - 1) begin r_done_r <= 1; st <= 3'd0; end
                else begin beat <= beat + 1; st <= 3'd2; end
            end
            default: st <= 3'd0;
        endcase
    end

    // ---------------- 写侧：突发写入 dst ----------------
    reg        w_ready_r = 1, w_done_r = 0;
    reg [1:0]  wbeat = 0;
    reg [27:0] waddr_l = 0;
    assign w_ready = w_ready_r;
    assign w_done  = w_done_r;
    assign w_adv   = 1'b1;      // 总是接受数据

    always @(posedge clk) begin
        w_done_r <= 0;
        if (w_req && w_ready_r) begin
            waddr_l <= w_addr;
            wbeat   <= 0;
            w_ready_r <= 0;
        end else if (!w_ready_r) begin
            // 吃两拍
            for (k = 0; k < 16; k = k + 1)
                dst[(waddr_l - DST_BASE)*2 + wbeat*16 + k] <= w_data[k*16 +: 16];
            if (wbeat == 1) begin
                w_ready_r <= 1;
                w_done_r  <= 1;
                wbeat     <= 0;
            end else wbeat <= wbeat + 1;
        end
    end

    // ---------------- 比对 ----------------
    reg [15:0] exp;
    initial begin
        for (i = 0; i < SRC_W*SRC_H; i = i + 1) src[i] = 16'h0000;
        fd = $fopen("sim/out/frame_src.txt", "r");
        for (i = 0; i < SRC_W*SRC_H; i = i + 1) code = $fscanf(fd, "%h", src[i]);
        $fclose(fd);

        repeat (5) @(posedge clk);
        rstn = 1;
        repeat (2) @(posedge clk);
        @(posedge clk); start <= 1; @(posedge clk); start <= 0;

        i = 0;
        while (!busy && i < 1000) begin @(posedge clk); i = i + 1; end
        i = 0;
        while (busy && i < 2000000) begin @(posedge clk); i = i + 1; end
        repeat (20) @(posedge clk);

        fd = $fopen("sim/out/frame_dut.txt", "w");
        for (i = 0; i < OUT_H; i = i + 1) begin
            for (n = 0; n < OUT_W; n = n + 1)
                $fwrite(fd, "%04x ", dst[i*OUT_W + n]);
            $fwrite(fd, "\n");
        end
        $fclose(fd);
        $display("TB_WARP_FRAME DONE: busy=%b done=%b cycles=%0d ovf=%b", busy, done, i, ovf);
        $finish;
    end

    integer tick = 0;
    always @(posedge clk) begin
        tick = tick + 1;
        if (tick % 200000 == 0)
            $display("DBG st=%0d frow=%0d fbcnt=%0d fst=%0d fb=%b fd=%b rreq=%b rrdy=%b rv=%b rdn=%b srvst=%0d beat=%0d",
                     u_dut.st, u_dut.u_fetch.row, u_dut.u_fetch.bcnt, u_dut.u_fetch.st,
                     u_dut.f_busy, u_dut.f_done, r_req, r_ready, r_valid, r_done, st, beat);
    end

    initial begin
        #20000000;
        $display("TB_WARP_FRAME TIMEOUT busy=%b done=%b", busy, done);
        $finish;
    end

endmodule

`default_nettype wire
