"""Independent fixed-point golden vs real streaming LUT/27-stage coordinate RTL."""
from pathlib import Path
import sys,json,hashlib,subprocess,os,datetime
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from rational_lut import build_table,factor_fixed,coordinates_fixed,coefficients
m=json.loads((ROOT/'prototype/candidate.json').read_text(encoding='utf-8'));table=build_table(m)
out=ROOT/'reports'/('lut_rtl_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'));out.mkdir()
rom=(ROOT/'prototype/radial_factor.hex').as_posix()
rng=np.random.default_rng(20261031)
r2=np.concatenate([[-1,0,1,1023,1024,2097151,2097152,2097153],rng.integers(0,2097153,4096)]).astype(np.int64)
f,ok=factor_fixed(table,r2)
def hexfile(name,values,bits=32):
 (out/name).write_text('\n'.join(f'{int(v)&((1<<bits)-1):0{bits//4}x}' for v in values)+'\n')
hexfile('r2.hex',r2);hexfile('f.hex',f);hexfile('range.hex',ok)
tb=r'''
`timescale 1ns/1ps
module tb_lut;
reg clk=0,rstn=0,vi=0;always #5 clk=~clk;reg signed[31:0]r2;
wire vo,range,empty_vo,empty_range;wire signed[31:0]factor;
radial_lut #(.ROM_FILE("ROM")) dut(.clk(clk),.rstn(rstn),.valid_i(vi),.r2_q16(r2),.valid_o(vo),.in_range_o(range),.factor_q16(factor));
radial_lut empty(.clk(clk),.rstn(rstn),.valid_i(vi),.r2_q16(r2),.valid_o(empty_vo),.in_range_o(empty_range),.factor_q16());
reg[31:0]inputs[0:N-1],gold[0:N-1],ranges[0:N-1];integer i,got=0,sent=0,ticks=0;integer launched[0:N-1];
always @(posedge clk)if(rstn)begin ticks<=ticks+1;if(vi)begin launched[sent]<=ticks;sent<=sent+1;end end
always @(negedge clk)if(rstn && vo)begin
 if(got>=N || range!==ranges[got][0] || (range && factor!==gold[got]))$fatal(1,"LUT mismatch %0d actual=%d gold=%d range=%b",got,factor,$signed(gold[got]),range);
 if(ticks-launched[got]!=3)$fatal(1,"LUT latency");
 if(empty_vo!==1 || empty_range!==0)$fatal(1,"Empty ROM accepted");got=got+1;
end
initial begin
 $readmemh("R2",inputs);$readmemh("GOLD",gold);$readmemh("RANGE",ranges);
 repeat(5)@(negedge clk);rstn=1;
 for(i=0;i<N;i=i+1)begin
  @(negedge clk);vi=0;if(i%9==0)repeat(2)@(negedge clk);
  r2=inputs[i];vi=1;
 end
 @(negedge clk);vi=0;repeat(8)@(negedge clk);
 if(got!=N || sent!=N)$fatal(1,"LUT incomplete");
 $display("RADIAL_LUT PASS N samples, 3 clocks, bubbles, endpoints, out-of-domain flags and empty-ROM fail-closed");$finish;
end
initial begin #1000000;$fatal(1,"LUT timeout");end
endmodule
'''
import re
tb=re.sub(r'\bN\b',str(len(r2)),tb)
for key,value in [('ROM',rom),('R2',(out/'r2.hex').as_posix()),('GOLD',(out/'f.hex').as_posix()),('RANGE',(out/'range.hex').as_posix())]:tb=tb.replace('"'+key+'"','"'+value+'"')
(out/'lut_tb.v').write_text(tb)
ys,xs=np.mgrid[0:720:23,0:1280:31];points=np.stack([xs.ravel(),ys.ravel()],axis=1)
points=np.vstack([points,[[0,0],[1279,0],[0,719],[1279,719],[640,360]]]);count=len(points)
phases=[(angle,enabled) for enabled in (True,False) for angle in (-20,0,20)]
fields=('A','B','C','D','E','F','k1','k2','p1','p2','fx','fy','cx','cy');coef=[];ux=[];vy=[];inside=[];xy=[]
for angle,enabled in phases:
 c=coefficients(m,angle);coef.append(sum((c[k]&0xffffffff)<<(32*i) for i,k in enumerate(fields)))
 u,v,valid=coordinates_fixed(m,table,angle,points[:,0],points[:,1],enabled)
 ux.extend(u);vy.extend(v);inside.extend(valid);xy.extend((points[:,0]<<16)|points[:,1])
