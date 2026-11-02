`timescale 1ns/1ps
module tb_stereo_fusion;
`include "stereo_expected.vh"
reg clk=0,rstn=0,start=0;always #5 clk=~clk;reg[1:0]mode=0;
wire busy,done,vs,de;wire[15:0]pixel;wire[20:0]fused;wire req,ready,rdone,valid;wire[27:0]addr;wire[7:0]beats;
reg[15:0]left[0:1151],right[0:1151],gold[0:1151];reg[31:0]rng=32'h12345678;
always @(posedge clk)rng<={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
reg[255:0]data;
stereo_fusion #(.WIDTH(384),.HEIGHT(3)) dut(.clk(clk),.rstn(rstn),.start(start),.left_base(28'd0),.right_base(28'd4096),.mode(mode),.busy(busy),.done(done),.vs(vs),.de(de),.pixel(pixel),.fused_pixels(fused),.r_req(req),.r_addr(addr),.r_beats(beats),.r_ready(ready),.r_done(rdone),.r_valid(valid),.r_data(data));
reg rb=0;integer ra=0,ri=0,rn=0,tail=0,q;
assign ready=!rb&&rng[0];assign valid=rb&&ri<rn&&rng[2];assign rdone=rb&&tail==1;
always @*begin data=0;if(rb)for(integer j=0;j<16;j=j+1)begin
 if(ra>=4096)data[j*16+:16]=right[(ra-4096)*2+ri*16+j];else data[j*16+:16]=left[ra*2+ri*16+j];end end
always @(posedge clk)begin
 if(req&&ready)begin if(addr%8||beats<1||beats>16)$fatal(1,"READ BURST");rb<=1;ra<=addr;ri<=0;rn<=beats;end
 if(valid)begin ri<=ri+1;if(ri==rn-1)tail<=4;end
 if(tail>0)begin tail<=tail-1;if(tail==1)rb<=0;end
end
integer n=0,round_no,cycles=0;reg marker=0;reg[15:0]expected;
always @(posedge clk)if(rstn)begin
 if(vs)begin n=0;marker=1;end
 if(de)begin
 if(!marker||n>=1152)$fatal(1,"STREAM LENGTH");
 case(mode)0:expected=gold[n];1:expected=left[n];2:expected=right[n];endcase
 if(pixel!==expected)$fatal(1,"FUSION PIXEL mode=%0d n=%0d got=%h exp=%h",mode,n,pixel,expected);
 n=n+1;end
end
initial begin
 $readmemh("sim/out/stereo_left.hex",left);$readmemh("sim/out/stereo_right.hex",right);$readmemh("sim/out/stereo_expect.hex",gold);
 repeat(5)@(negedge clk);rstn=1;
 for(round_no=0;round_no<3;round_no=round_no+1)begin
 mode=round_no;@(negedge clk);start=1;@(negedge clk);start=0;
 cycles=0;while(!done&&cycles<100000)begin @(negedge clk);cycles=cycles+1;end
 if(!done||busy||n!=1152)$fatal(1,"FUSION INCOMPLETE");
 if((mode==0&&fused!=EXPECT_FUSED)||(mode!=0&&fused!=0))$fatal(1,"FUSED COUNT got=%d exp=%d",fused,EXPECT_FUSED);
 repeat(5)@(negedge clk);
 end
 $display("STEREO_FUSION PASS: shifted pair registration, actual averaging, purple occlusion and flat fallback, random DDR stalls, three modes exact");$finish;
end
initial begin #3000000;$fatal(1,"STEREO FUSION TIMEOUT");end
endmodule
