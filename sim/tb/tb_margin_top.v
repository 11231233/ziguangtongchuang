`timescale 1ns/1ps
module tb_margin_top;
reg clk=0,pix=0,rstn=0,fs=0,done=0,slot=0,key2=1,key3=1;always #5 clk=~clk;always #7 pix=~pix;
top_pangu50 dut(.sys_clk(clk),.host_rx(1'b1),.key0(1'b1),.key1(1'b1),.key2(key2),.key3(key3),.key4(1'b1),.key5(1'b1),.key6(1'b1),.key7(1'b1),
.cam_pclk(clk),.cam_hs(1'b0),.cam_vs(1'b0),.cam_d(8'd0));
defparam dut.u_controls.DEBOUNCE=3;
reg[255:0]expected[0:3];reg[2047:0]path;integer p;
initial begin
 if(!$value$plusargs("EXPECTED=%s",path))$fatal(1,"Missing fixture");$readmemh(path,expected);
 force dut.ddr_clk=clk;force dut.clk_pix=pix;force dut.ddr_init_done=rstn;force dut.rstn_pix=rstn;
 force dut.rstn_cap_ddr=rstn;force dut.rstn_pclk=rstn;
 force dut.cam_cfg_done=1'b1;force dut.cam_fault=1'b0;
 force dut.gamma_status_ddr=2'd0;force dut.gamma_test_ddr=2'd0;force dut.bar_sync_ddr=2'd0;force dut.fw_ovf=1'b0;
 force dut.freeze_wanted=1'b1;force dut.accept_source=fs;force dut.selected_source_seq=32'd42;
 force dut.wp_start=1'b0;force dut.wp_done=done;force dut.wp_ovf=1'b0;force dut.wp_dst_slot=slot;
 repeat(8)@(negedge clk);rstn=1;repeat(20)@(negedge clk);
 if(dut.SRC_SLOT_WORDS!=746496 || dut.DST_SLOT_WORDS!=460800 || dut.CORR_BASE!=2239488)$fatal(1,"Source/output buffers overlap");
 if(dut.u_fw.H_ACT!=1296 || dut.u_fw.V_ACT!=972 || dut.u_fw.WORDS!=768 || dut.u_fw.SLOT_WORDS!=746496)$fatal(1,"Capture layout");
 if(dut.u_warp_frame.SRC_W!=1296 || dut.u_warp_frame.SRC_H!=972 || dut.u_warp_frame.SRC_STRIDE!=768 || dut.u_warp_frame.V_ACT!=688 || dut.u_warp_frame.u_bbox.W!=1296)$fatal(1,"Active width incorrectly includes padding");
 if(dut.u_dr.SLOT_WORDS!=460800 || dut.u_cam_cfg.GEOMETRY_PROFILE!=1 || dut.u_quality_display.active_mode!==1)$fatal(1,"Geometry/Q1 wiring");
 if(dut.u_cam_cfg.bar_request!==0 || dut.u_gamma.key_n!==1 || dut.u_gamma.test_key_n!==1)$fatal(1,"Calibration modes are mutable");
 for(p=0;p<4;p=p+1)begin
  if(p>0)begin
   key2=0;repeat(12)@(negedge clk);key2=1;repeat(12)@(negedge clk);
   if(dut.active_page!==p-1)$fatal(1,"ROI changed before source boundary");
  end
  slot=p%2;fs=1;@(negedge clk);fs=0;repeat(230)@(negedge clk);
  if(dut.active_page!==p || dut.WP_C!==(p%2?32'd2048:32'd0) || dut.WP_F!==(p>=2?32'd36352:32'd0))$fatal(1,"ROI identity mapping");
  if(dut.wp_dst_base!==(2239488+(slot?460800:0)))$fatal(1,"Destination slot used source pitch");
  if(!dut.metadata_ready || dut.working_metadata!==expected[p])$fatal(1,"Wrong geometry/frame/ROI metadata");
  done=1;@(negedge clk);done=0;@(negedge clk);
  if((slot?dut.metadata_slot1:dut.metadata_slot0)!==expected[p])$fatal(1,"Result tag not stored with slot");
 end
 force dut.cam_cfg_done=1'b0;repeat(5)@(negedge clk);fs=1;@(negedge clk);fs=0;repeat(230)@(negedge clk);
 if(dut.working_metadata[210]!==0)$fatal(1,"Unverified config was tagged valid");
 $display("MARGIN_TOP PASS active/padded source dimensions, separate slots, fixed RAW/Q1/G0, ROI frame commit, verified CRC result metadata and failed-config flag");$finish;
end
initial begin #1000000;$fatal(1,"Timeout");end
endmodule
