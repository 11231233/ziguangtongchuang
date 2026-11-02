`timescale 1ns/1ps
module tb_c2_status_rom;
 reg clk=0,rstn=1,vs=0,toggle=0,phase=0;always #5 clk=~clk;
 reg[18:0] status=0;reg[11:0] x=0,y=0;wire[15:0] result;wire overlay;
 metrics_osd #(.DEBOUNCE_CYCLES(3)) osd(.clk(clk),.rstn(rstn),.vs(vs),.de(1'b1),.key_n(1'b1),
  .camera_selected(1'b1),.fusion_enabled(1'b0),.fusion_used(1'b0),.frozen(1'b0),.format2(2'd0),.display_quality(2'd2),
  .c2_status(status),.c2_status_toggle(toggle),.c2_phase(phase),.x(x),.y(y),.pixel(16'h8410),
  .snapshot(86'd0),.snapshot_toggle(1'b0),.result(result),.enabled(),.overlay_active(overlay));
 reg[8:0] index=0;wire[23:0] rom_data;tri1 sda;
 ov5640_reg_rom rom(.reg_index(index),.reg_data(rom_data));
 reg_config #(.PLL_MULTIPLIER(8'h34),.RGB_FORMAT(8'h60)) original(.clk_25M(clk),.sccb_clk(clk),.camera_rstn(rstn),
  .initial_en(1'b0),.reg_conf_done(),.i2c_sclk(),.i2c_sdat(sda),.clock_20k(),.reg_index());
 task boundary;begin @(negedge clk);vs=1;repeat(3)@(negedge clk);vs=0;repeat(3)@(negedge clk);end endtask
 integer n;
 initial begin
  #1;rstn=0;repeat(4)@(negedge clk);rstn=1;
  force original.reg_index=index;index=9'd511;#2;
  for(n=0;n<358;n=n+1)begin index=n;#2;if(rom_data!==original.reg_data)$fatal(1,"ROM DIFFERENCE index=%0d new=%h old=%h",n,rom_data,original.reg_data);end
  release original.reg_index;
  status={8'hab,8'h60,1'b1,1'b0,1'b1};toggle=1;phase=1;repeat(8)@(negedge clk);
  if(osd.c2_visible!==0)$fatal(1,"STATUS CHANGED MIDFRAME");boundary;
  x=32;y=144;#1;if(osd.character!=="1" || !overlay)$fatal(1,"CONFIG FLAG");
  x=80;#1;if(osd.character!=="0")$fatal(1,"ERROR FLAG");
  x=128;#1;if(osd.character!=="6")$fatal(1,"FORMAT HEX HIGH");
  x=144;#1;if(osd.character!=="0")$fatal(1,"FORMAT HEX LOW");
  x=192;#1;if(osd.character!=="1")$fatal(1,"BAR FLAG");
  y=160;x=32;#1;if(osd.character!=="1")$fatal(1,"PHASE FLAG");
  x=80;#1;if(osd.character!=="A")$fatal(1,"RETRY HEX HIGH");
  x=96;#1;if(osd.character!=="B")$fatal(1,"RETRY HEX LOW");
  y=176;#1;if(overlay)$fatal(1,"OSD BOUNDS");
  $display("C2_STATUS_ROM PASS all 358 table slots match baseline, coherent VS-latched config/format/bar/phase/retry diagnostics");$finish;
 end
endmodule
