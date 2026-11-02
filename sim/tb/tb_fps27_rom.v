`timescale 1ns/1ps
module tb_fps27_rom;
 reg [8:0] index=0;wire [23:0] word;
 ov5640_reg_rom #(.PLL_MULTIPLIER(8'h60),.RGB_FORMAT(8'h60)) dut(.reg_index(index),.reg_data(word));
 integer n;
 initial begin
  for(n=0;n<358;n=n+1)begin index=n;#1;if(word!==24'hffffff)$display("REG %06h",word);end
  $display("FPS27_ROM PASS");$finish;
 end
endmodule
