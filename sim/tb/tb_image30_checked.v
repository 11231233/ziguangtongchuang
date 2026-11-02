`timescale 1ns/1ps
module tb_image30_checked;
 reg clk=0,rstn=0,en=0,bar=0,nack_all=0;always #5 clk=~clk;
 tri1 sda;wire scl,ok,fault,bactive;wire[7:0] fmt,retries;
 ov5640_checked_config #(.TICK_DIV(2),.DUMMY_DELAY(3),.RESET_DELAY(12),.MAX_RETRIES(3),.PLL_MULTIPLIER(8'h69),.VERIFY_PLL(1),.IMAGE_PROFILE(1)) dut(
  .clk(clk),.rstn(rstn),.initial_en(en),.bar_request(bar),.config_ok(ok),.fault(fault),.bar_active(bactive),
  .format_readback(fmt),.retry_total(retries),.scl(scl),.sda(sda));
 sccb_sensor_model sensor(.scl(scl),.sda(sda),.nack_all(nack_all),.nack_mask(4'd0),
  .nack_format_once(1'b1),.bad_format_read_once(1'b1));
 integer previous_writes,bad_index;reg[23:0] bad_word;
 initial begin
  #1;rstn=0;repeat(4)@(negedge clk);rstn=1;repeat(20)@(negedge clk);
  if(sensor.starts || ok)$fatal(1,"INITIAL ENABLE IGNORED");
  en=1;wait(ok||fault);@(negedge clk);
  if(!ok || fault || fmt!==8'h60 || retries!==2)$fatal(1,"CONFIG/RETRY fmt=%h retries=%d",fmt,retries);
  if(sensor.writes!=280)$fatal(1,"WRITTEN CONFIG COUNT %0d",sensor.writes);
  if(sensor.memory[16'h501f]!==1 || sensor.memory[16'h4740]!==8'h20 || sensor.memory[16'h4745]!==0)
   $fatal(1,"FINAL GUARDS");
  if(sensor.memory[16'h3036]!==8'h69 || sensor.memory[16'h3808]!==5 || sensor.memory[16'h380b]!==8'hd0)
   $fatal(1,"PLL/SIZE CHANGED");
  if(sensor.memory[16'h3a00]!==8'h78 || sensor.memory[16'h3406]!==0 || sensor.memory[16'h3503]!==0 || sensor.memory[16'h3a19]!==8'h80 || sensor.memory[16'h5308]!==8'h25 || sensor.memory[16'h3c00]!==8'h04 || sensor.memory[16'h3c01]!==8'h34)
   $fatal(1,"AEC/AWB/GAIN GUARDS");
  if(sensor.reads<25)$fatal(1,"IMAGE PROFILE READBACK OMITTED");
  bar=1;wait(bactive);@(negedge clk);if(sensor.memory[16'h503d]!==8'h80)$fatal(1,"BAR ON");
  bar=0;wait(!bactive);@(negedge clk);if(sensor.memory[16'h503d]!==0)$fatal(1,"BAR OFF");
  if(sensor.memory[16'h3035]!==8'h21 || sensor.memory[16'h3a09]!==8'hde || sensor.memory[16'h3a0b]!==8'hb8 || sensor.memory[16'h3a0e]!==3 || sensor.memory[16'h3a0d]!==4)$fatal(1,"30FPS TIMING/BANDING");
  if(sensor.reads<10)$fatal(1,"PLL READBACK OMITTED");
  previous_writes=sensor.writes;repeat(100)@(negedge clk);
  if(sensor.writes!=previous_writes)$fatal(1,"READY REPEATED WRITES");
  // A sensor accepting writes but returning the wrong PLL value must never open capture.
  rstn=0;repeat(5)@(negedge clk);rstn=1;
  wait(dut.state==6 && dut.verify_index==8);
  sensor.memory[16'h3036]=8'h34;
  wait(fault);@(negedge clk);
  if(ok || retries!==4)$fatal(1,"BAD PLL READBACK DID NOT STOP CAPTURE");
  // Every final image-profile register must block capture on bad readback.
  for(bad_index=9;bad_index<=23;bad_index=bad_index+1)begin
   rstn=0;repeat(5)@(negedge clk);rstn=1;
   wait(dut.state==6 && dut.verify_index==bad_index);
   bad_word=dut.image_write(bad_index-9);
   sensor.memory[bad_word[23:8]]=bad_word[7:0]^8'h01;
   wait(fault);@(negedge clk);
   if(ok || retries!==4)$fatal(1,"BAD IMAGE READBACK ALLOWED index=%0d",bad_index);
  end
  rstn=0;nack_all=1;repeat(5)@(negedge clk);rstn=1;wait(fault);@(negedge clk);
  if(ok || retries!==4)$fatal(1,"PERMANENT NACK NOT LATCHED");
  previous_writes=sensor.starts;repeat(1000)@(negedge clk);
  if(sensor.starts!=previous_writes)$fatal(1,"FAULT RETRY LOOP");
  $display("IMAGE30_CHECKED PASS complete ROM sequence, dummy skip, transient ACK/readback retries, PLL/size guards, native bars, permanent fault stops");$finish;
 end
 initial begin #200000000;$fatal(1,"C2 CONFIG TIMEOUT state=%d index=%d master=%d",dut.state,dut.index,dut.bus.state);end
endmodule
