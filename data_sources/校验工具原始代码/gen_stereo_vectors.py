from pathlib import Path
import json
p=Path(__file__).resolve().parents[1]/'sim/out';p.mkdir(parents=True,exist_ok=True)
w,h=384,3
L=[(((x*7+y*3)%28)<<11)|(((x*11+y*5)%56)<<5)|((x*3+y*13)%28) for y in range(h) for x in range(w)]
for y in range(h):
 for x in range(32,64):L[y*w+x]=(12<<11)|(24<<5)|12
R=[]
for y in range(h):
 for x in range(w):
  a=L[y*w+max(0,x-8)];r=(a>>11)&31;g=(a>>5)&63;b=a&31
  R.append((r<<11)|(min(63,g+2)<<5)|b if not 64<=x<96 else 0xf81f)
def lum(a):return (2*((a>>11)&31)+2*((a>>5)&63)+2*(a&31))//4
def close(a,b):return abs(((a>>11)&31)-((b>>11)&31))<=3 and abs(((a>>5)&63)-((b>>5)&63))<=8 and abs((a&31)-(b&31))<=3
def avg(a,b):return (((((a>>11)&31)+((b>>11)&31)+1)//2)<<11)|(((((a>>5)&63)+((b>>5)&63)+1)//2)<<5)|(((a&31)+(b&31)+1)//2)
out=[];fused=0
for y in range(h):
 for bx in range(0,w,32):
  taps=[bx+4+8*i for i in range(4)];costs=[]
  for d in range(-32,33,4):
   cost=sum(abs(lum(L[y*w+x])-lum(R[y*w+x+d])) for x in taps) if all(0<=x+d<w for x in taps) else 1023
   costs.append((cost,d))
  best,dx=min(costs,key=lambda a:a[0]);second=sorted(v for v,d in costs)[1]
  texture=sum(abs(lum(L[y*w+taps[i]])-lum(L[y*w+taps[i-1]])) for i in range(1,4))
  ok=best<=24 and second>=best+4 and texture>=8
  for x in range(bx,bx+32):
   a=L[y*w+x];j=x+dx
   if ok and 0<=j<w and close(a,R[y*w+j]):out.append(avg(a,R[y*w+j]));fused+=1
   else:out.append(a)
assert fused>0 and out!=L and out!=R
for name,values in [('stereo_left',L),('stereo_right',R),('stereo_expect',out)]:
 (p/(name+'.hex')).write_text('\n'.join(f'{v:04x}' for v in values))
(p/'stereo_expected.vh').write_text(f'localparam EXPECT_FUSED={fused};\n')
print('STEREO reference',len(out),'pixels, fused',fused,'nonzero shift / purple occlusion / flat ambiguity')