hexfile('coeff.hex',coef,448);hexfile('xy.hex',xy);hexfile('u.hex',ux);hexfile('v.hex',vy);hexfile('in.hex',inside)
coord=r'''
`timescale 1ns/1ps
module tb_coord_lut;
reg clk=0,rstn=0,vi=0,en=0;always #5 clk=~clk;reg[447:0]c;reg[15:0]x=0,y=0;
wire vo,hit_frame;wire signed[31:0]u,v;wire signed[15:0]ui,vi_int;wire[7:0]uf,vf;
coord_map #(.W(1296),.H(972),.AFFINE_FRAC_BITS(24),.RADIAL_MODEL_LUT(1),.RADIAL_LUT_FILE("ROM")) dut(
.clk(clk),.rstn(rstn),.A(c[31:0]),.B(c[63:32]),.C(c[95:64]),.D(c[127:96]),.E(c[159:128]),.F(c[191:160]),
.k1(c[223:192]),.k2(c[255:224]),.p1(c[287:256]),.p2(c[319:288]),.fx(c[351:320]),.fy(c[383:352]),.cx(c[415:384]),.cy(c[447:416]),
.valid_i(vi),.x_i(x),.y_i(y),.lut_enable(en),.valid_o(vo),.u_q16(u),.v_q16(v),.in_frame(hit_frame),.u_int(ui),.v_int(vi_int),.u_frac(uf),.v_frac(vf));
reg[447:0]coeff[0:5];reg[31:0]xy[0:TOTAL-1],gu[0:TOTAL-1],gv[0:TOTAL-1],gi[0:TOTAL-1];
integer p,i,n,got=0,sent=0,ticks=0;integer launched[0:TOTAL-1];
always @(posedge clk)if(rstn)begin ticks<=ticks+1;if(vi)begin launched[sent]<=ticks;sent<=sent+1;end end
always @(negedge clk)if(rstn && vo)begin
 if(got>=TOTAL || u!==gu[got] || v!==gv[got] || hit_frame!==gi[got][0])$fatal(1,"COORD LUT mismatch %0d actual %d %d expected %d %d in=%b",got,u,v,$signed(gu[got]),$signed(gv[got]),hit_frame);
 if(ticks-launched[got]!=27)$fatal(1,"Coordinate latency changed");
 if(ui!==u[31:16] || vi_int!==v[31:16] || uf!==u[15:8] || vf!==v[15:8])$fatal(1,"Fraction alignment");got=got+1;
end
initial begin
 $readmemh("COEFF",coeff);$readmemh("XY",xy);$readmemh("GU",gu);$readmemh("GV",gv);$readmemh("GI",gi);
 repeat(5)@(negedge clk);rstn=1;
 for(p=0;p<6;p=p+1)begin
  c=coeff[p];en=p<3;repeat(2)@(negedge clk);
  for(i=0;i<COUNT;i=i+1)begin
   @(negedge clk);vi=0;if(i%11==0)repeat(2)@(negedge clk);
   n=p*COUNT+i;{x,y}=xy[n];vi=1;
  end
  @(negedge clk);vi=0;repeat(35)@(negedge clk);
 end
 if(got!=TOTAL || sent!=TOTAL)$fatal(1,"Coordinate incomplete");
 $display("COORD_RATIONAL_LUT PASS TOTAL coordinates, +/-20 and 0 degrees, COR and true RAW, 27-stage alignment, bubbles and fixed-point pixels exact");$finish;
end
initial begin #3000000;$fatal(1,"Coordinate timeout");end
endmodule
'''
for name,value in [('TOTAL',len(xy)),('COUNT',count)]:coord=re.sub(r'\b'+name+r'\b',str(value),coord)
for name,value in [('ROM',rom),('COEFF',(out/'coeff.hex').as_posix()),('XY',(out/'xy.hex').as_posix()),('GU',(out/'u.hex').as_posix()),('GV',(out/'v.hex').as_posix()),('GI',(out/'in.hex').as_posix())]:coord=coord.replace('"'+name+'"','"'+str(value)+'"')
(out/'coord_tb.v').write_text(coord)
env=os.environ.copy();env.update(PATHEXT='.COM;.EXE;.BAT;.CMD',COMSPEC=r'C:\Windows\System32\cmd.exe')
results=[]
for name,top,tb_file,sources in [('lut','tb_lut','lut_tb.v',['radial_lut.v']),('coord','tb_coord_lut','coord_tb.v',['radial_lut.v','coord_map.v'])]:
 binary=out/(name+'.vvp');files=[ROOT/'rtl/warp'/n for n in sources]+[out/tb_file]
 r=subprocess.run(['D:/iverilog/bin/iverilog.exe','-g2012','-s',top,'-o',str(binary),*[str(f) for f in files]],cwd=ROOT,env=env,capture_output=True,text=True)
 (out/(name+'_compile.log')).write_text(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr
 r=subprocess.run(['D:/iverilog/bin/vvp.exe',str(binary)],cwd=ROOT,env=env,capture_output=True,text=True,timeout=120)
 body=r.stdout+r.stderr;(out/(name+'.log')).write_text(body)
 ok=r.returncode==0 and 'PASS' in body and not any(t in body for t in ['FATAL','ERROR','FAIL','TIMEOUT'])
 results.append(dict(name=name,passed=ok));print(body[-2000:],flush=True)
 if not ok:break
report=dict(passed=len(results)==2 and all(r['passed'] for r in results),tests=results,radial_samples=len(r2),coordinate_samples=len(xy),
 hardware_tested=False,model_certified=False,pds_built=False,source_sha256={str(f.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(f.read_bytes()).hexdigest() for f in [ROOT/'rtl/warp/radial_lut.v',ROOT/'rtl/warp/coord_map.v',ROOT/'rtl/warp/warp_frame.v']})
(out/'result.json').write_text(json.dumps(report,indent=2));print(out);raise SystemExit(0 if report['passed'] else 1)
