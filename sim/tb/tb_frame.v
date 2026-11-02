`timescale 1ns / 1ps
// ============================================================================
// tb_frame.v — 整帧矫正联合仿真：按 tile 装载包围盒 → warp_tile → 输出整帧
//   输入：sim/out/frame_src.txt（源图 hex）、frame_tiles.vh（包围盒列表）
//   输出：sim/out/frame_out.txt（RTL 矫正结果）
// ============================================================================
`default_nettype none

module tb_frame;
    `include "../out/frame_coef.vh"
    `include "../out/frame_tiles.vh"

    localparam integer OUT_W = 128;
    localparam integer OUT_H = 64;

    reg clk = 0, rstn = 0;
    always #5 clk = ~clk;

    reg  [15:0] src [0:192*96-1];
    reg  [15:0] frame [0:OUT_W*OUT_H-1];
    reg  [15:0] ram [0:4095];

    wire [11:0] raddr;
    reg  [15:0] rdata;
    always @(posedge clk) rdata <= ram[raddr];

    reg  start = 0;
    reg  [15:0] tx = 0, ty = 0, u0 = 0, v0 = 0;
    reg  [5:0]  bw = 64, bh = 64;
    wire we, busy;
    wire [15:0] ox, oy, pix;

    warp_tile u_dut (
        .clk(clk), .rstn(rstn),
        .A(A), .B(B), .C(C), .D(D), .E(E), .F(F),
        .k1(K1), .k2(K2), .p1(P1), .p2(P2),
        .fx(FX), .fy(FY), .cx(CX), .cy(CY),
        .start(start), .tx(tx), .ty(ty), .u0(u0), .v0(v0), .bw(bw), .bh(bh),
        .raddr(raddr), .rdata(rdata),
        .we(we), .ox(ox), .oy(oy), .pix(pix), .busy(busy)
    );

    reg [15:0] tx_a [0:15], ty_a [0:15], u0_a [0:15], v0_a [0:15], bw_a [0:15], bh_a [0:15];
    integer i, r, c, fd, code, n, err;

    initial begin
        // 读源图
        fd = $fopen("sim/out/frame_src.txt", "r");
        for (n = 0; n < 192*96; n = n + 1) begin
            code = $fscanf(fd, "%h", src[n]);
        end
        $fclose(fd);

        for (i = 0; i < OUT_W*OUT_H; i = i + 1) frame[i] = 16'h0000;

        tx_a[0]=T0_TX; ty_a[0]=T0_TY; u0_a[0]=T0_U0; v0_a[0]=T0_V0; bw_a[0]=T0_BW; bh_a[0]=T0_BH;
        tx_a[1]=T1_TX; ty_a[1]=T1_TY; u0_a[1]=T1_U0; v0_a[1]=T1_V0; bw_a[1]=T1_BW; bh_a[1]=T1_BH;
        tx_a[2]=T2_TX; ty_a[2]=T2_TY; u0_a[2]=T2_U0; v0_a[2]=T2_V0; bw_a[2]=T2_BW; bh_a[2]=T2_BH;
        tx_a[3]=T3_TX; ty_a[3]=T3_TY; u0_a[3]=T3_U0; v0_a[3]=T3_V0; bw_a[3]=T3_BW; bh_a[3]=T3_BH;
        tx_a[4]=T4_TX; ty_a[4]=T4_TY; u0_a[4]=T4_U0; v0_a[4]=T4_V0; bw_a[4]=T4_BW; bh_a[4]=T4_BH;
        tx_a[5]=T5_TX; ty_a[5]=T5_TY; u0_a[5]=T5_U0; v0_a[5]=T5_V0; bw_a[5]=T5_BW; bh_a[5]=T5_BH;
        tx_a[6]=T6_TX; ty_a[6]=T6_TY; u0_a[6]=T6_U0; v0_a[6]=T6_V0; bw_a[6]=T6_BW; bh_a[6]=T6_BH;
        tx_a[7]=T7_TX; ty_a[7]=T7_TY; u0_a[7]=T7_U0; v0_a[7]=T7_V0; bw_a[7]=T7_BW; bh_a[7]=T7_BH;

        repeat (5) @(posedge clk);
        rstn = 1;
        repeat (2) @(posedge clk);

        for (i = 0; i < N_TILES; i = i + 1) begin
            // 装载 64×64 窗口（超出包围盒的填 0）
            for (r = 0; r < 4096; r = r + 1) ram[r] = 16'h0000;
            for (r = 0; r < bh_a[i]; r = r + 1)
                for (c = 0; c < bw_a[i]; c = c + 1)
                    ram[r*64 + c] = src[(v0_a[i] + r) * 192 + (u0_a[i] + c)];

            tx <= tx_a[i]; ty <= ty_a[i];
            u0 <= u0_a[i]; v0 <= v0_a[i];
            bw <= bw_a[i]; bh <= bh_a[i];
            @(posedge clk);
            start <= 1;
            @(posedge clk);
            start <= 0;

            while (!busy) @(posedge clk);
            while (busy) begin
                @(posedge clk);
                if (we) frame[oy*OUT_W + ox] = pix;
            end
            repeat (4) @(posedge clk);
        end

        fd = $fopen("sim/out/frame_out.txt", "w");
        for (r = 0; r < OUT_H; r = r + 1) begin
            for (c = 0; c < OUT_W; c = c + 1)
                $fwrite(fd, "%04x ", frame[r*OUT_W + c]);
            $fwrite(fd, "\n");
        end
        $fclose(fd);
        $display("TB_FRAME DONE: %0d tiles", N_TILES);
        $finish;
    end

endmodule

`default_nettype wire
