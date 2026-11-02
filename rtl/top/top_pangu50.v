`timescale 1ns / 1ps
// MES50HP: OV5640 -> three protected source slots -> tiled correction -> two display slots.
// HDMI 1280x720 at 74.25 MHz / 60 Hz; correction frame rate is lower.
// Single C1 + Q2 + UART on J8 15/16. C2 ports and fusion engine removed.
`default_nettype none

module top_pangu50 #(
    parameter integer H_ACT   = 1280,   // 有效宽度（必须与 OV5640 寄存器一致）
    parameter integer V_ACT   = 720,    // 有效高度
    parameter integer BYTE_SWAP = 1,    // 1: {D[4:0],D[10:5],D[15:11]} 取 RGB565
    parameter integer USE_TPG  = 0,     // 1: 用内部彩条代替摄像头（bring-up 用）
    parameter integer HOST_CONTROL_ENABLE = 0,
    parameter integer SRC_W=1296,SRC_H=972,SRC_STRIDE_WORDS=768
) (
    input  wire        sys_clk,        // 50MHz 板载晶振  P20
    input  wire        host_rx,        // J8 pin15 / Y12, NC on dual OV5640 module
    output wire        host_tx,        // J8 pin16 / W12, NC on dual OV5640 module

    // ---------------- 按键 / LED ----------------
    input  wire        key0,           // B1
    input  wire        key1,           // R9
    input  wire        key2,           // R8
    input  wire        key3,           // U6
    input  wire        key4,           // T7
    input  wire        key5,           // W9
    input  wire        key6,           // Y8
    input  wire        key7,           // Y7
    output wire        led_int,        // LED0  R3
    output wire [7:1]  led,            // LED1..LED7

    // ---------------- HDMI 发送芯片复位 / I2C ----------------
    output wire        rstn_out1,      // R17
    output wire        rstn_out2,      // P21
    output wire        rstn_out3,      // P18
    output wire        iic_scl,        // C19  (MS7210 与 HDMI_IN3 共用)
    inout  wire        iic_sda,        // A20

    // ---------------- HDMI 输出 ----------------
    output wire        pixclk_out,     // F17
    output reg         vs_out,         // F7
    output reg         hs_out,         // A5
    output reg         de_out,         // C5
    output reg  [7:0]  r_out,          // D4,D5,C4,A4,E5,E6,G8,F9
    output reg  [7:0]  g_out,          // H10,H11,G13,H13,F14,F15,G16,D17
    output reg  [7:0]  b_out,          // C18,A18,B18,B20,B2,A2,B3,A3

    // ---------------- OV5640（40pin 扩展口） ----------------
    output wire        cam_rst_n,      // W10  模块 pin12 CAM1_REST
    inout  wire        cam_scl,        // Y11  模块 pin6  CAM1_SCL
    inout  wire        cam_sda,        // Y13  模块 pin4  CAM1_SDA
    input  wire        cam_pclk,       // T12  模块 pin18 CAM1_PCLK
    input  wire        cam_hs,         // AB10 模块 pin9  CAM1_HREF
    input  wire        cam_vs,         // U12  模块 pin17 CAM1_VSYNC
    input  wire [7:0]  cam_d,          // {AB13,Y10,T11,R11,W11,AB11,AA10,V11}

    // Single C1: no C2 FPGA ports allocated.

    // ---------------- DDR3 ----------------
    output wire        mem_rst_n,
    output wire        mem_ck,
    output wire        mem_ck_n,
    output wire        mem_cke,
    output wire        mem_cs_n,
    output wire        mem_ras_n,
    output wire        mem_cas_n,
    output wire        mem_we_n,
    output wire        mem_odt,
    output wire [14:0] mem_a,
    output wire [2:0]  mem_ba,
    inout  wire [3:0]  mem_dqs,
    inout  wire [3:0]  mem_dqs_n,
    inout  wire [31:0] mem_dq,
    output wire [3:0]  mem_dm
);

    // ======================================================================
    //  0. 常量
    // ======================================================================
    localparam integer MEM_ROW_ADDR_WIDTH = 15;
    localparam integer MEM_COL_ADDR_WIDTH = 10;
    localparam integer MEM_BADDR_WIDTH    = 3;
    localparam integer MEM_DQ_WIDTH       = 32;
    localparam integer CTRL_ADDR_WIDTH    = MEM_ROW_ADDR_WIDTH + MEM_BADDR_WIDTH + MEM_COL_ADDR_WIDTH;
    localparam [CTRL_ADDR_WIDTH-1:0] SRC_SLOT_WORDS = SRC_STRIDE_WORDS*SRC_H;
    localparam [CTRL_ADDR_WIDTH-1:0] DST_SLOT_WORDS = H_ACT*V_ACT/2;
    localparam [CTRL_ADDR_WIDTH-1:0] CORR_BASE = 3*SRC_SLOT_WORDS;

    // ======================================================================
    //  1. 时钟
    // ======================================================================
    wire clk_pix;      // 74.25MHz HDMI 像素时钟
    wire clk_pix_ref, pixel_locked;
    localparam integer PIXEL_HZ=74250000;
    wire cfg_clk;      // 10MHz      I2C 配置时钟
    wire clk_25m;      // 25MHz      OV5640 SCCB 状态机时钟
    wire locked;

    pll u_pll (
        .clkin1   (sys_clk),
        .clkout0  (clk_pix_ref),
        .clkout1  (cfg_clk),
        .clkout2  (clk_25m),
        .pll_lock (locked )
    );

    // Keep original 10MHz/25MHz control clocks; dedicated pixel PLL converts
    // the existing 75MHz reference to the exact nominal CEA 720p60 clock.
    pll_720p60 u_pixel_pll(.clkin1(clk_pix_ref),.clkout0(clk_pix),.clkout1(),.clkout2(),.pll_lock(pixel_locked));

    // ======================================================================
    //  2. 复位
    // ======================================================================
    reg [15:0] rstn_cnt = 16'd0;
    always @(posedge cfg_clk) begin
        if (!locked || !pixel_locked)      rstn_cnt <= 16'd0;
        else if (rstn_cnt != 16'h4000)     rstn_cnt <= rstn_cnt + 16'd1;
    end

    wire rstn_all = (rstn_cnt == 16'h4000);

    assign rstn_out1 = rstn_all;
    assign rstn_out2 = rstn_all;
    assign rstn_out3 = rstn_all;

    // 每个时钟域各自做一次复位同步（异步拉低、同步释放）。
    // 直接把别的时钟域产生的复位接到本域触发器的同步复位端，会形成真实的
    // 跨域时序路径（PDS 实测：cfg_clk → clk_pix 48 个端点 setup -2.817ns）。
    wire rstn_pix, rstn_pclk, rstn_cap_ddr, fb_init_pix;
    wire ddr_clk;         // 提前声明：摄像头分支（dvp_capture）要用
    wire ddr_init_done;   // 同上（DDR3 初始化完成）
    wire cam_cfg_done,host_byte_valid;
    wire format_key_n,gamma_key_n;
    key_short_long u_key4(.clk(ddr_clk),.rstn(ddr_init_done),.key_n(key4),
      .short_n(format_key_n),.long_n(gamma_key_n));
    wire strength_key_n,freeze_key_n,freeze_wanted,source_frozen,display_frozen;
    wire raw_key_n,zoom_key_n;
    key_short_long u_key0(.clk(ddr_clk),.rstn(ddr_init_done),.key_n(key0),
      .short_n(raw_key_n),.long_n(zoom_key_n));
    key_short_long u_key1(.clk(ddr_clk),.rstn(ddr_init_done),.key_n(key1),
      .short_n(strength_key_n),.long_n(freeze_key_n));
    reg [1:0] gamma_status_ddr=0,gamma_test_ddr=0;
    wire test_key_n,bar_key_n,phase_key_n;
    key_short_long u_key5(.clk(ddr_clk),.rstn(ddr_init_done),.key_n(key5),.short_n(test_key_n),.long_n(bar_key_n));
    key_short_long u_key6(.clk(ddr_clk),.rstn(ddr_init_done),.key_n(key6),.short_n(phase_key_n),.long_n());
    reg bar_request=0,phase_request=0,bar_key_q=1,phase_key_q=1;
    wire bar_active,phase_active,cam_fault;wire [7:0] cam_format,cam_retries;
    (* async_reg="true" *)reg [1:0] bar_sync_ddr=0,phase_sync_ddr=0;
    reg [1:0] decode_request=0,decode_active=0;reg format_key_q=1;
    always @(posedge ddr_clk)begin
      if(!ddr_init_done)begin bar_request<=0;phase_request<=0;bar_key_q<=1;phase_key_q<=1;format_key_q<=1;decode_request<=0;bar_sync_ddr<=0;phase_sync_ddr<=0;end
      else begin
        bar_key_q<=bar_key_n;phase_key_q<=phase_key_n;format_key_q<=format_key_n;
        if(bar_key_q && !bar_key_n)bar_request<=!bar_request;
        if(phase_key_q && !phase_key_n)phase_request<=!phase_request;
        // Fixed RGB decode for raw calibration; no key-controlled reinterpretation.
        bar_sync_ddr<={bar_sync_ddr[0],bar_active};phase_sync_ddr<={phase_sync_ddr[0],phase_active};
      end
    end
    wire probe_vs,probe_de;wire [15:0] probe_word;
    always @(posedge ddr_clk)begin
      if(!ddr_init_done)decode_active<=0;else if(probe_vs)decode_active<=decode_request;
    end
    reg tx_q=1;reg [7:0] tx_edges=0,rx_bytes=0;
    always @(posedge ddr_clk)begin
      if(!ddr_init_done)begin tx_q<=1;tx_edges<=0;rx_bytes<=0;end
      else begin tx_q<=host_tx;if(tx_q!=host_tx && tx_edges!=255)tx_edges<=tx_edges+1'b1;
        if(host_byte_valid && rx_bytes!=255)rx_bytes<=rx_bytes+1'b1;end
    end

    wire [9:0] freeze_context={2'd0,decode_active,gamma_status_ddr,gamma_test_ddr,bar_sync_ddr[1],phase_sync_ddr[1]};
    reg [9:0] freeze_context_previous=10'd0;
    always @(posedge ddr_clk)begin
      if(!ddr_init_done)freeze_context_previous<=10'd0;
      else freeze_context_previous<=freeze_context;
    end
    freeze_toggle u_freeze(.clk(ddr_clk),.rstn(ddr_init_done),.key_n(freeze_key_n),
      .clear_i(freeze_context!=freeze_context_previous),.wanted(freeze_wanted));
    wire fb_init_done;   // 同上（帧缓存初始化完成）
    reset_sync u_rst_pix  (.clk(clk_pix),  .arst_n(rstn_all && ddr_init_done), .rst_n(rstn_pix ));
    wire capture_ready = cam_cfg_done && ddr_init_done;
    reset_sync u_rst_pclk (.clk(cam_pclk), .arst_n(capture_ready), .rst_n(rstn_pclk));
    reset_sync u_rst_cap_ddr (.clk(ddr_clk), .arst_n(capture_ready), .rst_n(rstn_cap_ddr));
    assign fb_init_pix = rstn_pix;
    assign fb_init_done = ddr_init_done;

    // ======================================================================
    //  3. HDMI 发送芯片配置（MS7210）
    // ======================================================================
    wire hdmi_cfg_done;
    ms72xx_ctl u_ms72xx (
        .clk       (cfg_clk),
        .rst_n     (rstn_out1),
        .init_over (hdmi_cfg_done),
        .iic_scl   (iic_scl),
        .iic_sda   (iic_sda)
    );

    // ======================================================================
    //  4. OV5640 上电时序 + 寄存器配置
    // ======================================================================
    wire cam_rstn_int, cam_pwdn, cam_init_en;
    power_on_delay u_power_on (
        .clk_50M      (sys_clk),
        .reset_n      (rstn_all),
        .camera1_rstn (cam_rstn_int),
        .camera2_rstn (),
        .camera_pwnd  (cam_pwdn),
        .initial_en   (cam_init_en)
    );

    assign cam_rst_n  = cam_rstn_int;

    // The proven checked SCCB engine is now applied to the sole C1 bus.
    ov5640_checked_config #(.PLL_MULTIPLIER(8'h69),.VERIFY_PLL(1),.IMAGE_PROFILE(1),.GEOMETRY_PROFILE(1)) u_cam_cfg(.clk(clk_25m),.rstn(cam_rstn_int),.initial_en(cam_init_en),
      .bar_request(1'b0),.config_ok(cam_cfg_done),.fault(cam_fault),.bar_active(bar_active),
      .format_readback(cam_format),.retry_total(cam_retries),.scl(cam_scl),.sda(cam_sda));
    reg [14:0] camera_status_timer=0;reg [18:0] camera_status=0;reg camera_status_toggle=0;
    wire [18:0] camera_status_now={cam_retries,cam_format,bar_active,cam_fault,cam_cfg_done};
    always @(posedge clk_25m)begin
      if(!cam_rstn_int)begin camera_status_timer<=0;camera_status<=0;camera_status_toggle<=0;end
      else if(camera_status_timer==24999)begin camera_status_timer<=0;
        if(camera_status_now!=camera_status)begin camera_status<=camera_status_now;camera_status_toggle<=!camera_status_toggle;end
      end else camera_status_timer<=camera_status_timer+1'b1;
    end

    // ======================================================================
    //  5. 视频源：OV5640 DVP 采集 或 内部测试图案
    //     USE_TPG=1 时摄像头逻辑完全不综合，两条通路不会同时存在，
    //     src_clk 不需要时钟切换（时钟切换在 FPGA 里是高风险结构）。
    // ======================================================================
    wire [15:0] src_rgb565;
    wire        src_de;
    wire        src_vs;
    wire        src_clk;         // 写入帧缓存用的像素时钟

    generate
    if (USE_TPG) begin : g_tpg
        // ---- 内部彩条：不依赖摄像头，用来验证 DDR3+HDMI 整条通路 ----
        tpg_stream #(.H_ACT(SRC_W), .V_ACT(SRC_H)) u_tpg (
            .clk    (clk_pix),
            .rst_n  (rstn_pix),
            .vs     (src_vs ),
            .de     (src_de ),
            .rgb565 (src_rgb565)
        );
        assign src_clk = clk_pix;
        assign probe_vs=1'b0;assign probe_de=1'b0;assign probe_word=16'd0;assign phase_active=1'b0;
    end else begin : g_cam
        // 摄像头：cam_pclk 域采样拼字节 → 异步 FIFO → ddr_clk 域出像素。
        // 不用 GTP_IOCLKDIV 派生时钟（PDS 对它推断不稳定，实测 −5ns）。
        wire [15:0] cap_pix;
        wire        cap_de, cap_vs;

        dvp_capture_phase u_cap(.cam_pclk(cam_pclk),.rstn(rstn_pclk),.vs(cam_vs),.hs(cam_hs),.d(cam_d),
          .phase_request(phase_request),.phase_active(phase_active),.ddr_clk(ddr_clk),.ddr_rstn(rstn_cap_ddr),
          .pix(cap_pix),.de(cap_de),.vs_o(cap_vs));
        assign probe_vs=cap_vs;assign probe_de=cap_de;assign probe_word=cap_pix;

        // C1 canonical RGB565 feeds the protected source ring directly.
        wire [15:0] decoded_bytes=decode_active[0]?{cap_pix[7:0],cap_pix[15:8]}:cap_pix;
        assign src_rgb565=decode_active[1]?decoded_bytes:(BYTE_SWAP?{decoded_bytes[4:0],decoded_bytes[10:5],decoded_bytes[15:11]}:decoded_bytes);
        assign src_vs=cap_vs;assign src_de=cap_de;
        assign src_clk = ddr_clk;      // 帧写入器统一跑在 DDR 域
    end
    endgenerate

    // Hold KEY4 for 1s: natural-video adaptive Gamma; reset bypass.
    // key_n was tied to 1'b1 here, so the block was permanently bypassed and its state
    // never reached the OSD. gamma_key_n is the KEY4 long-press pulse; the module has
    // its own 2FF synchroniser, so crossing from ddr_clk into src_clk is by design.
    wire [15:0] enhanced_pixel;wire enhanced_vs,enhanced_de;
    wire [1:0] gamma_status_source,gamma_test_source;wire gamma_toggle_source;
    wire [7:0] gamma_mean_source;wire gamma_mean_toggle;
    adaptive_gamma #(.WIDTH(SRC_W),.HEIGHT(SRC_H)) u_gamma(
        .clk(src_clk),.rstn(USE_TPG ? rstn_pix : rstn_cap_ddr),
        .vs(src_vs),.de(src_de),.pixel(src_rgb565),.key_n(gamma_key_n),.test_key_n(1'b1),
        .vs_o(enhanced_vs),.de_o(enhanced_de),.pixel_o(enhanced_pixel),
        .active_enabled(),.active_curve(),.status_code(gamma_status_source),.status_toggle(gamma_toggle_source),
        .active_test_mode(gamma_test_source),.mean_luma_bcd(gamma_mean_source),.mean_toggle(gamma_mean_toggle));
    (* async_reg="true" *) reg [2:0] gamma_toggle_sync=0;
    (* async_reg="true" *) reg [2:0] gamma_mean_sync=0;
    reg [7:0] gamma_mean_ddr=0;
    always @(posedge ddr_clk)begin
        if(!ddr_init_done)begin gamma_toggle_sync<=0;gamma_status_ddr<=0;gamma_test_ddr<=0;gamma_mean_sync<=0;gamma_mean_ddr<=0;end
        else begin
            gamma_toggle_sync<={gamma_toggle_sync[1:0],gamma_toggle_source};
            if(gamma_toggle_sync[2]!=gamma_toggle_sync[1])begin
                gamma_status_ddr<=gamma_status_source;gamma_test_ddr<=gamma_test_source;
            end
            gamma_mean_sync<={gamma_mean_sync[1:0],gamma_mean_toggle};
            if(gamma_mean_sync[2]!=gamma_mean_sync[1])gamma_mean_ddr<=gamma_mean_source;
        end
    end

    // Focus metering taps the canonical raw source; it never drives video data.
    wire [15:0] focus_bcd_source;wire focus_toggle_source;
    focus_meter #(.WIDTH(SRC_W),.HEIGHT(SRC_H)) u_focus_meter(
        .clk(src_clk),.rstn(USE_TPG ? rstn_pix : rstn_cap_ddr),
        .vs(src_vs),.de(src_de),.pixel(src_rgb565),
        .score_bcd(focus_bcd_source),.score_toggle(focus_toggle_source));
    (* async_reg="true" *) reg [2:0] focus_toggle_sync=0;
    reg [15:0] focus_bcd_ddr=0;
    always @(posedge ddr_clk)begin
        if(!ddr_init_done)begin focus_toggle_sync<=0;focus_bcd_ddr<=0;end
        else begin
            focus_toggle_sync<={focus_toggle_sync[1:0],focus_toggle_source};
            if(focus_toggle_sync[2]!=focus_toggle_sync[1])focus_bcd_ddr<=focus_bcd_source;
        end
    end

    // ======================================================================
    //  6. DDR3 帧缓存（有序采集、六个源槽、两个矫正结果槽）
    // ======================================================================
    wire [CTRL_ADDR_WIDTH-1:0] axi_awaddr;
    wire [CTRL_ADDR_WIDTH-1:0] axi_araddr;
    wire [3:0]  axi_awid, axi_awlen, axi_arid, axi_arlen, axi_rid;
    wire [2:0]  axi_awsize, axi_arsize;      // fram_buf 输出，本工程不使用
    wire [1:0]  axi_awburst, axi_arburst;    // 同上
    wire        axi_awvalid, axi_awready, axi_wvalid, axi_wready;
    wire [MEM_DQ_WIDTH*8-1:0] axi_wdata, axi_rdata;
    wire [MEM_DQ_WIDTH-1:0]   axi_wstrb;
    wire        axi_arvalid, axi_arready, axi_rvalid, axi_rlast, axi_rready;
    wire        axi_wlast;          // DDR3 IP 给出的写突发结束（接 fram_buf）

    wire [15:0] fb_pix;
    wire        fb_de;
    wire        pll_lock_ddr;

    wire vs_disp, hs_disp, de_disp, de_disp_re;
    wire vid_line_start;wire [9:0] vid_line_y;
    wire [11:0] vid_x,vid_y;

    // ---------------- M2：自研存储子系统（替换厂商 fram_buf） ----------------
    wire        fw_req, fw_ready, fw_done, fw_adv, fw_ovf;
    wire display_visible_slot,runtime_certified,runtime_capture_ok;
    wire [2:0] fw_slot,fw_frame_slot;
    wire fw_frame_done,fw_frame_valid;
    wire [31:0] fw_frame_seq;
    wire read_hold;wire [2:0] read_slot;
    wire [CTRL_ADDR_WIDTH-1:0] fw_addr;
    wire [7:0]  fw_beats;
    wire [255:0] fw_data;

    frame_writer #(.H_ACT(SRC_W),.V_ACT(SRC_H),.STRIDE_WORDS(SRC_STRIDE_WORDS),.SLOT_WORDS(SRC_SLOT_WORDS),.FLIP_V(1),.SLOT_COUNT(3), .AW(CTRL_ADDR_WIDTH), .FRAME_BASE({CTRL_ADDR_WIDTH{1'b0}})) u_fw (
        .src_clk   (src_clk),
        .src_rstn  (USE_TPG ? rstn_pix : ddr_init_done),
        .src_vs    (enhanced_vs),
        .src_de    (enhanced_de),
        .src_pix   (enhanced_pixel),
        .ddr_clk   (ddr_clk),
        .ddr_rstn  (ddr_init_done),
        .w_req     (fw_req),
        .w_addr    (fw_addr),
        .w_beats   (fw_beats),
        .w_ready   (fw_ready),
        .w_done    (fw_done),
        .w_data    (fw_data),
        .w_adv     (fw_adv),
        .wr_slot   (fw_slot),
        .hold_valid(read_hold),.hold_slot(read_slot),
        .frame_done(fw_frame_done),.frame_valid(fw_frame_valid),.frame_slot(fw_frame_slot),.frame_seq(fw_frame_seq),
        .led_overflow (fw_ovf)
    );

    wire        dr_req, dr_ready, dr_done, dr_valid, dr_last, dr_underrun;
    wire [CTRL_ADDR_WIDTH-1:0] dr_addr;
    wire [7:0]  dr_beats;
    wire [255:0] dr_data;
    wire [15:0] disp_pix;
    wire dr_shown,dr_seen;
    wire wp_front,wp_have_frame;

    wire        axi_wr_req, axi_wr_ready, axi_wr_done, axi_wr_adv;
    wire [CTRL_ADDR_WIDTH-1:0] axi_wr_addr;
    wire [7:0]  axi_wr_beats;
    wire [255:0] axi_wr_data;
    wire        axi_rd_req, axi_rd_ready, axi_rd_done, axi_rd_valid, axi_rd_last;
    wire [CTRL_ADDR_WIDTH-1:0] axi_rd_addr;
    wire [7:0]  axi_rd_beats;
    wire [255:0] axi_rd_data;

    // Source/output slot constants declared before their users.

    // 校正引擎 <-> mem_hub 连线
    wire        wp_w_req, wp_w_ready, wp_w_done, wp_w_adv;
    wire [CTRL_ADDR_WIDTH-1:0] wp_w_addr;
    wire [7:0]  wp_w_beats;
    wire [255:0] wp_w_data;
    wire wp_dst_slot;      // 矫正结果双缓冲槽位（0/1 交替）
    wire        wp_r_req, wp_r_ready, wp_r_done, wp_r_valid, wp_r_last;
    wire [CTRL_ADDR_WIDTH-1:0] wp_r_addr;
    wire [7:0]  wp_r_beats;
    wire [255:0] wp_r_data;

    // Direct capture/correction ports: no stereo rings or arbitration.
    wire cap_m_req,cap_m_ready,cap_m_done,cap_m_adv;
    wire [27:0] cap_m_addr;wire [7:0] cap_m_beats;wire [255:0] cap_m_data;
    assign cap_m_req=fw_req;assign cap_m_addr=fw_addr;assign cap_m_beats=fw_beats;assign cap_m_data=fw_data;
    assign fw_ready=cap_m_ready;assign fw_done=cap_m_done;assign fw_adv=cap_m_adv;
    wire source_r_req,source_r_ready,source_r_done,source_r_valid,source_r_last;
    wire [27:0] source_r_addr;wire [7:0] source_r_beats;wire [255:0] source_r_data;
    assign source_r_req=wp_r_req;assign source_r_addr=wp_r_addr;assign source_r_beats=wp_r_beats;
    assign wp_r_ready=source_r_ready;assign wp_r_done=source_r_done;assign wp_r_valid=source_r_valid;
    assign wp_r_data=source_r_data;assign wp_r_last=source_r_last;
    mem_hub #(.AW(CTRL_ADDR_WIDTH)) u_hub (
        .clk(ddr_clk), .rstn(ddr_init_done),
        .w0_req(cap_m_req), .w0_addr(cap_m_addr), .w0_beats(cap_m_beats),
        .w0_ready(cap_m_ready), .w0_done(cap_m_done), .w0_data(cap_m_data), .w0_adv(cap_m_adv),
        .w1_req(wp_w_req), .w1_addr(wp_w_addr), .w1_beats(wp_w_beats),
        .w1_ready(wp_w_ready), .w1_done(wp_w_done), .w1_data(wp_w_data), .w1_adv(wp_w_adv),
        .r0_req(dr_req), .r0_addr(dr_addr), .r0_beats(dr_beats),
        .r0_ready(dr_ready), .r0_done(dr_done),
        .r0_data(dr_data), .r0_valid(dr_valid), .r0_last(dr_last),
        .r1_req(source_r_req), .r1_addr(source_r_addr), .r1_beats(source_r_beats),
        .r1_ready(source_r_ready), .r1_done(source_r_done),
        .r1_data(source_r_data), .r1_valid(source_r_valid), .r1_last(source_r_last),
        .m_wr_req(axi_wr_req), .m_wr_addr(axi_wr_addr), .m_wr_beats(axi_wr_beats),
        .m_wr_ready(axi_wr_ready), .m_wr_done(axi_wr_done),
        .m_wr_data(axi_wr_data), .m_wr_adv(axi_wr_adv),
        .m_rd_req(axi_rd_req), .m_rd_addr(axi_rd_addr), .m_rd_beats(axi_rd_beats),
        .m_rd_ready(axi_rd_ready), .m_rd_done(axi_rd_done),
        .m_rd_data(axi_rd_data), .m_rd_valid(axi_rd_valid), .m_rd_last(axi_rd_last)
    );

    axi_ddr_master #(.AW(CTRL_ADDR_WIDTH)) u_axi (
        .clk(ddr_clk), .rstn(ddr_init_done),
        .wr_req(axi_wr_req), .wr_addr(axi_wr_addr), .wr_beats(axi_wr_beats),
        .wr_ready(axi_wr_ready), .wr_done(axi_wr_done),
        .wr_data(axi_wr_data), .wr_dready(axi_wr_adv),
        .rd_req(axi_rd_req), .rd_addr(axi_rd_addr), .rd_beats(axi_rd_beats),
        .rd_ready(axi_rd_ready), .rd_done(axi_rd_done),
        .rd_data(axi_rd_data), .rd_dvalid(axi_rd_valid), .rd_dlast(axi_rd_last),
        .axi_awaddr(axi_awaddr), .axi_awid(axi_awid), .axi_awlen(axi_awlen),
        .axi_awvalid(axi_awvalid), .axi_awready(axi_awready),
        .axi_wdata(axi_wdata), .axi_wstrb(axi_wstrb),
        .axi_wready(axi_wready), .axi_wusero_last(1'b0),
        .axi_araddr(axi_araddr), .axi_arid(axi_arid), .axi_arlen(axi_arlen),
        .axi_arvalid(axi_arvalid), .axi_arready(axi_arready),
        .axi_rdata(axi_rdata), .axi_rvalid(axi_rvalid),
        .axi_rlast(axi_rlast), .axi_rid(axi_rid)
    );

    // ======================================================================
    //  7. 720p 时序发生器
    // ======================================================================
    sync_vg #(
        .V_TOTAL (750 ), .V_FP (5  ), .V_BP (20 ), .V_SYNC (5  ), .V_ACT (720 ),
        .H_TOTAL (1650), .H_FP (110), .H_BP (220), .H_SYNC (40 ), .H_ACT (1280)
    ) u_sync_vg (
        .clk    (clk_pix  ),
        .rstn   (rstn_pix),
        .vs_out (vs_disp  ),
        .hs_out (hs_disp  ),
        .de_out (de_disp),
        .de_re  (de_disp_re),
        .line_start(vid_line_start),.line_y(vid_line_y),
        .x_act  (vid_x),
        .y_act  (vid_y)
    );

    // ---------------- M2：显示行读取器 ----------------
    disp_reader #(.H_ACT(H_ACT), .V_ACT(V_ACT), .V_OFFSET(21),.FLIP_V(0),.EXTERNAL_LINE(1),
                  .AW(CTRL_ADDR_WIDTH), .FRAME_BASE(CORR_BASE), .SLOT_WORDS(DST_SLOT_WORDS)) u_dr (
        .pix_clk   (clk_pix),
        .pix_rstn  (rstn_pix),
        .vs        (vs_disp),
        .hs        (hs_disp),
        .de        (de_disp),
        .pix_out   (disp_pix),
        .wr_slot   (~wp_front),
        .frame_valid(wp_have_frame),.shown_slot(dr_shown),.frame_seen(dr_seen),.visible_slot(display_visible_slot),
        .line_start(vid_line_start),.line_y(vid_line_y),
        .ddr_clk   (ddr_clk),
        .ddr_rstn  (ddr_init_done),
        .r_req     (dr_req),
        .r_addr    (dr_addr),
        .r_beats   (dr_beats),
        .r_ready   (dr_ready),
        .r_done    (dr_done),
        .r_data    (dr_data),
        .r_valid   (dr_valid),
        .r_last    (dr_last),
        .led_underrun (dr_underrun)
    );

    assign fb_pix = disp_pix;
    assign fb_de  = de_disp;

    // ======================================================================
    //  矫正引擎：相机完整帧（A/B 槽）→ 逐块矫正 → CORR 槽（显示读它）
    //  系数先用经验值，标定后由串口替换。
    // ======================================================================
    wire signed [31:0] WP_A,WP_B,WP_C,WP_D,WP_E,WP_F,WP_FX,WP_FY,WP_CX,WP_CY,WP_K1,WP_K2,WP_P1,WP_P2;
    wire signed [31:0] PRE_A,PRE_B,PRE_C,PRE_D,PRE_E,PRE_F,PRE_FX,PRE_FY,PRE_CX,PRE_CY,PRE_K1,PRE_K2;
    wire signed [9:0] active_angle;wire [12:0] angle_bcd;wire angle_toggle;
    wire[447:0]runtime_coeff;
    wire [1:0] requested_page,active_page;wire[15:0]roi_x,roi_y;
    wire[31:0]selected_source_seq;
    wire [447:0] host_coeff;
    wire local_correction_active;wire [1:0] local_strength_active,local_zoom_active;
    wire host_active,host_bad_stop,restore_defaults;
    wire [7:0] host_byte,host_sequence;
    wire accept_source;
    uart_rx u_host_rx(.clk(ddr_clk),.rstn(ddr_init_done),.rx(host_rx),
        .valid(host_byte_valid),.data(host_byte),.framing_error(host_bad_stop));
    warp_config u_host_config(.clk(ddr_clk),.rstn(ddr_init_done),.byte_valid(1'b0),.byte_data(host_byte),
        .abort_packet(host_bad_stop),.frame_start(accept_source),.release_host(restore_defaults),
        .active_coeff(host_coeff),.active(host_active),.packet_ok(),.packet_error(),.active_sequence(host_sequence));
    assign {WP_CY,WP_CX,WP_FY,WP_FX,WP_P2,WP_P1,WP_K2,WP_K1,WP_F,WP_E,WP_D,WP_C,WP_B,WP_A} =
        runtime_coeff;
    assign local_strength_active=0;assign local_zoom_active=0;assign restore_defaults=0;
    margin_runtime_controls u_controls(.clk(ddr_clk),.rstn(ddr_init_done),.frame_start(accept_source),
      .key_n({key3,key2,1'b1,raw_key_n}),.coeff(runtime_coeff),.active_enabled(local_correction_active),
      .active_angle(active_angle),.angle_bcd(angle_bcd),.angle_toggle(angle_toggle),.certified(runtime_certified));

    wire wp_start;
    wire [CTRL_ADDR_WIDTH-1:0] wp_src;
    wire [CTRL_ADDR_WIDTH-1:0] wp_dst_base = CORR_BASE + (wp_dst_slot ? DST_SLOT_WORDS : {CTRL_ADDR_WIDTH{1'b0}});
    wire        wp_busy, wp_done, wp_ovf;
    warp_telemetry u_telemetry(.clk(ddr_clk),.rstn(ddr_init_done),.frame_start(wp_start),
        .frame_done(wp_done && !wp_ovf),.sequence_id(host_active?host_sequence:8'd0),
        .tx(host_tx),.last_cycles(),.completed_frames());

    // Completion metadata stays in ddr_clk; never synchronize a binary slot bus.
    (* async_reg="true" *) reg [1:0] shown_sync=0,seen_sync=0;
    always @(posedge ddr_clk) begin
      if(!ddr_init_done)begin shown_sync<=0;seen_sync<=0;end
      else begin shown_sync<={shown_sync[0],dr_shown};seen_sync<={seen_sync[0],dr_seen};end
    end
    warp_scheduler #(.AW(CTRL_ADDR_WIDTH),.SLOT_WORDS(SRC_SLOT_WORDS)) u_warp_scheduler(
      .clk(ddr_clk),.rstn(ddr_init_done),.freeze_wanted(freeze_wanted && runtime_capture_ok),
      .frame_valid(fw_frame_valid && runtime_capture_ok),.frame_seq(fw_frame_seq),.frame_slot(fw_frame_slot),
      .process_done(wp_done),.process_overflow(wp_ovf),.display_seen(seen_sync[1]),.display_slot(shown_sync[1]),
      .accept_source(accept_source),.process_start(wp_start),.source_base(wp_src),
      .read_hold(read_hold),.read_slot(read_slot),.destination_slot(wp_dst_slot),
      .front_slot(wp_front),.have_frame(wp_have_frame),.frozen(source_frozen),.display_frozen(display_frozen),.selected_frame_seq(selected_source_seq));

    warp_frame #(.AW(CTRL_ADDR_WIDTH), .COLS(40), .ROWS(23),
                 .WORDS_PER_LINE(640), .SRC_STRIDE(SRC_STRIDE_WORDS),.SRC_W(SRC_W),.SRC_H(SRC_H),.V_ACT(720),.TILE(16),.AFFINE_FRAC_BITS(24),
                 .RADIAL_MODEL_LUT(1),
                 .RADIAL_LUT_FILE("rtl/warp/radial_lut.hex")) u_warp_frame (
        .clk(ddr_clk), .rstn(ddr_init_done),
        .A(WP_A), .B(WP_B), .C(WP_C), .D(WP_D), .E(WP_E), .F(WP_F),
        .k1(WP_K1), .k2(WP_K2), .p1(WP_P1), .p2(WP_P2),
        .fx(WP_FX), .fy(WP_FY), .cx(WP_CX), .cy(WP_CY),
        .src_base(wp_src), .dst_base(wp_dst_base),
        .start(wp_start), .lut_enable(local_correction_active),
         .busy(wp_busy), .done(wp_done),
        .r_req(wp_r_req), .r_addr(wp_r_addr), .r_beats(wp_r_beats),
        .r_ready(wp_r_ready), .r_done(wp_r_done),
        .r_data(wp_r_data), .r_valid(wp_r_valid), .r_last(wp_r_last),
        .w_req(wp_w_req), .w_addr(wp_w_addr), .w_beats(wp_w_beats),
        .w_ready(wp_w_ready), .w_done(wp_w_done), .w_data(wp_w_data), .w_adv(wp_w_adv),
        .overflow(wp_ovf)
    );



    (* async_reg="true" *) reg [1:0] config_sync=0,fault_sync=0;
    always @(posedge ddr_clk)begin
      if(!ddr_init_done)begin config_sync<=0;fault_sync<=0;end
      else begin config_sync<={config_sync[0],cam_cfg_done};fault_sync<={fault_sync[0],cam_fault};end
    end
    assign runtime_capture_ok=runtime_certified && config_sync[1] && !fault_sync[1];

    reg de_aligned=0,hs_aligned=0,vs_aligned=0;
    reg [11:0] x_aligned=0,y_aligned=0;
    always @(posedge clk_pix) begin
        de_aligned<=fb_de;hs_aligned<=hs_disp;vs_aligned<=vs_disp;
        x_aligned<=vid_x;y_aligned<=vid_y;
    end
    wire [85:0] metric_snapshot;wire metric_toggle;
    wire [15:0] pclk_rate_bcd;
    pclk_meter u_pclk_meter(.ref_clk(ddr_clk),.source_clk(cam_pclk),.rstn(ddr_init_done),.rate_bcd(pclk_rate_bcd));
    wire [15:0] osd_pixel;
    wire osd_overlay,osd_key_n,quality_cycle_n;wire [1:0] display_quality;
    wire quality_vs,quality_hs,quality_de;wire [23:0] quality_rgb;
    key_short_long #(.DEBOUNCE_CYCLES(PIXEL_HZ/100),.LONG_CYCLES(PIXEL_HZ),.PULSE_CYCLES(PIXEL_HZ/50)) u_quality_key(
      .clk(clk_pix),.rstn(rstn_pix),.key_n(key7),.short_n(osd_key_n),.long_n(quality_cycle_n));
    video_metrics u_metrics(.clk(ddr_clk),.rstn(ddr_init_done),
        .source_done(fw_frame_done && fw_frame_valid),.process_start(wp_start),
        .process_done(wp_done && !wp_ovf),
        .mode_status({host_active,local_correction_active,local_strength_active,local_zoom_active}),
        .pclk_rate_bcd(pclk_rate_bcd),.focus_bcd(focus_bcd_ddr),.gamma_status(gamma_status_ddr),.test_mode(gamma_test_ddr),.mean_luma_bcd(gamma_mean_ddr),.snapshot(metric_snapshot),.snapshot_toggle(metric_toggle));
    wire [204:0] camera_probe_visible;
    camera_probe #(.WIDTH(SRC_W),.HEIGHT(SRC_H)) u_probe(.clk(ddr_clk),.rstn(ddr_init_done),
      .vs(probe_vs),.de(probe_de),.word_i(probe_word),.uart_status({tx_edges,rx_bytes}),
      .pix_clk(clk_pix),.pix_rstn(rstn_pix),.pix_vs(vs_aligned),.visible(camera_probe_visible));
    metrics_osd #(.SINGLE_CAMERA(1),.SHOW_ANGLE(1)) u_osd(.clk(clk_pix),.rstn(rstn_pix),.vs(vs_aligned),.de(de_aligned),
        .angle_bcd(angle_bcd),.angle_toggle(angle_toggle),
        .key_n(osd_key_n),.c2_status(camera_status),.c2_status_toggle(camera_status_toggle),.c2_phase(phase_sync_ddr[1]),.probe(camera_probe_visible),.display_quality(display_quality),.overlay_active(osd_overlay),.camera_selected(1'b0),.fusion_enabled(1'b0),.fusion_used(1'b0),.format2(decode_active),.frozen(display_frozen),.x(x_aligned),.y(y_aligned),.pixel(fb_pix),
        .snapshot(metric_snapshot),.snapshot_toggle(metric_toggle),.result(osd_pixel),.enabled());
    defparam u_osd.PIPELINE_FONT = 1;

    // ======================================================================
    //  8. HDMI 输出寄存（RGB565 → RGB888，与厂商时序一致）
    // ======================================================================
    // Split diagnostic character decode and font lookup to close pixel timing.
    // Match the added OSD cycle on the image and every video qualifier.
    // Footer provides the same single pixel-clock boundary.
    reg osd_vs_d=0,osd_hs_d=0,osd_de_d=0;
    reg [15:0] osd_image_d=0;
    always @(posedge clk_pix)begin
      if(!rstn_pix)begin osd_vs_d<=0;osd_hs_d<=0;osd_de_d<=0;osd_image_d<=0;end
      else begin osd_vs_d<=vs_aligned;osd_hs_d<=hs_aligned;osd_de_d<=de_aligned;osd_image_d<=fb_pix;end
    end
    quality_display #(.DEFAULT_MODE(1),.MAX_MODE(1),.NATURAL_DETAIL(0)) u_quality_display(.clk(clk_pix),.rstn(rstn_pix),
      .vs(osd_vs_d),.hs(osd_hs_d),.de(osd_de_d),.cycle_n(1'b1),
      .pixel(osd_image_d),.osd_pixel(osd_pixel),.osd_overlay(osd_overlay),
      .active_mode(display_quality),.vs_o(quality_vs),.hs_o(quality_hs),.de_o(quality_de),.rgb_o(quality_rgb));
    always @(posedge clk_pix) begin
        r_out<=quality_rgb[23:16];g_out<=quality_rgb[15:8];b_out<=quality_rgb[7:0];
        vs_out<=quality_vs;hs_out<=quality_hs;de_out<=quality_de;
    end

    assign pixclk_out = clk_pix;

    // ======================================================================
    //  9. DDR3 控制器
    // ======================================================================
    DDR3_50H u_DDR3_50H (
        .ref_clk     (sys_clk),
        .resetn      (rstn_out1),
        .ddr_init_done (ddr_init_done),
        .ddrphy_clkin  (ddr_clk),
        .pll_lock      (pll_lock_ddr),

        .axi_awaddr    (axi_awaddr),
        .axi_awuser_ap (1'b0),
        .axi_awuser_id (axi_awid),
        .axi_awlen     (axi_awlen),
        .axi_awready   (axi_awready),
        .axi_awvalid   (axi_awvalid),
        .axi_wdata     (axi_wdata),
        .axi_wstrb     (axi_wstrb),
        .axi_wready    (axi_wready),
        .axi_wusero_id (),
        .axi_wusero_last (),
        .axi_araddr    (axi_araddr),
        .axi_aruser_ap (1'b0),
        .axi_aruser_id (axi_arid),
        .axi_arlen     (axi_arlen),
        .axi_arready   (axi_arready),
        .axi_arvalid   (axi_arvalid),
        .axi_rdata     (axi_rdata),
        .axi_rid       (axi_rid),
        .axi_rlast     (axi_rlast),
        .axi_rvalid    (axi_rvalid),

        .apb_clk       (1'b0),
        .apb_rst_n     (1'b1),
        .apb_sel       (1'b0),
        .apb_enable    (1'b0),
        .apb_addr      (8'b0),
        .apb_write     (1'b0),
        .apb_ready     (),
        .apb_wdata     (16'b0),
        .apb_rdata     (),
        .apb_int       (),

        .mem_rst_n  (mem_rst_n),
        .mem_ck     (mem_ck),
        .mem_ck_n   (mem_ck_n),
        .mem_cke    (mem_cke),
        .mem_cs_n   (mem_cs_n),
        .mem_ras_n  (mem_ras_n),
        .mem_cas_n  (mem_cas_n),
        .mem_we_n   (mem_we_n),
        .mem_odt    (mem_odt),
        .mem_a      (mem_a),
        .mem_ba     (mem_ba),
        .mem_dqs    (mem_dqs),
        .mem_dqs_n  (mem_dqs_n),
        .mem_dq     (mem_dq),
        .mem_dm     (mem_dm),

        .debug_data       (),
        .debug_slice_state(),
        .debug_calib_ctrl (),
        .ck_dly_set_bin   (),
        .force_ck_dly_en  (1'b0),
        .force_ck_dly_set_bin (8'h05),
        .dll_step         (),
        .dll_lock         (),
        .init_read_clk_ctrl   (2'b0),
        .init_slip_step       (4'b0),
        .force_read_clk_ctrl  (1'b0),
        .ddrphy_gate_update_en(1'b0),
        .update_com_val_err_flag (),
        .rd_fake_stop     (1'b0)
    );

    // ======================================================================
    //  10. 指示灯
    //      LED0 心跳 | LED1 DDR 初始化完成 | LED2 相机配置完成
    //      LED3 HDMI 发送配置完成 | LED4 帧缓存已启动 | LED5..7 预留/视频活动
    // ======================================================================
    reg [26:0] hb_cnt = 27'd0;
    always @(posedge sys_clk) hb_cnt <= hb_cnt + 27'd1;

    reg src_de_seen = 1'b0;
    always @(posedge src_clk) if (src_de) src_de_seen <= 1'b1;

    reg disp_de_seen = 1'b0;
    always @(posedge clk_pix) if (fb_de) disp_de_seen <= 1'b1;

    // 按键目前未使用：参与异或只是为了让未用输入不被综合器警告为悬空
    wire keys_unused = ^{key7,key6,key5,key4,key3,key2,key1,key0};

    assign led_int = hb_cnt[25];                                  // LED0
    assign led[1]  = ddr_init_done;                               // LED1
    assign led[2]  = cam_cfg_done;                                // LED2
    assign led[3]  = hdmi_cfg_done;                               // LED3
    assign led[4]  = wp_have_frame;                                // LED4
    assign led[5]  = src_de_seen;                                 // LED5 视频源出过有效行
    assign led[6]  = disp_de_seen;                                // LED6 显示出过有效像素
    assign led[7]  = fw_ovf | wp_ovf | dr_underrun;       // LED7 心跳参考

endmodule

`default_nettype wire
