`timescale 1ns / 1ps
// ============================================================================
// tb_coord.v — coord_map 与 Python 黄金模型的定点比对
//   向量文件：+VEC=sim/out/coord_vec.txt，每行 "x y u_q16 v_q16"（十六进制）
//   系数文件：+COEF=sim/out/coord_coef.txt（14 行 Q16 十六进制）
//   不给 plusargs 时使用默认 base 用例，保持原 30 项回归入口不变。
// ============================================================================
`default_nettype none

module tb_coord;
    // Coefficients and vectors are runtime files so one testbench can sweep
    // several calibrations/angles. Defaults keep the original regression call.
    reg [31:0] cf [0:13];
    reg [1023:0] coef_file, vec_file;
    wire signed [31:0] A = cf[0];
    wire signed [31:0] B = cf[1];
    wire signed [31:0] C = cf[2];
    wire signed [31:0] D = cf[3];
    wire signed [31:0] E = cf[4];
    wire signed [31:0] F = cf[5];
    wire signed [31:0] K1 = cf[6];
    wire signed [31:0] K2 = cf[7];
    wire signed [31:0] P1 = cf[8];
    wire signed [31:0] P2 = cf[9];
    wire signed [31:0] FX = cf[10];
    wire signed [31:0] FY = cf[11];
    wire signed [31:0] CX = cf[12];
    wire signed [31:0] CY = cf[13];

    reg clk = 0, rstn = 0;
    always #5 clk = ~clk;

    reg         valid_i = 0;
    reg  [15:0] x_i = 0, y_i = 0;
    wire        valid_o, in_frame;
    wire signed [31:0] u_q16, v_q16;
    wire [15:0] u_int, v_int;
    wire [7:0]  u_frac, v_frac;

    coord_map u_dut (
        .clk(clk), .rstn(rstn),
        .A(A), .B(B), .C(C), .D(D), .E(E), .F(F),
        .k1(K1), .k2(K2), .p1(P1), .p2(P2),
        .fx(FX), .fy(FY), .cx(CX), .cy(CY),
        .valid_i(valid_i), .x_i(x_i), .y_i(y_i),
        .valid_o(valid_o), .u_q16(u_q16), .v_q16(v_q16),
        .in_frame(in_frame), .u_int(u_int), .v_int(v_int),
        .u_frac(u_frac), .v_frac(v_frac)
    );

    // 向量存储
    reg [15:0] vx  [0:4095];
    reg [15:0] vy  [0:4095];
    reg [31:0] vu  [0:4095];
    reg [31:0] vv  [0:4095];
    integer n_vec = 0;

    integer i, errors = 0;
    integer fd, code, n;

    initial begin
        if (!$value$plusargs("COEF=%s", coef_file)) coef_file = "sim/out/coord_coef.txt";
        if (!$value$plusargs("VEC=%s", vec_file)) vec_file = "sim/out/coord_vec.txt";
        $readmemh(coef_file, cf);
        // 读取向量（每行 4 个 hex）
        fd = $fopen(vec_file, "r");
        if (fd == 0) begin
            $display("TB_COORD FAIL: 打不开向量文件");
            $finish;
        end
        while (!$feof(fd) && n_vec < 4096) begin
            code = $fscanf(fd, "%h %h %h %h\n", vx[n_vec], vy[n_vec], vu[n_vec], vv[n_vec]);
            if (code == 4) n_vec = n_vec + 1;
        end
        $fclose(fd);
        $display("TB_COORD: %0d vectors  A=%0d C=%0d FX=%0d CX=%0d", n_vec, A, C, FX, CX);

        repeat (5) @(posedge clk);
        rstn = 1;
        repeat (3) @(negedge clk);

        for (i = 0; i < n_vec; i = i + 1) begin
            @(negedge clk);
            valid_i <= 1;
            x_i <= vx[i];
            y_i <= vy[i];
            // 固定 8 拍流水延迟后采样
            @(negedge clk);valid_i=0;
            n=0;
            while(!valid_o && n<100) begin @(negedge clk);n=n+1;end
            if (!valid_o) begin
                $display("TB_COORD FAIL: no valid_o at vec %0d", i);
                errors = errors + 1;
            end else begin
                // 允许 ±0.125 像素（Q16.16 下 0x2000）
                if (($signed(u_q16) - $signed(vu[i]) > 32'sd8192) ||
                    ($signed(vu[i]) - $signed(u_q16) > 32'sd8192) ||
                    ($signed(v_q16) - $signed(vv[i]) > 32'sd8192) ||
                    ($signed(vv[i]) - $signed(v_q16) > 32'sd8192)) begin
                    if (errors < 10)
                        $display("TB_COORD MISMATCH vec=%0d xy=(%0d,%0d) got=(%0d,%0d) exp=(%0d,%0d) (q16)",
                                 i, vx[i], vy[i], u_q16, v_q16, vu[i], vv[i]);
                    errors = errors + 1;
                end
            end
            if(u_frac!==u_q16[15:8] || v_frac!==v_q16[15:8]) errors=errors+1;
            @(negedge clk);
        end

        if (errors == 0) $display("TB_COORD PASS: %0d vectors within +/-0.125px", n_vec);
        else             $display("TB_COORD FAIL: %0d errors / %0d", errors, n_vec);
        $finish;
    end

endmodule

`default_nettype wire

