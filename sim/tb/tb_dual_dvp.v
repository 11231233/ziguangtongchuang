`timescale 1ns/1ps
module tb_dual_dvp;
reg clk=0,c1=0,c2=0,rstn=0,key_n=1;always #5 clk=~clk;always #6 c1=~c1;always #8 c2=~c2;
reg v1=0,h1=0,v2=0,h2=0;reg [7:0]d1=0,d2=0;
wire [15:0]p1,p2,p;wire de1,vs1,de2,vs2,de,vs,selected,waiting;
dvp_capture cap1(.cam_pclk(c1),.rstn(rstn),.vs(v1),.hs(h1),.d(d1),.ddr_clk(clk),.ddr_rstn(rstn),.pix(p1),.de(de1),.vs_o(vs1));
dvp_capture cap2(.cam_pclk(c2),.rstn(rstn),.vs(v2),.hs(h2),.d(d2),.ddr_clk(clk),.ddr_rstn(rstn),.pix(p2),.de(de2),.vs_o(vs2));
camera_select #(.DEBOUNCE_CYCLES(3)) mux(.clk(clk),.rstn(rstn),.key_n(key_n),.vs1(vs1),.de1(de1),.pix1(p1),.vs2(vs2),.de2(de2),.pix2(p2),.vs(vs),.de(de),.pix(p),.selected(selected),.waiting(waiting));
integer f1,i1,f2,i2,expected=0,n1=0,n2=0,frames=0;reg armed=0;
initial begin wait(rstn);for(f1=0;f1<40;f1=f1+1)begin
 @(negedge c1);v1=1;repeat(3)@(negedge c1);v1=0;repeat(3)@(negedge c1);
 for(i1=0;i1<16;i1=i1+1)begin h1=1;d1=8'ha1;@(negedge c1);d1=i1;@(negedge c1);end
 h1=0;repeat(10)@(negedge c1);
end end
initial begin wait(rstn);repeat(7)@(negedge c2);for(f2=0;f2<40;f2=f2+1)begin
 @(negedge c2);v2=1;repeat(3)@(negedge c2);v2=0;repeat(3)@(negedge c2);
 for(i2=0;i2<16;i2=i2+1)begin h2=1;d2=8'hb2;@(negedge c2);d2=i2;@(negedge c2);end
 h2=0;repeat(10)@(negedge c2);
end end
always @(posedge clk)if(rstn)begin
 if(vs)begin armed=1;expected=0;frames=frames+1;end
 if(de)begin
  if(!armed||p[15:8] !== (selected?8'hb2:8'ha1)||p[7:0]!==expected[7:0])$fatal(1,"DUAL_DVP MIXED/UNORDERED PIXELS p=%h expected=%0d selected=%b",p,expected,selected);
  expected=expected+1;if(selected)n2=n2+1;else n1=n1+1;
 end
end
task press;begin @(negedge clk);key_n=0;repeat(15)@(negedge clk);key_n=1;repeat(15)@(negedge clk);end endtask
initial begin repeat(5)@(negedge clk);rstn=1;repeat(200)@(negedge clk);press;
 repeat(350)@(negedge clk);if(!selected)$fatal(1,"CAM2 NOT ACTIVE");press;
 repeat(300)@(negedge clk);if(selected||n1<32||n2<32||frames<4)$fatal(1,"DUAL COVERAGE");
 $display("DUAL_DVP PASS: unrelated PCLKs, independent FIFOs, simultaneous streams, mid-frame switch, ordered bytes and target VS");$finish;
end
initial begin #100000;$fatal(1,"DUAL_DVP TIMEOUT");end
endmodule
