`timescale 1ns/1ps
// Behavioral register bank for bus protocol tests, not an OV5640 ISP model.
module sccb_sensor_model(input wire scl,inout wire sda,input wire nack_all,
 input wire [3:0] nack_mask,input wire nack_format_once,bad_format_read_once);
 reg low=0;assign sda=low?1'b0:1'bz;
 reg [7:0] memory[0:65535];reg [15:0] pointer=0;
 integer writes=0,reads=0,starts=0,stops=0,i;
 reg injected_nack=0,injected_bad=0;event started,stopped;
 reg [7:0] a,hi,lo,value;reg got_data,accepted;integer byte_number;
 initial begin for(i=0;i<65536;i=i+1)memory[i]=0;memory[16'h300a]=8'h56;memory[16'h300b]=8'h40;end
 always @(negedge sda)if(scl===1'b1)begin starts=starts+1;->started;end
 always @(posedge sda)if(scl===1'b1)begin stops=stops+1;->stopped;end
 task receive_byte(output reg[7:0] v);
  integer b;begin v=0;for(b=7;b>=0;b=b-1)begin @(posedge scl);v[b]=sda;end end
 endtask
 task ack(input integer n);
  reg reject;begin
   reject=nack_all || nack_mask[n] || (nack_format_once && !injected_nack && n==3 && pointer==16'h4300);
   if(nack_format_once && !injected_nack && n==3 && pointer==16'h4300)injected_nack=1;
   if(reject)accepted=0;
   @(negedge scl);low=!reject;@(posedge scl);@(negedge scl);low=0;
  end
 endtask
 task transmit_byte(input [7:0] v);
  integer b;begin
   for(b=7;b>=0;b=b-1)begin low=!v[b];@(posedge scl);@(negedge scl);end
   low=0;@(posedge scl);if(sda!==1'b1)$fatal(1,"MASTER DID NOT NACK LAST READ BYTE");@(negedge scl);
  end
 endtask
 initial forever begin
  @started;low=0;accepted=1;receive_byte(a);ack(0);
  if(a==8'h78)begin
   receive_byte(hi);ack(1);receive_byte(lo);pointer={hi,lo};ack(2);got_data=0;
   fork: data_or_stop
    begin receive_byte(value);got_data=1;end
    begin @stopped;end
   join_any
   disable data_or_stop;
   if(got_data)begin
    ack(3);
    if(accepted)begin memory[pointer]=value;writes=writes+1;if(pointer==16'hffff)$fatal(1,"DUMMY SLOT WRITTEN ON BUS");end
    @stopped;
   end
  end else if(a==8'h79)begin
   value=memory[pointer];
   if(bad_format_read_once && !injected_bad && pointer==16'h4300)begin value=8'h61;injected_bad=1;end
   transmit_byte(value);reads=reads+1;@stopped;
  end else $fatal(1,"BAD DEVICE ADDRESS %h",a);
  low=0;
 end
endmodule
