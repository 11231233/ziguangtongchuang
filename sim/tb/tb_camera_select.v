`timescale 1ns/1ps
module tb_camera_select;
reg clk=0,rstn=0,key_n=1;always #5 clk=~clk;
reg v1=0,d1=0,v2=0,d2=0;reg [15:0]p1=16'h1111,p2=16'h2222;
wire vs,de,selected,waiting;wire [15:0]pix;
camera_select #(.DEBOUNCE_CYCLES(3)) dut(.clk(clk),.rstn(rstn),.key_n(key_n),
 .vs1(v1),.de1(d1),.pix1(p1),.vs2(v2),.de2(d2),.pix2(p2),
 .vs(vs),.de(de),.pix(pix),.selected(selected),.waiting(waiting));
task tick;begin @(negedge clk);#1;end endtask
task press;begin key_n=0;repeat(12)tick;key_n=1;repeat(12)tick;end endtask
integer seen1=0,seen2=0;reg have_marker=0,marker_cam=0;
always @(posedge clk)if(rstn)begin
 if(vs)begin have_marker=1;marker_cam=dut.requested;end
 if(de)begin
  if(!have_marker||selected!==marker_cam)$fatal(1,"PIXELS BEFORE CORRECT VS");
  if(selected)begin if(pix!==16'h2222)$fatal(1,"CAM2 MIXED PIXELS");seen2=seen2+1;end
  else begin if(pix!==16'h1111)$fatal(1,"CAM1 MIXED PIXELS");seen1=seen1+1;end
 end
end
initial begin
 repeat(4)tick;rstn=1;d1=1;d2=1;repeat(4)tick;
 if(de||!waiting)$fatal(1,"START BEFORE VS");
 v2=1;tick;v2=0;if(de)$fatal(1,"UNSELECTED MARKER ACCEPTED");
 v1=1;tick;v1=0;repeat(4)tick;if(!de||selected)$fatal(1,"CAM1 START");
 key_n=0;tick;key_n=1;repeat(10)tick;if(dut.requested)$fatal(1,"BOUNCE");
 press;if(!waiting||de)$fatal(1,"MUST MUTE OLD FRAME");
 v1=1;tick;v1=0;repeat(3)tick;if(de||vs)$fatal(1,"OLD CAMERA LEAK");
 // Absent target: keep output muted and old published framebuffer can stay visible.
 repeat(30)tick;if(de||!waiting)$fatal(1,"MISSING CAMERA LEAK");
 v2=1;tick;v2=0;repeat(5)tick;if(!selected||!de||waiting)$fatal(1,"CAM2 START");
 key_n=0;repeat(40)tick;if(dut.requested)$fatal(1,"HELD KEY REPEATED");
 key_n=1;repeat(12)tick;v1=1;tick;v1=0;repeat(5)tick;
 if(selected||!de||waiting)$fatal(1,"RETURN CAM1");
 if(seen1<5||seen2<5)$fatal(1,"BOTH CAMERAS NOT SEEN");
 $display("CAMERA_SELECT PASS: debounce, held key, both sources, target VS gating, absent camera, no mixed pixels");$finish;
end
initial begin #100000;$fatal(1,"TIMEOUT CAMERA_SELECT");end
endmodule
