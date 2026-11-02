`timescale 1ns/1ps
module tb_angle_osd;
reg srcclk=0,clk=0;always #5 srcclk=~srcclk;always #7 clk=~clk;
reg rstn=0,vs=0;reg [11:0]x=80;reg[12:0]bcd=0;reg toggle=0;
wire[15:0]result;wire overlay,en;
metrics_osd #(.SHOW_ANGLE(1),.SINGLE_CAMERA(1)) dut(.clk(clk),.rstn(rstn),.vs(vs),.de(1'b1),.key_n(1'b1),
.camera_selected(1'b0),.fusion_enabled(1'b0),.fusion_used(1'b0),.frozen(1'b0),.format2(2'd0),.display_quality(2'd2),
.probe(205'd0),.c2_status(19'd0),.c2_status_toggle(1'b0),.c2_phase(1'b0),.overlay_active(overlay),
.x(x),.y(12'd128),.pixel(16'd0),.snapshot(86'd0),.snapshot_toggle(1'b0),.angle_bcd(bcd),.angle_toggle(toggle),.result(result),.enabled(en));
reg[12:0]old;
task display_angle(input[12:0]value);begin
 old=dut.angle_visible;
 @(negedge srcclk);bcd=value;toggle=!toggle;
 repeat(8)@(negedge clk);
 if(dut.angle_visible!==old)$fatal(1,"Mid-frame angle display changed");
 vs=1;@(negedge clk);vs=0;@(negedge clk);
 if(dut.angle_visible!==value)$fatal(1,"CDC/VS commit wrong");
 x=80;#1;if(dut.character!=="A")$fatal(1,"Angle label");
 x=112;#1;if(dut.character!==(value[12]?8'd45:8'd43))$fatal(1,"Sign");
 x=128;#1;if(dut.character!==8'd48+value[11:8])$fatal(1,"Hundreds");
 x=144;#1;if(dut.character!==8'd48+value[7:4])$fatal(1,"Tens");
 x=160;#1;if(dut.character!==8'd48+value[3:0])$fatal(1,"Ones");
end endtask
initial begin
 repeat(5)@(negedge clk);rstn=1;
 display_angle(13'h0008);display_angle(13'h1008);display_angle(13'h1180);display_angle(13'h0179);display_angle(13'h0000);
 if(dut.font(8'd43)==64'd0)$fatal(1,"Plus glyph missing");
 $display("ANGLE_OSD PASS: unrelated source/pixel clocks, stable bus/toggle capture, VS-only publish, signed 3-digit display");$finish;
end
initial begin #10000;$fatal(1,"Timeout");end
endmodule
