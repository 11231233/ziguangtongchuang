`timescale 1ns / 1ps
// ============================================================================
// tb_warp_tile.v — warp_tile 单元测试：恒等映射，源图内容 = {v[7:0],u[7:0]}
//   输出块 (0,0) 的 32×32 像素必须与源图逐像素一致。
// ============================================================================
`default_nettype none

module tb_warp_tile;
    reg clk = 0, rstn = 0;
    always #5 clk = ~clk;

    // 源图：64×64
    reg [15:0] mem [0:4095];
    wire [11:0] raddr;
    reg  [15:0] rdata;
    reg [15:0] rq;
always @(posedge clk) begin rq <= mem[raddr]; rdata <= rq; end   // 2 拍延迟，匹配流水后的读口

    reg  start = 0;
    wire we, busy;
    wire [15:0] ox, oy, pix;

    warp_tile u_dut (
        .clk(clk), .rstn(rstn),
        .A(32'sd8192), .B(32'sd0), .C(32'sd0),
        .D(32'sd0), .E(32'sd8192), .F(32'sd0),
        .k1(32'sd0), .k2(32'sd0), .p1(32'sd0), .p2(32'sd0),
        .fx(32'sd524288), .fy(32'sd524288), .cx(32'sd0), .cy(32'sd0),
        .start(start), .tx(16'd0), .ty(16'd0), .u0(16'd0), .v0(16'd0),
        .bw(7'd64), .bh(7'd64),
        .raddr(raddr), .rdata(rdata),
        .we(we), .ox(ox), .oy(oy), .pix(pix), .busy(busy)
    );

    integer i, x, y, errors = 0, got = 0;
    reg [15:0] exp;

    initial begin
        for (i = 0; i < 4096; i = i + 1)
            mem[i] = {i[11:6], i[5:0]};          // {v, u}

        repeat (5) @(posedge clk);
        rstn = 1;
        repeat (2) @(posedge clk);

        @(posedge clk);
        start <= 1;
        @(posedge clk);
        start <= 0;

        while (!busy) @(posedge clk);
        while (busy) begin
            @(posedge clk);
            if (we) begin
                exp = {oy[5:0], ox[5:0]};
                // 边界列/行：u+1 会跨到测试图案的下一行（u=32 溢出到 G 域），
                // 期望值不再是恒等映射，这里只校验 tile 内部像素。
                if (pix !== exp) begin
                    if (errors < 8)
                        $display("TB_TILE MISMATCH (%0d,%0d) got=%04x exp=%04x cl=(%0d,%0d) r=(%0d,%0d)", ox, oy, pix, exp, u_dut.cl_u, u_dut.cl_v, u_dut.ru, u_dut.rv);
                    errors = errors + 1;
                end
                got = got + 1;
            end
        end
        // 收尾：忙于下降沿时可能还有最后一拍输出
        repeat (5) @(posedge clk);

        if (got != 1024) begin
            $display("TB_TILE FAIL: 输出像素数 %0d != 1024", got);
            errors = errors + 1;
        end
        if (errors == 0) $display("TB_TILE PASS: 1024 pixels identical");
        else             $display("TB_TILE FAIL: %0d errors, %0d pixels", errors, got);
        $finish;
    end

    initial begin
        #20000000;
        $display("TB_TILE TIMEOUT (got=%0d busy=%b)", got, busy);
        $finish;
    end

endmodule

`default_nettype wire
