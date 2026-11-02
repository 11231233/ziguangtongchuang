`timescale 1ns/1ps
module tb_margin_footer;
reg clk=0,pix=0,rstn=0,start=0,vs=0,de=1,slot=0;always #5 clk=~clk;always #7 pix=~pix;
reg[223:0]payload=0;wire[255:0]metadata;wire ready;
reg[255:0]slot0=0,slot1=0;reg[11:0]x=0,y=712;wire[15:0]result;wire overlay;
margin_metadata crc(.clk(clk),.rstn(rstn),.start(start),.payload(payload),.metadata(metadata),.ready(ready));
margin_footer footer(.clk(pix),.rstn(rstn),.vs(vs),.de(de),.visible_slot(slot),.slot0(slot0),.slot1(slot1),.x(x),.y(y),.pixel(16'h1234),.result(result),.overlay(overlay));
reg[255:0]expected[0:3];reg[255:0]prior_meta;reg[2047:0]input_path,output_path;integer fd,p,i,r;
initial begin
 if(!$value$plusargs("EXPECTED=%s",input_path)||!$value$plusargs("BITS=%s",output_path))$fatal(1,"Missing fixture");
 $readmemh(input_path,expected);fd=$fopen(output_path,"w");
 repeat(5)@(negedge clk);rstn=1;
 for(p=0;p<4;p=p+1)begin
  @(negedge clk);payload=expected[p][255:32];start=1;@(negedge clk);start=0;
  repeat(100)@(negedge clk);if(ready)$fatal(1,"Premature CRC completion");
  wait(ready);@(negedge clk);if(metadata!==expected[p])$fatal(1,"Footer CRC/ordering page %0d",p);
  prior_meta=footer.visible;if(p%2)slot1=metadata;else slot0=metadata;slot=p%2;
  repeat(6)@(negedge pix);if(footer.visible!==prior_meta)$fatal(1,"Metadata changed mid-display-frame");
  vs=1;repeat(4)@(negedge pix);vs=0;repeat(3)@(negedge pix);
  if(footer.visible!==metadata)$fatal(1,"Selected result slot metadata lost");
  y=712;
  for(i=0;i<256;i=i+1)begin
   x=i*4+2;repeat(2)@(negedge pix);#1;
   if(!overlay || result!==(expected[p][255-i]?16'hffff:16'd0))$fatal(1,"Barcode bit %0d page %0d",i,p);
   $fdisplay(fd,"%01x",result==16'hffff);
  end
  y=688;x=112;repeat(2)@(negedge pix);#1;if(footer.character!==8'd48+p)$fatal(1,"Human page label");
  x=160;#1;if(footer.character!=="1")$fatal(1,"Frozen label");
  x=320;#1;if(footer.character!=="A")$fatal(1,"Frame ID hex label");
  y=100;x=100;repeat(2)@(negedge pix);#1;if(overlay || result!==16'h1234)$fatal(1,"Footer corrupts raw ROI");
 end
 $fclose(fd);$display("MARGIN_FOOTER PASS CRC, four result-slot tags, VS-only publication, async clocks, all 1024 barcode bits and raw ROI passthrough");$finish;
end
initial begin #1000000;$fatal(1,"Timeout");end
endmodule
