"""Full 1280x688 raw viewport from padded 1296x972 source; modeled DDR."""
from pathlib import Path
import argparse,datetime,json,hashlib,subprocess,os,re,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from margin_geometry import load
ap=argparse.ArgumentParser();ap.add_argument('--page',type=int,choices=range(4),default=3);a=ap.parse_args()
g=load();rx,ry=g['raw_view_offsets'][a.page]
out=ROOT/'reports'/('margin_view_'+str(a.page)+'_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'));out.mkdir()
coeff=dict(A=32768,B=0,C=rx*128,D=0,E=32768,F=ry*128,k1=0,k2=0,p1=0,p2=0,fx=33554432,fy=33554432,cx=0,cy=0)
(out/'frame_coef.vh').write_text('\n'.join('localparam signed[31:0] '+k.upper()+f"=32'sd{v};" for k,v in coeff.items())+'\n')
y,x=np.mgrid[0:688,0:1280];x=x+rx;y=y+ry
gold=(((x*13+y*7)%32)<<11)|(((x+y*3)%64)<<5)|((x*3+y*5)%32)
(out/'full_expect.hex').write_text('\n'.join(f'{int(p):04x}' for p in gold.flat)+'\n')
text=(ROOT/'sim/tb/tb_full.v').read_text().replace('sim/out/',out.as_posix()+'/')
text=text.replace('SW=1280,SH=720,W=1280,H=720,BASE=2000000','SW=1296,SH=972,W=1280,H=688,BASE=2239488')
text=text.replace('warp_frame #(', 'warp_frame #(.AFFINE_FRAC_BITS(24),.SRC_W(SW),')
text=text.replace('.SRC_STRIDE(SW/2)', '.SRC_STRIDE(768)')
text=text.replace('r_addr*2+r_beats*16>SW*SH', 'r_addr*2+r_beats*16>1536*SH')
text=text.replace('x=address%SW;y=address/SW;', 'x=address%1536;y=address/1536;')
text=text.replace('source_pixel=(((x*13+y*7)%32)', "source_pixel=(x>=1296)?16'h0bad:(((x*13+y*7)%32)")
tb=out/'tb.v';tb.write_text(text)
files=[p for p in (ROOT/'rtl/warp').glob('*.v') if p.name not in ['tile_fetch.v','line_ring.v']]+[ROOT/'rtl/mem/mem_hub.v',ROOT/'sim/model/video_background.v',tb]
hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'rtl').rglob('*.v')}
env=os.environ.copy();env.update(PATHEXT='.COM;.EXE;.BAT;.CMD',COMSPEC=r'C:\Windows\System32\cmd.exe')
binary=out/'test.vvp'
r=subprocess.run(['D:/iverilog/bin/iverilog.exe','-g2012','-DFULL720P','-DSHARED_DDR','-I',str(out),'-s','tb_full','-o',str(binary),*[str(p) for p in files]],cwd=ROOT,env=env,capture_output=True,text=True)
(out/'compile.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stderr
r=subprocess.run(['D:/iverilog/bin/vvp.exe',str(binary)],cwd=ROOT,env=env,capture_output=True,text=True,timeout=1200)
body=r.stdout+r.stderr;(out/'test.log').write_text(body)
ok=r.returncode==0 and 'FULL_FRAME PASS:' in body and not any(t in body for t in ['FAIL','FATAL','TIMEOUT'])
d=dict(passed=ok,page=a.page,roi=[rx,ry,1280,688],pixels_compared=880640,hardware_tested=False,
 source_size=[1296,972],stride_pixels=1536,padding_poisoned=True,shared_ddr_modeled=True,rtl_sha256=hashes,
 cycles=int(re.search(r'FULL_FRAME PASS:[^\n]*cycles=\s*(\d+)',body)[1]) if ok else None,
 changed=[n for n,h in hashes.items() if hashlib.sha256((ROOT/n).read_bytes()).hexdigest()!=h])
if d['changed']:d['passed']=False
(out/'result.json').write_text(json.dumps(d,indent=2));print(body[-1800:],flush=True);print(out);raise SystemExit(0 if d['passed'] else 1)
