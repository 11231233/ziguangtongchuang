`timescale 1ns/1ps
module tb_cam_start;
reg clk=0,clk25=0,slow=0,slow_run=0,rstn=0,crst=1,enable=0;
always #10 clk=~clk;always #20 clk25=~clk25;always #25 if(slow_run)slow=~slow;
wire r1,r2,pwdn,init_en,done,scl,raw;wire[8:0]index;tri1 sda;
power_on_delay poweron(.clk_50M(clk),.reset_n(rstn),.camera1_rstn(r1),.camera2_rstn(r2),.camera_pwnd(pwdn),.initial_en(init_en));
reg_config cfg(.clk_25M(clk25),.sccb_clk(slow),.camera_rstn(crst),.initial_en(enable),.reg_conf_done(done),.i2c_sclk(scl),.i2c_sdat(sda),.clock_20k(raw),.reg_index(index));
wire done2,scl2,raw2;wire[8:0]index2;tri1 sda2;
reg_config #(.PLL_MULTIPLIER(8'h34),.RGB_FORMAT(8'h61)) cfg2(.clk_25M(clk25),.sccb_clk(slow),.camera_rstn(crst),.initial_en(enable),.reg_conf_done(done2),.i2c_sclk(scl2),.i2c_sdat(sda2),.clock_20k(raw2),.reg_index(index2));
integer n, writes=0; reg checking=0; reg p_done=0,c_done=0;
always @(posedge cfg.start) if(checking) begin
 #1;
 if(cfg.i2c_data[31:24]!==8'h78) $fatal(1,"CAMERA ADDRESS");
 if(index!==writes) $fatal(1,"CONFIG ORDER");
 if(index==312 && cfg.i2c_data!==32'h78382101) $fatal(1,"HORIZONTAL BINNING");
 if(index==313 && cfg.i2c_data!==32'h78381431) $fatal(1,"X SUBSAMPLE");
 if(index==314 && cfg.i2c_data!==32'h78381531) $fatal(1,"Y SUBSAMPLE");
 if(index==357 && cfg.i2c_data!==32'h78530825) $fatal(1,"RESTORE AUTO CIP");
 if(index2!==index)$fatal(1,"SECOND CONFIG ORDER");
 if(index==156 && cfg2.i2c_data!==32'h78430061)$fatal(1,"CAM2 STANDARD RGB565");
 if(index==309 && cfg2.i2c_data!==32'h78303634)$fatal(1,"SLOW PLL");
 if(index==339 && cfg2.i2c_data!==32'h783a096f)$fatal(1,"SLOW BANDING");
 writes=writes+1;
end
initial begin
 repeat(5)@(negedge clk);
 if(r1!==0||r2!==0||pwdn!==1||init_en!==0)$fatal(1,"POWER RESET UNKNOWN");
 rstn=1;wait(pwdn===0);if(r1!==0||init_en!==0)$fatal(1,"RESET RELEASE ORDER");
 wait(r1===1);if(init_en!==0||r2!==1)$fatal(1,"SCCB STARTED EARLY");
 wait(init_en===1);@(negedge clk);rstn=0;repeat(4)@(negedge clk);
 if(r1!==0||init_en!==0||pwdn!==1)$fatal(1,"POWER RESTART");
 p_done=1;
end
initial begin
 #1;crst=0;#100;
 // SCCB clock is stopped: its state machines must still reset.
 if(index!==0||cfg.start!==0||cfg.u1.cyc_count!==63||cfg.u1.tr_end!==0)$fatal(1,"STOPPED CLOCK RESET");
 crst=1;slow_run=1;repeat(100)@(negedge slow);
 if(index!==0||cfg.start!==0)$fatal(1,"IGNORED POWER SETTLE DELAY");
 enable=1;wait(index>=3);@(negedge slow);slow_run=0;#100;crst=0;#100;
 if(index!==0||cfg.start!==0||cfg.u1.tr_end!==0)$fatal(1,"STOPPED CLOCK RESTART");
 crst=1;checking=1;slow_run=1;wait(done===1);@(negedge slow);
 if(writes!=358 || index!=358 || !done2 || index2!=358) $fatal(1,"CONFIG INCOMPLETE");
 repeat(200)@(negedge slow);if(writes!=358) $fatal(1,"CONFIG DID NOT STOP");
 c_done=1;
end
initial begin wait(p_done&&c_done);$display("CAM_START PASS: defined power/reset order, SCCB waits for enable, async reset while SCCB stopped, all 358 config writes, H binning/subsample pair and automatic CIP restore");$finish;end
initial begin #30000000;$fatal(1,"TIMEOUT CAMERA START");end
endmodule
