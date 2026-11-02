from pathlib import Path
import argparse,datetime,json,subprocess,os,hashlib,sys,binascii,struct
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from margin_geometry import load,identity
ap=argparse.ArgumentParser();ap.add_argument('--case',choices=['checked','footer','top'],required=True);a=ap.parse_args()
out=ROOT/'reports'/('margin_'+a.case+'_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'));out.mkdir()
g=load();gid=identity(g)[1];expected=[]
for page,(x,y) in enumerate(g['raw_view_offsets']):
 data=b'WRAW'+bytes([1,0x7f,page,0])+gid.to_bytes(4,'big')+struct.pack('>6H',1296,972,x,y,1280,688)+(42).to_bytes(4,'big')
 expected.append(data+binascii.crc_hqx(data,0xffff).to_bytes(2,'big')+b'OK')
(out/'expected.hex').write_text('\n'.join(v.hex() for v in expected)+'\n')
if a.case=='checked':
 top='tb_margin_checked';files=[ROOT/'rtl/cam'/n for n in ['ov5640_reg_rom.v','sccb_checked_master.v','ov5640_checked_config.v']]+[ROOT/'sim/model/sccb_sensor_model.v',ROOT/'sim/tb/tb_margin_checked.v']
elif a.case=='footer':
 top='tb_margin_footer';files=[ROOT/'rtl/common/margin_metadata.v',ROOT/'rtl/video/margin_footer.v',ROOT/'sim/tb/tb_margin_footer.v']
else:
 top='tb_margin_top';files=[ROOT/'rtl/top/top_pangu50.v']
 for folder in ['common','video','cam','hdmi','mem']:files += [p for p in (ROOT/'rtl'/folder).glob('*.v') if p.name!='cmos_8_16bit.v']
 files += [ROOT/'rtl/ddr/sync_vg.v']+[p for p in (ROOT/'rtl/warp').glob('*.v') if p.name not in ['tile_fetch.v','line_ring.v']]+[ROOT/'sim/tb/tb_margin_top.v']
env=os.environ.copy();env.update(PATHEXT='.COM;.EXE;.BAT;.CMD',COMSPEC=r'C:\Windows\System32\cmd.exe')
binary=out/'test.vvp';cmd=['D:/iverilog/bin/iverilog.exe','-g2012','-s',top,'-o',str(binary)]
if a.case=='top':cmd+=['-i']
r=subprocess.run(cmd+[str(p) for p in files],cwd=ROOT,env=env,capture_output=True,text=True)
(out/'compile.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stderr
r=subprocess.run(['D:/iverilog/bin/vvp.exe',str(binary),'+EXPECTED='+str(out/'expected.hex'),'+BITS='+str(out/'bits.txt')],cwd=ROOT,env=env,capture_output=True,text=True,timeout=300)
body=r.stdout+r.stderr;(out/'test.log').write_text(body);ok=r.returncode==0 and 'PASS' in body and not any(t in body for t in ['FATAL','FAIL','TIMEOUT'])
if ok and a.case=='footer':
 import numpy as np
 from reconstruct_margin_frame import decode
 bits=[int(n.strip(),16) for n in (out/'bits.txt').read_text().splitlines()]
 assert len(bits)==1024
 for page in range(4):
  image=np.zeros((720,1280,3),np.uint8)
  for i,bit in enumerate(bits[page*256:(page+1)*256]):image[704:720,i*4:i*4+4]=bit*255
  assert decode(image)['page']==page
result=dict(passed=ok,hardware_tested=False,case=a.case,vendor_ip_black_boxes=a.case=='top',
 source_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
(out/'result.json').write_text(json.dumps(result,indent=2));print(body[-2500:]);print(out);raise SystemExit(0 if ok else 1)
