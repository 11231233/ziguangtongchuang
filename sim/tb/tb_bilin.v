`timescale 1ns / 1ps
// ============================================================================
// tb_bilin.v — bilinear_2x2 逐向量比对（允许 ±1 LSB）
// ============================================================================
`default_nettype none

module tb_bilin;
    reg clk = 0, rstn = 0;
    always #5 clk = ~clk;

    reg         valid_i = 0;
    reg  [15:0] p00 = 0, p01 = 0, p10 = 0, p11 = 0;
    reg  [7:0]  fu = 0, fv = 0;
    wire        valid_o;
    wire [15:0] rgb_o;

    bilinear_2x2 u_dut (
        .clk(clk), .rstn(rstn),
        .valid_i(valid_i),
        .p00(p00), .p01(p01), .p10(p10), .p11(p11),
        .fu(fu), .fv(fv),
        .valid_o(valid_o), .rgb_o(rgb_o)
    );

    reg [15:0] vp00 [0:511], vp01 [0:511], vp10 [0:511], vp11 [0:511];
    reg [7:0]  vfu  [0:511], vfv  [0:511];
    reg [15:0] vexp [0:511];
    integer n_vec = 0, i, waitcycles, errors = 0, fd, code;

    function [4:0] r5(input [15:0] p); r5 = p[15:11]; endfunction
    function [5:0] g6(input [15:0] p); g6 = p[10:5];  endfunction
    function [4:0] b5(input [15:0] p); b5 = p[4:0];   endfunction

    task automatic check(input [15:0] got, input [15:0] exp, input integer idx);
        integer dr, dg, db;
        begin
            dr = r5(got) - r5(exp); if (dr < 0) dr = -dr;
            dg = g6(got) - g6(exp); if (dg < 0) dg = -dg;
            db = b5(got) - b5(exp); if (db < 0) db = -db;
            if (dr > 1 || dg > 1 || db > 1) begin
                if (errors < 8)
                    $display("TB_BILIN MISMATCH vec=%0d got=%04x exp=%04x (dR%d dG%d dB%d)",
                             idx, got, exp, dr, dg, db);
                errors = errors + 1;
            end
        end
    endtask

    initial begin
        fd = $fopen("sim/out/bilin_vec.txt", "r");
        if (fd == 0) begin $display("TB_BILIN FAIL: 无向量文件"); $finish; end
        while (!$feof(fd) && n_vec < 512) begin
            code = $fscanf(fd, "%h %h %h %h %h %h %h\n",
                           vp00[n_vec], vp01[n_vec], vp10[n_vec], vp11[n_vec],
                           vfu[n_vec], vfv[n_vec], vexp[n_vec]);
            if (code == 7) n_vec = n_vec + 1;
        end
        $fclose(fd);
        $display("TB_BILIN: %0d vectors", n_vec);

        repeat (4) @(posedge clk);
        rstn = 1;
        repeat (2) @(posedge clk);

        for (i = 0; i < n_vec; i = i + 1) begin
            @(posedge clk);
            valid_i <= 1;
            p00 <= vp00[i]; p01 <= vp01[i]; p10 <= vp10[i]; p11 <= vp11[i];
            fu  <= vfu[i];  fv  <= vfv[i];
            @(posedge clk);
            valid_i <= 0;
            waitcycles=0;
            @(negedge clk);
            while(!valid_o && waitcycles<12)begin @(negedge clk);waitcycles=waitcycles+1;end
            if (!valid_o) begin
                $display("TB_BILIN FAIL: no valid_o vec %0d", i);
                errors = errors + 1;
            end else begin
                check(rgb_o, vexp[i], i);
            end
        end

        if (errors == 0) $display("TB_BILIN PASS: %0d vectors (+/-1 LSB)", n_vec);
        else             $display("TB_BILIN FAIL: %0d errors / %0d", errors, n_vec);
        $finish;
    end

endmodule

`default_nettype wire
