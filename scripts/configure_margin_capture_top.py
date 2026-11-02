"""One-shot conversion of the copied key-angle top to raw margin acquisition."""
from pathlib import Path
import re,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from margin_geometry import load,identity
p=ROOT/'rtl/top/top_pangu50.v';s=p.read_text(encoding='utf-8')
def once(old,new):
 global s
 assert s.count(old)==1,old
 s=s.replace(old,new)
once('parameter integer HOST_CONTROL_ENABLE = 0 // Standalone: retain original local presets and keys.',
 'parameter integer HOST_CONTROL_ENABLE = 0,\n    parameter integer SRC_W=1296,SRC_H=972,SRC_STRIDE_WORDS=768')
once('if(format_key_q && !format_key_n)decode_request<=decode_request+1\'b1;', '// Fixed RGB decode for raw calibration; no key-controlled reinterpretation.')
once('.VERIFY_PLL(1),.IMAGE_PROFILE(1)) u_cam_cfg','.VERIFY_PLL(1),.IMAGE_PROFILE(1),.GEOMETRY_PROFILE(1)) u_cam_cfg')
once('.bar_request(bar_request),.config_ok(cam_cfg_done)',".bar_request(1'b0),.config_ok(cam_cfg_done)")
once('tpg_stream #(.H_ACT(H_ACT), .V_ACT(V_ACT))','tpg_stream #(.H_ACT(SRC_W), .V_ACT(SRC_H))')
once('adaptive_gamma #(.WIDTH(H_ACT),.HEIGHT(V_ACT))','adaptive_gamma #(.WIDTH(SRC_W),.HEIGHT(SRC_H))')
once('.key_n(gamma_key_n),.test_key_n(test_key_n)',".key_n(1'b1),.test_key_n(1'b1)")
once('focus_meter #(.WIDTH(H_ACT),.HEIGHT(V_ACT))','focus_meter #(.WIDTH(SRC_W),.HEIGHT(SRC_H))')
once('frame_writer #(.H_ACT(H_ACT),.V_ACT(V_ACT),.FLIP_V(1)',
 'frame_writer #(.H_ACT(SRC_W),.V_ACT(SRC_H),.STRIDE_WORDS(SRC_STRIDE_WORDS),.SLOT_WORDS(SRC_SLOT_WORDS),.FLIP_V(1)')
s,n=re.subn(r'localparam \[CTRL_ADDR_WIDTH-1:0\] SRC_SLOT_WORDS = 460800;[^\n]*\n\s*localparam \[CTRL_ADDR_WIDTH-1:0\] CORR_BASE\s*= 1382400;[^\n]*',
 'localparam [CTRL_ADDR_WIDTH-1:0] SRC_SLOT_WORDS = SRC_STRIDE_WORDS*SRC_H;\n    localparam [CTRL_ADDR_WIDTH-1:0] DST_SLOT_WORDS = H_ACT*V_ACT/2;\n    localparam [CTRL_ADDR_WIDTH-1:0] CORR_BASE = 3*SRC_SLOT_WORDS;',s);assert n==1
once('.FRAME_BASE(CORR_BASE), .SLOT_WORDS(SRC_SLOT_WORDS)) u_dr','.FRAME_BASE(CORR_BASE), .SLOT_WORDS(DST_SLOT_WORDS)) u_dr')
once('.shown_slot(dr_shown),.frame_seen(dr_seen)', '.shown_slot(dr_shown),.frame_seen(dr_seen),.visible_slot(display_visible_slot)')
once('wire signed [9:0] active_angle;wire [12:0] angle_bcd;wire angle_toggle;',
 'wire signed [9:0] active_angle=0;wire [12:0] angle_bcd=0;wire angle_toggle=0;\n    wire [1:0] requested_page,active_page;wire[15:0]roi_x,roi_y;\n    wire display_visible_slot;wire[31:0]selected_source_seq;')
once("{PRE_CY,PRE_CX,PRE_FY,PRE_FX,32'd0,32'd0,PRE_K2,PRE_K1,PRE_F,PRE_E,PRE_D,PRE_C,PRE_B,PRE_A};",
 "{32'd0,32'd0,32'd33554432,32'd33554432,32'd0,32'd0,32'd0,32'd0,\n         (32'd128*roi_y),32'd32768,32'd0,(32'd128*roi_x),32'd0,32'd32768};")
