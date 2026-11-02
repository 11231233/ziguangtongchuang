`timescale 1ns / 1ps
// ============================================================================
// tb_out_pack_check.v — 只用于本次排查：验证 out_pack 的两个疑点
//   1) 行 FIFO 的 f_cnt 在没有像素流（we=0）时还能不能减到 0
//   2) oy >= 720 的 tile 行会不会写出本帧范围（写地址 >= 720*640）
// 该文件不参与正式回归，不修改任何 RTL。
// ============================================================================
`default_nettype none

module tb_out_pack_check;
    reg clk = 0, rstn = 0;
    always #5 clk = ~clk;

    reg  [27:0] dst_base = 28'd0;
    reg         we = 0;
    reg  [15:0] ox = 0, oy = 0, pix = 0;
    wire        w_req;
    wire [27:0] w_addr;
    wire [7:0]  w_beats;
    reg         w_ready = 0, w_done = 0, w_adv = 0;
    wire [255:0] w_data;
    wire        ovf;

    out_pack #(.TEST_PAT(0), .AW(28), .WORDS_PER_LINE(640)) dut (
        .clk(clk), .rstn(rstn), .dst_base(dst_base),
        .we(we), .ox(ox), .oy(oy), .pix(pix),
        .w_req(w_req), .w_addr(w_addr), .w_beats(w_beats),
        .w_ready(w_ready), .w_done(w_done), .w_data(w_data), .w_adv(w_adv),
        .overflow(ovf)
    );

    // 模拟 mem_hub 写客户端时序：接受 1 拍 → 2 拍数据 → done
    integer beat = 0;
    reg busy = 0;
    always @(posedge clk) begin
        w_ready <= 1'b0; w_adv <= 1'b0; w_done <= 1'b0;
        if (!busy) begin
            if (w_req) begin
                busy    <= 1'b1;
                w_ready <= 1'b1;
                beat    <= 0;
            end
        end else begin
            w_adv <= 1'b1;
            beat  <= beat + 1;
            if (beat == 1) begin
                busy   <= 1'b0;
                w_done <= 1'b1;
            end
        end
    end

    task do_row(input [15:0] yy);
        integer k;
        begin
            for (k = 0; k < 32; k = k + 1) begin
                @(posedge clk);
                we <= 1'b1; ox <= k[15:0]; oy <= yy; pix <= 16'h1234;
            end
            @(posedge clk);
            we <= 1'b0;
            // 留出足够时间给发送端把这一行发完
            repeat (40) @(posedge clk);
            $display("ROW y=%0d done: f_cnt=%0d f_wp=%0d f_rp=%0d ovf=%b", yy,
                     dut.f_cnt, dut.f_wp, dut.f_rp, ovf);
        end
    endtask

    initial begin
        repeat (5) @(posedge clk);
        rstn = 1;
        repeat (3) @(posedge clk);

        do_row(16'd719);
        do_row(16'd735);

        $display("last_addr=%0d  (720*640 = %0d, 一帧字数 = 460800)", w_addr, 720*640);
        $finish;
    end
endmodule

`default_nettype wire
