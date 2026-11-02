"""Generate board-local rotation coefficients; never reads a new camera model."""
from pathlib import Path
import math,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
def row(angle,zoom):
 a,c,f=[(126,-80660,-45371),(101,-64528,-36297),(82,-52429,-29491)][zoom]
 t=math.radians(angle);co=math.cos(t);si=math.sin(t)
 # Rotate OUTPUT sampling coordinates about (640,360), then apply original affine.
 return [round(a*co*256),round(-a*si*256),round(c+a*(640-640*co+360*si)),
         round(a*si*256),round(a*co*256),round(f+a*(360-640*si-360*co))]
lines=['`timescale 1ns/1ps','module key_angle_rom(input wire clk,input wire [10:0] index,output reg [191:0] coeff,output reg [12:0] bcd);','always @(posedge clk)begin','case(index)']
rows=[]
for zoom in range(3):
 for angle in range(-180,180):
  values=row(angle,zoom);assert all(-131072<=values[k]<131072 for k in [0,1,3,4])
  packed=sum((v&0xffffffff)<<(32*(5-i)) for i,v in enumerate(values))
  n=abs(angle);bcd=((angle<0)<<12)|((n//100)<<8)|(((n//10)%10)<<4)|(n%10)
  lines.append(f"11'd{zoom*360+angle+180}:begin coeff<=192'h{packed:048x};bcd<=13'h{bcd:04x};end")
  rows.append(dict(angle=angle,zoom=zoom,coeff=values,bcd=bcd))
zero=sum((v&0xffffffff)<<(32*(5-i)) for i,v in enumerate(row(0,0)))
lines+=['default:begin coeff<=192\'h'+f'{zero:048x}'+";bcd<=0;end",'endcase','end','endmodule']
(ROOT/'rtl/common/key_angle_rom.v').write_text('\n'.join(lines)+'\n',encoding='ascii')
(ROOT/'targets/key_angle_rom.json').write_text(json.dumps(dict(affine_slope_frac_bits=24,translation_frac_bits=16,rows=rows),indent=2),encoding='utf-8')
print('Generated',len(rows),'angle/zoom settings; zero-degree coefficients preserve original mapping exactly')
if __name__=='__main__':pass