s,n=re.subn(r'key_angle_controls u_controls\(.*?\.restore_defaults\(restore_defaults\)\);',
 '''assign local_correction_active=0;assign local_strength_active=0;assign local_zoom_active=0;assign restore_defaults=0;
    margin_view_controls u_controls(.clk(ddr_clk),.rstn(ddr_init_done),.frame_start(accept_source),
      .next_n(key2),.previous_n(key3),.requested_page(requested_page),.active_page(active_page),.roi_x(roi_x),.roi_y(roi_y));''',s,flags=re.S);assert n==1
once('wp_dst_slot ? SRC_SLOT_WORDS :','wp_dst_slot ? DST_SLOT_WORDS :')
once('.process_overflow(wp_ovf),.display_seen', '.process_overflow(wp_ovf || !metadata_ready),.display_seen')
once('.display_frozen(display_frozen));','.display_frozen(display_frozen),.selected_frame_seq(selected_source_seq));')
once('.SRC_STRIDE(640),.SRC_H(720),.V_ACT(720)', '.SRC_STRIDE(SRC_STRIDE_WORDS),.SRC_W(SRC_W),.SRC_H(SRC_H),.V_ACT(688)')
metadata='''
    (* async_reg="true" *) reg [1:0] config_sync=0,fault_sync=0;
    always @(posedge ddr_clk)begin
      if(!ddr_init_done)begin config_sync<=0;fault_sync<=0;end
      else begin config_sync<={config_sync[0],cam_cfg_done};fault_sync<={fault_sync[0],cam_fault};end
    end
    wire [7:0] capture_flags={1'b0,1'b1,(gamma_status_ddr==0 && gamma_test_ddr==0),
      !bar_sync_ddr[1],!fw_ovf,(config_sync[1] && !fault_sync[1]),freeze_wanted,1'b1};
    wire [223:0] metadata_payload={32'h57524157,8'd1,capture_flags,{6'd0,requested_page},8'd0,
      GEOMETRY_ID,16'd1296,16'd972,(requested_page[0]?16'd16:16'd0),
      (requested_page[1]?16'd284:16'd0),16'd1280,16'd688,selected_source_seq};
    wire[255:0]working_metadata;wire metadata_ready;
    reg[255:0]metadata_slot0=0,metadata_slot1=0;
    margin_metadata u_metadata(.clk(ddr_clk),.rstn(ddr_init_done),.start(accept_source),
      .payload(metadata_payload),.metadata(working_metadata),.ready(metadata_ready));
    always @(posedge ddr_clk)begin
      if(!ddr_init_done)begin metadata_slot0<=0;metadata_slot1<=0;end
      else if(wp_done && !wp_ovf && metadata_ready)begin
        if(wp_dst_slot)metadata_slot1<=working_metadata;else metadata_slot0<=working_metadata;
      end
    end
'''.replace('GEOMETRY_ID',f"32'h{identity(load())[1]:08x}")
once('    reg de_aligned=0,hs_aligned=0,vs_aligned=0;',metadata+'\n    reg de_aligned=0,hs_aligned=0,vs_aligned=0;')
once('camera_probe #(.WIDTH(H_ACT),.HEIGHT(V_ACT))','camera_probe #(.WIDTH(SRC_W),.HEIGHT(SRC_H))')
s,n=re.subn(r'metrics_osd #\(\.SINGLE_CAMERA\(1\),\.SHOW_ANGLE\(1\)\) u_osd\(.*?\.enabled\(\)\);',
 '''margin_footer u_footer(.clk(clk_pix),.rstn(rstn_pix),.vs(vs_aligned),.de(de_aligned),
        .visible_slot(display_visible_slot),.slot0(metadata_slot0),.slot1(metadata_slot1),
        .x(x_aligned),.y(y_aligned),.pixel(fb_pix),.result(osd_pixel),.overlay(osd_overlay));''',s,flags=re.S);assert n==1
once('    defparam u_osd.PIPELINE_FONT = 1;','    // Footer provides the same single pixel-clock boundary.')
once('quality_display #(.DEFAULT_MODE(2),.MAX_MODE(3),.NATURAL_DETAIL(1))','quality_display #(.DEFAULT_MODE(1),.MAX_MODE(1),.NATURAL_DETAIL(0))')
once('.cycle_n(quality_cycle_n)',".cycle_n(1'b1)")
p.write_text(s,encoding='utf-8');print('Converted acquisition top; geometry ID',hex(identity(load())[1]))
