`timescale 1ns / 1ps
// ============================================================================
// tb_mem.v — M2 存储通路仿真：源(256×8) → frame_writer → mem_hub → DDR 模型
//           → disp_reader → 显示像素，逐像素比对。
// ============================================================================
`default_nettype none

module tb_mem;
    localparam integer H_ACT = 256;
    localparam integer V_ACT = 8;
    localparam integer V_OFF = 2;
    localparam integer AW    = 28;

    reg src_clk = 0, ddr_clk = 0, pix_clk = 0, rstn = 0;
    always #13.5 src_clk = ~src_clk;   // 37MHz
    always #5.0  ddr_clk = ~ddr_clk;   // 100MHz
    always #13.5 pix_clk = ~pix_clk;

    // ---------------- 源 ----------------
    reg         src_vs = 0, src_de = 0;
    reg  [15:0] src_pix = 0;
    integer     sx, sy;

    // ---------------- 显示时序 ----------------
    reg  vs = 0, hs = 0, de = 0;
    wire [15:0] disp_pix;

    // ---------------- hub ----------------
    wire        m_wr_req, m_wr_ready, m_wr_done, m_wr_adv;
    wire [AW-1:0] m_wr_addr;
    wire [7:0]  m_wr_beats;
    wire [255:0] m_wr_data;
    wire        m_rd_req, m_rd_ready, m_rd_done, m_rd_valid, m_rd_last;
    wire [AW-1:0] m_rd_addr;
    wire [7:0]  m_rd_beats;
    wire [255:0] m_rd_data;

    wire awvalid, awready, arvalid, arready, rvalid, rlast;
    wire [AW-1:0] awaddr, araddr;
    wire [3:0]  awlen, arlen;
    wire [255:0] wdata, rdata;

    // frame_writer 客户端
    wire        fw_req, fw_ready, fw_done, fw_adv;
    wire [AW-1:0] fw_addr;
    wire [7:0]  fw_beats;
    wire [255:0] fw_data;
    wire        fw_ovf;

    // disp_reader 客户端
    wire        dr_req, dr_ready, dr_done, dr_valid, dr_last;
    wire [AW-1:0] dr_addr;
    wire [7:0]  dr_beats;
    wire [255:0] dr_data;
    wire        dr_underrun;

    frame_writer #(.H_ACT(H_ACT),.V_ACT(V_ACT), .AW(AW), .FRAME_BASE(0), .SLOT_WORDS(0)) u_fw (
        .src_clk(src_clk), .src_rstn(rstn),
        .src_vs(src_vs), .src_de(src_de), .src_pix(src_pix),
        .ddr_clk(ddr_clk), .ddr_rstn(rstn),
        .w_req(fw_req), .w_addr(fw_addr), .w_beats(fw_beats),
        .w_ready(fw_ready), .w_done(fw_done), .w_data(fw_data), .w_adv(fw_adv),
        .led_overflow(fw_ovf),.hold_valid(1'b0),.hold_slot(3'd0)
    );

    disp_reader #(.H_ACT(H_ACT), .V_ACT(V_ACT), .V_OFFSET(V_OFF), .AW(AW), .FRAME_BASE(0), .SLOT_WORDS(0), .FLIP_V(0)) u_dr (
        .pix_clk(pix_clk), .pix_rstn(rstn),
        .vs(vs), .hs(hs), .de(de), .pix_out(disp_pix),
        .wr_slot(1'b1),.frame_valid(1'b1),.line_start(1'b0),.line_y(10'd0),
        .ddr_clk(ddr_clk), .ddr_rstn(rstn),
        .r_req(dr_req), .r_addr(dr_addr), .r_beats(dr_beats),
        .r_ready(dr_ready), .r_done(dr_done),
        .r_data(dr_data), .r_valid(dr_valid), .r_last(dr_last),
        .led_underrun(dr_underrun)
    );

    mem_hub #(.AW(AW)) u_hub (
        .clk(ddr_clk), .rstn(rstn),
        .w0_req(fw_req), .w0_addr(fw_addr), .w0_beats(fw_beats),
        .w0_ready(fw_ready), .w0_done(fw_done), .w0_data(fw_data), .w0_adv(fw_adv),
        .w1_req(1'b0), .w1_addr({AW{1'b0}}), .w1_beats(8'd0),
        .w1_ready(), .w1_done(), .w1_data(256'd0), .w1_adv(),
        .r0_req(dr_req), .r0_addr(dr_addr), .r0_beats(dr_beats),
        .r0_ready(dr_ready), .r0_done(dr_done),
        .r0_data(dr_data), .r0_valid(dr_valid), .r0_last(dr_last),
        .r1_req(1'b0), .r1_addr({AW{1'b0}}), .r1_beats(8'd0),
        .r1_ready(), .r1_done(), .r1_data(), .r1_valid(), .r1_last(),
        .m_wr_req(m_wr_req), .m_wr_addr(m_wr_addr), .m_wr_beats(m_wr_beats),
        .m_wr_ready(m_wr_ready), .m_wr_done(m_wr_done), .m_wr_data(m_wr_data), .m_wr_adv(m_wr_adv),
        .m_rd_req(m_rd_req), .m_rd_addr(m_rd_addr), .m_rd_beats(m_rd_beats),
        .m_rd_ready(m_rd_ready), .m_rd_done(m_rd_done),
        .m_rd_data(m_rd_data), .m_rd_valid(m_rd_valid), .m_rd_last(m_rd_last)
    );

    axi_ddr_master #(.AW(AW)) u_axi (
        .clk(ddr_clk), .rstn(rstn),
        .wr_req(m_wr_req), .wr_addr(m_wr_addr), .wr_beats(m_wr_beats),
        .wr_ready(m_wr_ready), .wr_done(m_wr_done), .wr_data(m_wr_data), .wr_dready(m_wr_adv),
        .rd_req(m_rd_req), .rd_addr(m_rd_addr), .rd_beats(m_rd_beats),
        .rd_ready(m_rd_ready), .rd_done(m_rd_done),
        .rd_data(m_rd_data), .rd_dvalid(m_rd_valid), .rd_dlast(m_rd_last),
        .axi_awaddr(awaddr), .axi_awid(), .axi_awlen(awlen), .axi_awvalid(awvalid), .axi_awready(awready),
        .axi_wdata(wdata), .axi_wstrb(), .axi_wready(1'b1), .axi_wusero_last(1'b0),
        .axi_araddr(araddr), .axi_arid(), .axi_arlen(arlen), .axi_arvalid(arvalid), .axi_arready(arready),
        .axi_rdata(rdata), .axi_rvalid(rvalid), .axi_rlast(rlast), .axi_rid(4'd0)
    );

    axi_mem_model #(.AW(AW), .MEM_WORDS(1<<16), .RD_LAT(6)) u_mem (
        .clk(ddr_clk), .rstn(rstn),
        .axi_awaddr(awaddr), .axi_awlen(awlen), .axi_awvalid(awvalid), .axi_awready(awready),
        .axi_wdata(wdata), .axi_wready(),
        .axi_araddr(araddr), .axi_arlen(arlen), .axi_arvalid(arvalid), .axi_arready(arready),
        .axi_rdata(rdata), .axi_rvalid(rvalid), .axi_rlast(rlast), .axi_rready(1'b1)
    );

    // ====================== 统计 ======================
    integer errors = 0;
    integer de_d = 0;
    integer lx = 0, li = 0;
    reg [15:0] exp_pix;

    always @(posedge pix_clk) de_d <= de;

    always @(posedge pix_clk) begin
        if (de_d) begin
            exp_pix = {li[7:0], lx[7:0]};
            if (disp_pix !== exp_pix) begin
                if (errors < 10)
                    $display("MISMATCH line=%0d x=%0d got=%04x exp=%04x", li, lx, disp_pix, exp_pix);
                errors = errors + 1;
            end
            lx = lx + 1;
            if (lx == H_ACT) begin
                lx = 0;
                li = li + 1;
            end
        end
    end


    // ====================== 激励 ======================
    integer i, j;
    initial begin
        rstn = 0;
        repeat (10) @(posedge pix_clk);
        rstn = 1;

        // ---- 源：写 V_ACT 行 ----
        @(posedge src_clk);
        src_vs <= 1;
        repeat (H_ACT) @(posedge src_clk);
        src_vs <= 0;
        repeat (20) @(posedge src_clk);

        for (i = 0; i < V_ACT; i = i + 1) begin
            for (j = 0; j < H_ACT; j = j + 1) begin
                @(posedge src_clk);
                src_de  <= 1;
                src_pix <= {i[7:0], j[7:0]};
            end
            @(posedge src_clk);
            src_de <= 0;
            repeat (20) @(posedge src_clk);
        end
        src_de <= 0;

        repeat (200) @(posedge src_clk);

        // Display accepts the completed slot only at a frame boundary.
        @(negedge pix_clk);vs=1;repeat(8) @(negedge pix_clk);vs=0;
        // ---- 显示：V_OFF 个空行 + V_ACT 行 ----
        for (i = 0; i < V_OFF + V_ACT; i = i + 1) begin
            @(posedge pix_clk);
            hs <= 1;
            repeat (4) @(posedge pix_clk);
            hs <= 0;
            repeat (40) @(posedge pix_clk);
            if (i >= V_OFF) begin
                for (j = 0; j < H_ACT; j = j + 1) begin
                    @(posedge pix_clk);
                    de <= 1;
                end
                @(posedge pix_clk);
                de <= 0;
            end
            repeat (30) @(posedge pix_clk);
        end

        repeat (100) @(posedge pix_clk);
        if (errors == 0)
            $display("TB_MEM PASS: %0d lines x %0d px, no mismatch", V_ACT, H_ACT);
        else
            $display("TB_MEM FAIL: %0d mismatches", errors);
        $finish;
    end

    initial begin
        #2000000;
        $display("TB_MEM TIMEOUT (errors=%0d) underrun=%b ovf=%b", errors, dr_underrun, fw_ovf);
        $finish;
    end

endmodule

`default_nettype wire
